import os

# app.main reads DATABASE_URL at import time and fails fast without it. The pool
# is built with open=False, so this URL is never dialled by the tests.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
