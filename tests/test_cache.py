from contextlib import nullcontext
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import CACHE_TTL_SECONDS, app, get_cache, get_conn, get_conn_factory
from tests.fakes import DownCache, FakeCache

BOB = (1, "bob", "bob@coderco.io", datetime(2026, 11, 5, 19, 6, tzinfo=timezone.utc))
BOB_JSON = '{"id":1,"name":"bob","email":"bob@coderco.io","created_at":"2026-11-05T19:06:00Z"}'


class RecordingConn:
    """Postgres holding one user, writing down what it is asked to do."""

    def __init__(self, row=BOB, calls: list[str] | None = None):
        self.row = row
        self.calls = [] if calls is None else calls

    def execute(self, sql, params=()):
        self.calls.append(sql.split()[0])
        if sql.startswith("UPDATE"):
            self.row = (self.row[0], params[0], params[1], self.row[3])
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        self.calls.append("COMMIT")


def _client(cache, conn) -> TestClient:
    # conftest clears the overrides after each test. One cache and one conn for
    # the whole test, so a second request sees what the first one left behind.
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_conn_factory] = lambda: lambda: nullcontext(conn)
    return TestClient(app)


def test_first_read_is_a_miss_and_second_is_a_hit():
    cache, conn = FakeCache(), RecordingConn()
    client = _client(cache, conn)

    first = client.get("/users/1")
    second = client.get("/users/1")

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()
    # the point of the cache: two reads, one trip to Postgres.
    assert conn.calls == ["SELECT"]
    assert cache.ttls["user:1"] == CACHE_TTL_SECONDS


def test_patch_invalidates_the_cached_user_after_commit():
    calls: list[str] = []
    cache, conn = FakeCache({"user:1": BOB_JSON}), RecordingConn(calls=calls)
    cache.calls = calls
    client = _client(cache, conn)

    response = client.patch("/users/1", json={"name": "robert"})

    assert response.status_code == 200
    assert "user:1" not in cache.entries
    # commit first: invalidating before it would let a concurrent GET re-cache
    # the old row.
    assert calls == ["SELECT", "UPDATE", "COMMIT", "delete user:1"]
    after = client.get("/users/1")
    assert after.headers["X-Cache"] == "MISS"
    assert after.json()["name"] == "robert"


def test_redis_down_still_answers_from_postgres():
    client = _client(DownCache(), RecordingConn())

    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.headers["X-Cache"] == "BYPASS"
    assert response.json()["name"] == "bob"


def test_redis_down_does_not_fail_a_write():
    conn = RecordingConn()
    client = _client(DownCache(), conn)

    response = client.patch("/users/1", json={"name": "robert"})

    assert response.status_code == 200
    assert "COMMIT" in conn.calls


def test_missing_user_is_not_cached():
    cache = FakeCache()
    client = _client(cache, RecordingConn(row=None))

    response = client.get("/users/999")

    assert response.status_code == 404
    assert response.headers["X-Cache"] == "MISS"
    assert cache.entries == {}


def test_unreadable_cache_entry_is_a_miss_and_gets_replaced():
    cache = FakeCache({"user:1": "not a user"})
    client = _client(cache, RecordingConn())

    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    assert cache.entries["user:1"] != "not a user"
