# Deployment Request Service

The running service for this series. An in-memory, FastAPI CRUD API for users, implementing
session 1's HLD (`../diagrams/session1-hla-method-req-res.png`): client → API → datastore.

Session write-ups live in `../sessions/`: start with
[`../sessions/session-2.md`](../sessions/session-2.md) for what this version of the service does
and why.

## Requirements

- Docker + Docker Compose (recommended), or
- Python 3.13+

## Run with Docker (recommended)

```bash
docker compose up --build
```

The API is on `http://localhost:8000`. A Postgres container also comes up on `localhost:5432`:
it's the datastore box from the diagram, but the app doesn't read/write to it yet; storage is
still the in-memory dict described below. Persistence lands in a later session.

Stop and remove both containers:

```bash
docker compose down
```

## Run locally without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Data model

Storage is a process-local in-memory dict; restarting the service clears all users.

```json
{"id": 123, "name": "bob", "email": "bob@coderco.io"}
```

## Endpoints

| Method | Path          | Auth         | Body                          | Success   | Errors                                    |
|--------|---------------|--------------|--------------------------------|-----------|--------------------------------------------|
| POST   | `/users`      | none         | full user                     | 201       | 400 if `id` already exists                 |
| GET    | `/users/{id}` | none         | none                           | 200       | 404 if not found                           |
| PUT    | `/users/{id}` | none         | full user, `id` must match path | 200     | 400 on id mismatch, 404 if not found        |
| PATCH  | `/users/{id}` | none         | partial `{name?, email?}`     | 200       | 404 if not found                           |
| DELETE | `/users/{id}` | admin token  | none                           | 200       | 401 no/invalid token, 403 wrong role, 404 if not found |

## Auth

`DELETE` requires `Authorization: Bearer <token>`. The token → role mapping is a hardcoded
in-memory table for the exercise, not real auth:

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
curl localhost:8000/users/123

# partial update
curl -X PATCH localhost:8000/users/123 -H 'content-type: application/json' \
  -d '{"email":"new@coderco.io"}'

# full overwrite
curl -X PUT localhost:8000/users/123 -H 'content-type: application/json' \
  -d '{"id":123,"name":"bob b","email":"bob@coderco.io"}'

# delete, no token: 401
curl -i -X DELETE localhost:8000/users/123

# delete, wrong role: 403
curl -i -X DELETE localhost:8000/users/123 -H 'Authorization: Bearer viewer-token'

# delete, admin: 200
curl -i -X DELETE localhost:8000/users/123 -H 'Authorization: Bearer admin-token'

# not found
curl -i localhost:8000/users/999
```

## Interactive docs

Swagger UI at `http://localhost:8000/docs`, ReDoc at `http://localhost:8000/redoc`.
