import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, status
from psycopg.errors import UniqueViolation
from pydantic import BaseModel


DATABASE_URL = os.environ["DATABASE_URL"]


# -------------------------------------------------------------------
# Database setup
# -------------------------------------------------------------------

def create_tables() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE
            );
            """
        )
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Deployment Request Service",
    lifespan=lifespan,
)


# -------------------------------------------------------------------
# Fake authentication
# -------------------------------------------------------------------

# Fake token store.
# Maps bearer token -> role.
_TOKEN_ROLES: dict[str, str] = {
    "admin-token": "admin",
    "viewer-token": "viewer",
}


def require_role(*allowed_roles: str):
    def _check(
        authorization: str | None = Header(default=None),
    ) -> None:

        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
            )

        token = authorization.removeprefix("Bearer ")
        role = _TOKEN_ROLES.get(token)

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid token",
            )

        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{role}' cannot perform this action",
            )

    return _check


# -------------------------------------------------------------------
# Pydantic models
# -------------------------------------------------------------------

class User(BaseModel):
    id: int
    name: str
    email: str


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


# -------------------------------------------------------------------
# Database helper
# -------------------------------------------------------------------

def get_user_or_404(user_id: int) -> User:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE id = %s;
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user {user_id} not found",
        )

    return User(
        id=row[0],
        name=row[1],
        email=row[2],
    )


# -------------------------------------------------------------------
# CREATE
# -------------------------------------------------------------------

@app.post(
    "/users",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
)
def create_user(user: User) -> User:

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                INSERT INTO users (id, name, email)
                VALUES (%s, %s, %s);
                """,
                (
                    user.id,
                    user.name,
                    user.email,
                ),
            )

            conn.commit()

    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user id or email already exists",
        )

    return user


# -------------------------------------------------------------------
# READ
# -------------------------------------------------------------------

@app.get(
    "/users/{user_id}",
    response_model=User,
)
def get_user(user_id: int) -> User:
    return get_user_or_404(user_id)


# -------------------------------------------------------------------
# REPLACE
# -------------------------------------------------------------------

@app.put(
    "/users/{user_id}",
    response_model=User,
)
def replace_user(
    user_id: int,
    user: User,
) -> User:

    get_user_or_404(user_id)

    if user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body id must match path id",
        )

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                UPDATE users
                SET name = %s,
                    email = %s
                WHERE id = %s;
                """,
                (
                    user.name,
                    user.email,
                    user_id,
                ),
            )

            conn.commit()

    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email already exists",
        )

    return user


# -------------------------------------------------------------------
# PARTIAL UPDATE
# -------------------------------------------------------------------

@app.patch(
    "/users/{user_id}",
    response_model=User,
)
def update_user(
    user_id: int,
    patch: UserUpdate,
) -> User:

    existing = get_user_or_404(user_id)

    updated = existing.model_copy(
        update=patch.model_dump(exclude_unset=True)
    )

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                UPDATE users
                SET name = %s,
                    email = %s
                WHERE id = %s;
                """,
                (
                    updated.name,
                    updated.email,
                    user_id,
                ),
            )

            conn.commit()

    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email already exists",
        )

    return updated


# -------------------------------------------------------------------
# DELETE
# -------------------------------------------------------------------

@app.delete(
    "/users/{user_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_user(
    user_id: int,
) -> dict[str, str]:

    get_user_or_404(user_id)

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            DELETE FROM users
            WHERE id = %s;
            """,
            (user_id,),
        )

        conn.commit()

    return {
        "detail": f"user {user_id} deleted"
    }
