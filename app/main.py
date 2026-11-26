import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime

import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ValidationError
from redis.backoff import NoBackoff
from redis.retry import Retry

DATABASE_URL = os.environ["DATABASE_URL"]

# Which replica answered. In Docker the hostname is the short container ID, so
# each `--scale api=N` replica reports a different value with no extra config.
INSTANCE_ID = os.environ.get("INSTANCE_ID") or socket.gethostname()

# The schema lives in migrations/, applied by `alembic upgrade head` before the
# API starts. Named here because which unique rule broke decides the response.
EMAIL_CONSTRAINT = "users_email_key"

# One pool per process. Connecting per request would pay a TCP and auth
# handshake on every call; the pool also lets startup wait for Postgres.
pool = ConnectionPool(DATABASE_URL, open=False)

# Redis holds a temporary copy of selected reads. Postgres stays the source of
# truth: nothing is written only to Redis, and losing Redis loses no data.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# How stale a cached user may be, at most. A lab choice: in a real design the
# product requirement decides it, and a bank balance would not get 15 seconds.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "15"))

# Short timeouts and no retries: a cache is only worth asking if asking costs
# less than the database read it saves. When Redis is down we want to know in
# milliseconds and go to Postgres, not wait out redis-py's retry backoff.
cache = redis.Redis.from_url(
    REDIS_URL,
    socket_connect_timeout=0.2,
    socket_timeout=0.2,
    retry=Retry(NoBackoff(), 0),
)

logger = logging.getLogger("app.cache")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Postgres may still be running initdb when the API starts. The pool keeps
    # retrying in the background, so wait rather than crash on a cold volume.
    pool.open(wait=True, timeout=30)
    yield
    pool.close()


app = FastAPI(title="Deployment Request Service", lifespan=lifespan)


@app.middleware("http")
async def add_instance_id(request: Request, call_next):
    # a header, not a body field: it describes the server, not the user, and
    # it lands on error responses too, so a 404 still says who sent it.
    response = await call_next(request)
    response.headers["X-Instance-ID"] = INSTANCE_ID
    return response


def get_conn():
    # One connection, one transaction, per request. Leaving this block commits.
    with pool.connection() as conn:
        yield conn


def get_conn_factory():
    # GET /users/{id} needs Postgres only on a cache miss, so it borrows a
    # connection then and not before. A HIT that still held one of the pool's
    # connections would not relieve the limit we hit under load in session 7.1.
    return pool.connection


def get_cache() -> redis.Redis:
    return cache


@app.get("/health/live")
def health_live() -> dict[str, str]:
    # Liveness only says this process can answer HTTP; a database outage should
    # not cause an orchestrator to restart an otherwise healthy process.
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    # Every current business endpoint needs Postgres, so only accept traffic
    # while a pooled connection can successfully run a trivial query. Redis is
    # not checked: a cache outage makes reads slower, not wrong, so it is no
    # reason to take an instance out of rotation.
    try:
        with pool.connection(timeout=1) as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="not ready",
        ) from None
    return {"status": "ok"}


# fake token store, no real auth service yet. Maps bearer token -> role.
_TOKEN_ROLES: dict[str, str] = {
    "admin-token": "admin",
    "viewer-token": "viewer",
}


def require_role(*allowed_roles: str):
    def _check(authorization: str | None = Header(default=None)) -> None:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
        role = _TOKEN_ROLES.get(authorization.removeprefix("Bearer "))
        if role is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
        if role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role '{role}' cannot perform this action")

    return _check


class User(BaseModel):
    id: int
    name: str
    email: str


class StoredUser(User):
    # what the API returns. created_at is set by Postgres on INSERT, so it is not
    # on User: a client cannot send it, and a sent value is ignored like any
    # other unknown field.
    created_at: datetime


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


# one list of returned columns, so a new column cannot reach some endpoints
# and silently miss others.
USER_COLUMNS = "id, name, email, created_at"

SELECT_USER = f"SELECT {USER_COLUMNS} FROM users WHERE id = %s"
EMAIL_OWNER = "SELECT id FROM users WHERE email = %s AND id <> %s"
UPDATE_USER = f"UPDATE users SET name = %s, email = %s WHERE id = %s RETURNING {USER_COLUMNS}"


def _to_user(row: tuple) -> StoredUser:
    return StoredUser(id=row[0], name=row[1], email=row[2], created_at=row[3])


def _user_or_404(row: tuple | None, user_id: int) -> StoredUser:
    # every statement below returns the row it touched, so "no row" is the only
    # 404 test we need, and it stays correct if the row goes away mid-request.
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user {user_id} not in DB")
    return _to_user(row)


def _get_user_or_404(conn, user_id: int) -> StoredUser:
    return _user_or_404(conn.execute(SELECT_USER, (user_id,)).fetchone(), user_id)


def _update_user(conn, user_id: int, user: User) -> StoredUser:
    try:
        row = conn.execute(UPDATE_USER, (user.name, user.email, user_id)).fetchone()
    except UniqueViolation:
        # id never changes in an UPDATE, so email is the only unique rule it can
        # break. This is the race _reject_conflict cannot see: two requests both
        # read the address as free, and the constraint stops the second write.
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"email {user.email} already belongs to another user"
        ) from None
    return _user_or_404(row, user_id)


def _cache_key(user_id: int) -> str:
    return f"user:{user_id}"


def _cache_get(cache: redis.Redis, user_id: int) -> tuple[StoredUser | None, str]:
    # returns the cached user, if any, and what happened, for the X-Cache header.
    # A failing cache is a slower request, never a failed one.
    key = _cache_key(user_id)
    try:
        cached = cache.get(key)
    except redis.RedisError as exc:
        logger.warning("cache_read_failed key=%s error=%r fallback=postgres", key, exc)
        return None, "BYPASS"
    if cached is None:
        return None, "MISS"
    try:
        return StoredUser.model_validate_json(cached), "HIT"
    except ValidationError:
        # written by an older shape of StoredUser, or not by us at all. Treat it
        # as a miss; the fresh copy written below replaces it.
        logger.warning("cache_entry_invalid key=%s fallback=postgres", key)
        return None, "MISS"


def _cache_set(cache: redis.Redis, user: StoredUser) -> None:
    key = _cache_key(user.id)
    try:
        cache.setex(key, CACHE_TTL_SECONDS, user.model_dump_json())
    except redis.RedisError as exc:
        logger.warning("cache_write_failed key=%s error=%r", key, exc)


def _cache_invalidate(cache: redis.Redis, *user_ids: int) -> None:
    # called only after Postgres has committed: invalidating first would let a
    # concurrent GET re-cache the old row before the write lands. If this fails
    # the write still succeeded, so we log it and let the TTL bound how long the
    # stale copy can be served.
    keys = [_cache_key(user_id) for user_id in user_ids]
    try:
        cache.delete(*keys)
    except redis.RedisError as exc:
        logger.warning(
            "cache_invalidate_failed keys=%s error=%r stale_for_up_to=%ss", keys, exc, CACHE_TTL_SECONDS
        )


def _get_users(conn) -> list[StoredUser]:
    # unbounded on purpose for now: the response grows with the table, and
    # pagination is its own session. ORDER BY so repeated calls agree, which an
    # unordered SELECT does not guarantee.
    rows = conn.execute(f"SELECT {USER_COLUMNS} FROM users ORDER BY id").fetchall()
    return [_to_user(row) for row in rows]


@app.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(user: User, conn=Depends(get_conn), cache=Depends(get_cache)) -> StoredUser:
    try:
        row = conn.execute(
            f"INSERT INTO users (id, name, email) VALUES (%s, %s, %s) RETURNING {USER_COLUMNS}",
            (user.id, user.name, user.email),
        ).fetchone()
    except UniqueViolation as exc:
        # the constraint name says which rule broke; the message text is not a
        # contract and changes with Postgres version and locale.
        if exc.diag.constraint_name == EMAIL_CONSTRAINT:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"email {user.email} already belongs to another user"
            ) from None
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"user {user.id} already exists") from None
    created = _user_or_404(row, user.id)
    conn.commit()
    # nothing should be cached for an id that did not exist, but a DELETE whose
    # invalidation failed can leave the old user there. Clear it so the new
    # user is not hidden behind it for up to the TTL.
    _cache_invalidate(cache, user.id)
    return created


@app.get("/users/{user_id}")
def get_user(
    user_id: int,
    response: Response,
    connect=Depends(get_conn_factory),
    cache=Depends(get_cache),
) -> StoredUser:
    # cache-aside: ask Redis first, fall back to Postgres, then keep a copy.
    user, outcome = _cache_get(cache, user_id)
    # a header so the lab can see which path answered.
    response.headers["X-Cache"] = outcome
    if user is not None:
        return user
    with connect() as conn:
        # a 404 raises here and is not cached, so a user created a moment later
        # is visible on the next read rather than after the TTL.
        try:
            user = _get_user_or_404(conn, user_id)
        except HTTPException as exc:
            # a raised HTTPException builds its own response and drops the
            # header set above, so carry it over: a 404 also says whether the
            # cache was consulted.
            exc.headers = {"X-Cache": outcome}
            raise
    if outcome == "MISS":
        _cache_set(cache, user)
    return user


@app.get("/users")
def get_users(conn=Depends(get_conn)) -> list[StoredUser]:
    return _get_users(conn)


def _reject_conflict(conn, current: User, incoming: User) -> None:
    # the rules that need the stored user to decide, so they run after the 404.
    # A rejection here is 409, not 400: the body is well formed, it disagrees
    # with the state the server already holds.
    conflicts = []
    if incoming.id != current.id:
        conflicts.append(f"id is immutable, {current.id} cannot become {incoming.id}")
    # users_email_key is what guarantees uniqueness, concurrent PUTs included.
    # This check stays because it can name the owner, which the constraint can't.
    owner = conn.execute(EMAIL_OWNER, (incoming.email, current.id)).fetchone()
    if owner is not None:
        conflicts.append(f"email {incoming.email} already belongs to user {owner[0]}")
    if conflicts:
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(conflicts))


@app.put("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def replace_user(user_id: int, user: User, conn=Depends(get_conn), cache=Depends(get_cache)) -> Response:
    current = _get_user_or_404(conn, user_id)
    _reject_conflict(conn, current, user)
    # the user is dropped, not returned, but it still proves the UPDATE hit a
    # row rather than silently matching nothing.
    _update_user(conn, user_id, user)
    conn.commit()
    _cache_invalidate(cache, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/users/{user_id}")
def update_user(
    user_id: int, patch: UserUpdate, conn=Depends(get_conn), cache=Depends(get_cache)
) -> StoredUser:
    existing = _get_user_or_404(conn, user_id)
    updated = existing.model_copy(update=patch.model_dump(exclude_unset=True))
    stored = _update_user(conn, user_id, updated)
    # commit here, not when get_conn exits: the invalidation must follow the
    # commit, and a dependency's teardown is not guaranteed to run before it.
    conn.commit()
    _cache_invalidate(cache, user_id)
    return stored


@app.delete("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
def delete_user(user_id: int, conn=Depends(get_conn), cache=Depends(get_cache)) -> dict[str, str]:
    row = conn.execute(f"DELETE FROM users WHERE id = %s RETURNING {USER_COLUMNS}", (user_id,)).fetchone()
    _user_or_404(row, user_id)
    conn.commit()
    _cache_invalidate(cache, user_id)
    return {"detail": f"user {user_id} deleted"}


@app.delete("/users", dependencies=[Depends(require_role("admin"))])
def delete_users(conn=Depends(get_conn), cache=Depends(get_cache)) -> dict[str, str]:
    # RETURNING id, not the whole row: the ids name the cache keys to clear,
    # and an id is all we need to carry back from Postgres for that.
    ids = [row[0] for row in conn.execute("DELETE FROM users RETURNING id").fetchall()]
    count = len(ids)
    conn.commit()
    if ids:
        _cache_invalidate(cache, *ids)
    return {"detail": f"deleted {count} user(s) from the database"}
