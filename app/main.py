import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL
);
"""

# One pool per process. Connecting per request would pay a TCP and auth
# handshake on every call; the pool also lets startup wait for Postgres.
pool = ConnectionPool(DATABASE_URL, open=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Postgres may still be running initdb when the API starts. The pool keeps
    # retrying in the background, so wait rather than crash on a cold volume.
    pool.open(wait=True, timeout=30)
    with pool.connection() as conn:
        conn.execute(SCHEMA)
    yield
    pool.close()


app = FastAPI(title="Deployment Request Service", lifespan=lifespan)


def get_conn():
    # One connection, one transaction, per request. Leaving this block commits.
    with pool.connection() as conn:
        yield conn


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


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


SELECT_USER = "SELECT id, name, email FROM users WHERE id = %s"
EMAIL_OWNER = "SELECT id FROM users WHERE email = %s AND id <> %s"
UPDATE_USER = "UPDATE users SET name = %s, email = %s WHERE id = %s RETURNING id, name, email"


def _user_or_404(row: tuple | None, user_id: int) -> User:
    # every statement below returns the row it touched, so "no row" is the only
    # 404 test we need, and it stays correct if the row goes away mid-request.
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user {user_id} not in DB")
    return User(id=row[0], name=row[1], email=row[2])


def _get_user_or_404(conn, user_id: int) -> User:
    return _user_or_404(conn.execute(SELECT_USER, (user_id,)).fetchone(), user_id)


def _get_users_or_404() -> [User]:
    users = []
    for id, user in _users.items():
        users.append(user)
    if users == []:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No users found in the database")
    return users


@app.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(user: User, conn=Depends(get_conn)) -> User:
    try:
        row = conn.execute(
            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) RETURNING id, name, email",
            (user.id, user.name, user.email),
        ).fetchone()
    except UniqueViolation:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"user {user.id} already exists") from None
    return _user_or_404(row, user.id)


@app.get("/users/{user_id}")
def get_user(user_id: int, conn=Depends(get_conn)) -> User:
    return _get_user_or_404(conn, user_id)


@app.get("/users")
def get_users():
    return _get_users_or_404()


def _reject_conflict(conn, current: User, incoming: User) -> None:
    # the rules that need the stored user to decide, so they run after the 404.
    # A rejection here is 409, not 400: the body is well formed, it disagrees
    # with the state the server already holds.
    conflicts = []
    if incoming.id != current.id:
        conflicts.append(f"id is immutable, {current.id} cannot become {incoming.id}")
    # no UNIQUE on email yet, so two concurrent PUTs can both read "free" and
    # both write. This closes the sequential case only, deliberately.
    owner = conn.execute(EMAIL_OWNER, (incoming.email, current.id)).fetchone()
    if owner is not None:
        conflicts.append(f"email {incoming.email} already belongs to user {owner[0]}")
    if conflicts:
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(conflicts))


@app.put("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def replace_user(user_id: int, user: User, conn=Depends(get_conn)) -> Response:
    current = _get_user_or_404(conn, user_id)
    _reject_conflict(conn, current, user)
    row = conn.execute(UPDATE_USER, (user.name, user.email, user_id)).fetchone()
    # the row is dropped, not returned, but it still proves the UPDATE hit a row
    # rather than silently matching nothing.
    _user_or_404(row, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/users/{user_id}")
def update_user(user_id: int, patch: UserUpdate, conn=Depends(get_conn)) -> User:
    existing = _get_user_or_404(conn, user_id)
    updated = existing.model_copy(update=patch.model_dump(exclude_unset=True))
    row = conn.execute(UPDATE_USER, (updated.name, updated.email, user_id)).fetchone()
    return _user_or_404(row, user_id)


@app.delete("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
def delete_user(user_id: int, conn=Depends(get_conn)) -> dict[str, str]:
    row = conn.execute("DELETE FROM users WHERE id = %s RETURNING id, name, email", (user_id,)).fetchone()
    _user_or_404(row, user_id)
    return {"detail": f"user {user_id} deleted"}