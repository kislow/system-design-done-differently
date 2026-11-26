# Session 11 lab steps: Redis cache on `GET /users/{id}`

The commands for [session 11](session-11.md). Run everything from the repo root. Watch two
response headers:

- `X-Cache`: `MISS`, `HIT` or `BYPASS`
- `X-Instance-ID`: which API replica answered

## 0. Start the stack

```bash
docker compose up -d --build
docker compose ps
```

Expected: `db` and `redis` healthy, two `api` containers healthy, `load-balancer` up.

## 1. Seed user 501

```bash
curl -i -X POST http://localhost:8000/users \
  -H 'content-type: application/json' \
  -d '{"id":501,"name":"Ada","email":"ada@example.com"}'
```

Expected: `201 Created`.

If it says `400 user 501 already exists`, delete the user and run the `POST` again. `DELETE` needs
the admin token; without it the answer is `401 missing bearer token`.

```bash
curl -i -X DELETE http://localhost:8000/users/501 \
  -H 'Authorization: Bearer admin-token'
```

## 2. Part A: first and second read

```bash
curl -i http://localhost:8000/users/501
curl -i http://localhost:8000/users/501
```

Expected:

```
first  → X-Cache: MISS
second → X-Cache: HIT
```

The `X-Instance-ID` differs between the two: one replica filled the cache, the other read from it.

Look at the copy Redis holds and how long it has left:

```bash
docker compose exec redis redis-cli get user:501
docker compose exec redis redis-cli ttl user:501
```

Expected: the user as JSON, and a number counting down from 300, the TTL Compose sets.

## 3. Part B: change the user

```bash
curl -i -X PATCH http://localhost:8000/users/501 \
  -H 'content-type: application/json' \
  -d '{"name":"Ada Lovelace"}'

curl -i http://localhost:8000/users/501
curl -i http://localhost:8000/users/501
```

Expected:

```
PATCH      → 200, name is "Ada Lovelace"
first GET  → X-Cache: MISS, name is "Ada Lovelace"
second GET → X-Cache: HIT
```

Between the `PATCH` and the first `GET`, Redis holds nothing for the user:
`docker compose exec redis redis-cli get user:501` prints `(nil)`. The write deletes the copy; the
next read puts the new one back.

## 4. TTL expiry

At 300 seconds an expiry is a five-minute wait. Restart the API with a 15-second TTL to watch one:

```bash
CACHE_TTL_SECONDS=15 docker compose up -d api
```

Repeat step 3 with a different name, so the copy written with the old TTL is replaced. Then wait
16 seconds and read twice:

```bash
sleep 16
curl -i http://localhost:8000/users/501
curl -i http://localhost:8000/users/501
```

Expected: `MISS`, then `HIT`. Nobody changed the user; the copy just expired.

Go back to the Compose default with `docker compose up -d api`.

The TTL is a plain number of seconds. `300s` stops the API at startup with
`ValueError: invalid literal for int()`.

## 5. Part C: stop Redis

Ask the room first: should a cache outage make user data disappear?

```bash
docker compose stop redis
curl -i http://localhost:8000/users/501
```

Expected: `200 OK` with `X-Cache: BYPASS`. The API skipped the cache and read PostgreSQL.

Show the logged cache error:

```bash
docker compose logs api --since 2m | grep cache
```

Expected: `cache_read_failed key=user:501 ... fallback=postgres`.

The API is still ready, because Redis is not part of readiness:

```bash
curl -i http://localhost:8000/health/ready
```

Expected: `200`.

## 6. Restart Redis

```bash
docker compose start redis
curl -i http://localhost:8000/users/501
curl -i http://localhost:8000/users/501
```

Expected: `MISS`, then `HIT`. Redis came back empty and refilled from PostgreSQL.

## 7. Optional: a missing user is not cached

```bash
curl -i http://localhost:8000/users/999
curl -i http://localhost:8000/users/999
```

Expected: `404` with `X-Cache: MISS` both times.

## 8. Optional: invalidate by hand

```bash
docker compose exec redis redis-cli keys 'user:*'
docker compose exec redis redis-cli del user:501
docker compose exec redis redis-cli flushall
```

`del` removes one user's copy and prints `(integer) 1` if it existed. `flushall` empties the cache.
The next read of anything removed is a `MISS`.

## Clean up

```bash
docker compose down
```

The users stay in the `db-data` volume. Redis keeps nothing.
