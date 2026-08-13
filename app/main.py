from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

app = FastAPI(title="Deployment Request Service")

# process-local memory only (session 1) — no datastore yet, see README roadmap.
_users: dict[int, "User"] = {}

# fake token store, same in-memory-only stance as _users — no real auth
# service yet. Maps bearer token -> role.
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


def _get_user_or_404(user_id: int) -> User:
    user = _users.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user {user_id} not in DB")
    return user


@app.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(user: User) -> User:
    if user.id in _users:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"user {user.id} already exists")
    _users[user.id] = user
    return user


@app.get("/users/{user_id}")
def get_user(user_id: int) -> User:
    return _get_user_or_404(user_id)


@app.put("/users/{user_id}")
def replace_user(user_id: int, user: User) -> User:
    _get_user_or_404(user_id)
    if user.id != user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "body id must match path id")
    _users[user_id] = user
    return user


@app.patch("/users/{user_id}")
def update_user(user_id: int, patch: UserUpdate) -> User:
    existing = _get_user_or_404(user_id)
    updated = existing.model_copy(update=patch.model_dump(exclude_unset=True))
    _users[user_id] = updated
    return updated


@app.delete("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
def delete_user(user_id: int) -> dict[str, str]:
    _get_user_or_404(user_id)
    del _users[user_id]
    return {"detail": f"user {user_id} deleted"}
