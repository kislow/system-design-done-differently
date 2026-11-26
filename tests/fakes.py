import redis


class FakeCache:
    """The slice of redis.Redis the API uses, kept in a dict."""

    def __init__(self, entries: dict[str, str] | None = None):
        self.entries = dict(entries or {})
        self.ttls: dict[str, int] = {}
        self.calls: list[str] = []

    def get(self, key):
        self.calls.append(f"get {key}")
        return self.entries.get(key)

    def setex(self, key, ttl, value):
        self.calls.append(f"setex {key}")
        self.entries[key] = value
        self.ttls[key] = ttl

    def delete(self, *keys):
        self.calls.append(f"delete {' '.join(keys)}")
        for key in keys:
            self.entries.pop(key, None)


class DownCache:
    """Redis as the API sees it when the container is stopped."""

    def __getattr__(self, _name):
        def fail(*_args):
            raise redis.ConnectionError("Error -2 connecting to redis:6379. Name or service not known.")

        return fail
