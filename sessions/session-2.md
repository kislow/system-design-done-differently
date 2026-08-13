# Session 2: from HLD to a running service

## Goal

Turn session 1's whiteboard HLD (`../diagrams/session1-hla-method-req-res.png`), client, API,
datastore, the HTTP method table, the status code table, into a running service students can
call.

## What we built

- FastAPI app (`../app/main.py`) implementing the methods from the session 1 diagram: `POST /users`,
  `GET/PUT/PATCH/DELETE /users/{id}`.
- Storage is a process-local in-memory dict, no datastore wired up yet, deliberately, per the
  root README's "one requirement at a time" pace.
- Status codes match the whiteboard's list where they apply today: 201 on create, 200 on
  read/update/delete, 400 on bad request (duplicate `id` on create, `id` mismatch on `PUT`), 404
  not found ("user not in DB", the diagram's own wording).
- Containerized the API (`../Dockerfile`) and stood up a Postgres container
  (`../docker-compose.yml`) as the datastore box from the diagram, running, but not yet called by
  the app. Wiring it up is a later session's topic.
- Added role-based auth on `DELETE` only: a bearer token maps to a role (in-memory table, not real
  auth), and only the `admin` role can delete a user. No/invalid token returns 401, wrong role
  returns 403. This is the answer to the diagram's own question next to 404, "what are we doing",
  by drawing the line between not authenticated (401), not authorized (403), and not found (404).

## Why these decisions

- **No DB wiring yet.** The datastore container exists so the topology matches the diagram, but
  wiring persistence in is scoped to its own future session rather than folded into this one.
- **Auth only on `DELETE`.** The ask this session was specifically "not all users/tokens should be
  able to delete", so read/write endpoints stay open for now, which keeps the change narrow and
  easy to reason about.
- **Tokens/roles are a hardcoded dict.** Same "process-local, no external service" stance as the
  user store, consistent with everything else being in-memory at this stage.

## Try it

See [`../app/README.md`](../app/README.md) for how to run it (Docker or local) and the full
endpoint/auth reference.

## Open questions for next session

- Should `PUT`/`PATCH` also require auth (e.g. only the owning user or an admin)?
- When do we wire the API to the Postgres container instead of the in-memory dict?
- Do we want a `role` claim decoded from a real token/JWT instead of a static token table?
