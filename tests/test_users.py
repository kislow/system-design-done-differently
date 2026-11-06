from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

from app.main import EMAIL_CONSTRAINT, INSTANCE_ID, app, get_conn


class NoRowsConn:
    """A connection whose queries match nothing, the state a 404 is read from."""

    def execute(self, *_args):
        return self

    def fetchone(self):
        return None


def test_get_missing_user_returns_404():
    app.dependency_overrides[get_conn] = NoRowsConn
    try:
        # TestClient outside a `with` block skips lifespan, so no Postgres is
        # needed: the 404 is decided by the row the SELECT returns, not by the DB.
        response = TestClient(app).get("/users/999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "user 999 not in DB"}


def test_responses_carry_instance_id_header():
    app.dependency_overrides[get_conn] = NoRowsConn
    try:
        # a 404 is enough: the header is added on every response, errors included.
        response = TestClient(app).get("/users/999")
    finally:
        app.dependency_overrides.clear()

    assert response.headers["X-Instance-ID"] == INSTANCE_ID
    assert INSTANCE_ID


class EmailTaken(UniqueViolation):
    # Postgres fills diag from the server's error report; this stands in for one
    # that names the email constraint.
    diag = SimpleNamespace(constraint_name=EMAIL_CONSTRAINT)


class IdTaken(UniqueViolation):
    diag = SimpleNamespace(constraint_name="users_pkey")


class WriteFailsConn:
    """Reads find user 1; writes hit a unique constraint, as Postgres reports it."""

    def __init__(self, error: UniqueViolation):
        self.error = error

    def execute(self, sql, *_args):
        if sql.startswith("SELECT"):
            return self
        raise self.error

    def fetchone(self):
        return (1, "bob", "bob@coderco.io", datetime(2026, 11, 5, tzinfo=timezone.utc))


def _send(error: UniqueViolation, method: str, path: str, body: dict):
    app.dependency_overrides[get_conn] = lambda: WriteFailsConn(error)
    try:
        return TestClient(app).request(method, path, json=body)
    finally:
        app.dependency_overrides.clear()


def test_create_with_taken_email_returns_409():
    response = _send(EmailTaken(), "POST", "/users", {"id": 2, "name": "eve", "email": "bob@coderco.io"})

    assert response.status_code == 409
    assert response.json() == {"detail": "email bob@coderco.io already belongs to another user"}


def test_create_with_taken_id_still_returns_400():
    response = _send(IdTaken(), "POST", "/users", {"id": 1, "name": "eve", "email": "eve@coderco.io"})

    assert response.status_code == 400
    assert response.json() == {"detail": "user 1 already exists"}


def test_patch_to_taken_email_returns_409():
    # PATCH never checked email ownership; before the constraint this write
    # succeeded and left two users sharing an address.
    response = _send(EmailTaken(), "PATCH", "/users/1", {"email": "eve@coderco.io"})

    assert response.status_code == 409
    assert response.json() == {"detail": "email eve@coderco.io already belongs to another user"}


class OneUserConn:
    def execute(self, *_args):
        return self

    def fetchone(self):
        return (1, "bob", "bob@coderco.io", datetime(2026, 11, 5, 19, 6, tzinfo=timezone.utc))


def test_get_user_returns_created_at():
    app.dependency_overrides[get_conn] = OneUserConn
    try:
        response = TestClient(app).get("/users/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["created_at"] == "2026-11-05T19:06:00Z"
