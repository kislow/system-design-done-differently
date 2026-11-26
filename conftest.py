import os

import pytest

# app.main reads DATABASE_URL at import time and fails fast without it. The pool
# is built with open=False, so this URL is never dialled by the tests.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture(autouse=True)
def no_real_redis():
    # every test gets an empty in-memory cache, so none of them depends on, or
    # leaks state through, a Redis server. Tests that need a particular cache
    # override get_cache themselves.
    from app.main import app, get_cache
    from tests.fakes import FakeCache

    # a lambda, not the class: FastAPI reads an override's signature for request
    # parameters, and would take FakeCache's `entries` argument as the JSON body.
    app.dependency_overrides[get_cache] = lambda: FakeCache()
    yield
    app.dependency_overrides.clear()
