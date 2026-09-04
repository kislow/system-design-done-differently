# Deployment Request Service

The running service for this series. A FastAPI CRUD API for users, storing them in PostgreSQL,
implementing session 1's HLD (`../diagrams/session1-hla-method-req-res.png`): client → API →
datastore. All three boxes are now on the request path.

Session write-ups live in `../sessions/`: start with
[`../sessions/session-3.md`](../sessions/session-3.md) for what this version of the service does
and why.

## Requirements

- Docker + Docker Compose (recommended), or
- Python 3.13+

## Run with Docker (recommended)

```bash
docker compose up --build
```

The API is on `http://localhost:8000`, Postgres on `localhost:5432`. The API waits for Postgres
to accept connections before it starts serving, and creates the `users` table on startup.

Credentials live in `.env`, committed because they are fake and only reachable on your machine.
Both the db container and the API's `DATABASE_URL` read from it, so there is one copy of each
value.

Stop and remove both containers:

```bash
docker compose down
```

## Run locally without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# required, the app fails fast without it. Point it at the Compose Postgres:
set -a; . ./.env; set +a
export DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@localhost:5432/$POSTGRES_DB"
uvicorn app.main:app --reload
```

## Data model

PostgreSQL is the source of truth. One user is one row in the `users` table:

| Column  | Type   | Notes           |
|---------|--------|-----------------|
| `id`    | BIGINT | primary key     |
| `name`  | TEXT   | not null        |
| `email` | TEXT   | not null        |

```json
{"id": 123, "name": "bob", "email": "bob@coderco.io"}
```

Users survive API restarts. They are removed only by `DELETE /users/{id}`, `DELETE /users` or by deleting the
`db-data` volume.

## Prove it persists

```bash
./scripts/prove-persistence.sh
```

It seeds a user, restarts the API, takes the stack down and back up, and fails loudly if the user
stops coming back. Same thing by hand:

```bash
curl -X POST localhost:8000/users -H 'content-type: application/json' \
  -d '{"id":123,"name":"bob","email":"bob@coderco.io"}'
docker compose restart api
curl localhost:8000/users/123          # still 200, the row outlived the process

docker compose down                    # keeps the db-data volume
docker compose up -d
curl localhost:8000/users/123          # still 200

docker compose exec db psql -U appuser -d appdb -c 'select * from users;'
```

Deleting the volume (`docker compose down -v`) is the one thing that does clear it.

## Run the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest -q
```

No Postgres needed. The tests override the `get_conn` dependency and drive the API through
`TestClient`, which skips the lifespan, so the connection pool is never opened. See
[`../sessions/session-5.md`](../sessions/session-5.md) for what that does and does not prove.

It is `-m pytest`, not `-m test`: `test` is CPython's own stdlib suite and will happily run for
minutes.

## Endpoints

| Method | Path          | Auth         | Body                          | Success   | Errors                                    |
|--------|---------------|--------------|--------------------------------|-----------|--------------------------------------------|
| POST   | `/users`      | none         | full user                     | 201       | 400 if `id` already exists                 |
| GET    | `/users/{id}` | none         | none                           | 200       | 404 if not found                           |
| GET    | `/users`      | none         | none                           | 200       | none, `[]` when empty                      |
| PUT    | `/users/{id}` | none         | full user, `id` must match path | 204       | 404 if not found, 409 on id change or email owned by another user |
| PATCH  | `/users/{id}` | none         | partial `{name?, email?}`     | 200       | 404 if not found                           |
| DELETE | `/users/{id}` | admin token  | none                           | 200       | 401 no/invalid token, 403 wrong role, 404 if not found |
| DELETE | `/users`      | admin token  | none                           | 200       | 401 no/invalid token, 403 wrong role        |


## Auth

`DELETE` requires `Authorization: Bearer <token>`. The token → role mapping is a hardcoded
table for the exercise, not real auth:

| Token          | Role   | Can delete? |
|----------------|--------|-------------|
| `admin-token`  | admin  | yes         |
| `viewer-token` | viewer | no (403)    |

## Example requests

```bash
# create
curl -X POST localhost:8000/users -H 'content-type: application/json' \
  -d '{"id":123,"name":"bob","email":"bob@coderco.io"}'

# read
curl -X GET localhost:8000/users/123

# read all users
curl -X GET localhost:8000/users

# partial update
curl -X PATCH localhost:8000/users/123 -H 'content-type: application/json' \
  -d '{"email":"new@coderco.io"}'

# full overwrite: 204, no body
curl -i -X PUT localhost:8000/users/123 -H 'content-type: application/json' \
  -d '{"id":123,"name":"bob b","email":"bob@coderco.io"}'

# conflict, changing an immutable id: 409
curl -i -X PUT localhost:8000/users/123 -H 'content-type: application/json' \
  -d '{"id":124,"name":"bob b","email":"bob@coderco.io"}'

# conflict, email already belongs to another user: 409
curl -i -X PUT localhost:8000/users/123 -H 'content-type: application/json' \
  -d '{"id":123,"name":"bob b","email":"someone-elses@coderco.io"}'

# delete, no token: 401
curl -i -X DELETE localhost:8000/users/123

# delete, wrong role: 403
curl -i -X DELETE localhost:8000/users/123 -H 'Authorization: Bearer viewer-token'

# delete, admin: 200
curl -i -X DELETE localhost:8000/users/123 -H 'Authorization: Bearer admin-token'

# delete all users, admin: 200
curl -i -X DELETE localhost:8000/users -H 'Authorization: Bearer admin-token'

# not found
curl -i localhost:8000/users/999
```

## Interactive docs

Swagger UI at `http://localhost:8000/docs`, ReDoc at `http://localhost:8000/redoc`.
