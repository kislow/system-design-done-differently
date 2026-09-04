from fastapi.testclient import TestClient

from app.main import app, get_conn


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
