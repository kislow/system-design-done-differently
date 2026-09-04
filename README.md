# System Design, Done Differently

A practical system design series for DevOps, Platform, SRE, Infrastructure, SWE, and MLOps
engineers: build enough application-level understanding to reason about how systems work, before
reasoning about the infrastructure around them.

```text
Client → Service → Data Store
```

Throughout the series we build and evolve one running application, the **Deployment Request
Service**, one session at a time:

```text
Understand → Draw → Build → Run → Observe → Explain → Evolve
```

Each session commits a diagram, running code, and an observation that motivates the next change.
Nothing gets added ahead of an observed need: no database, cache, load balancer, queue, container,
or Kubernetes cluster shows up just because a typical diagram has one.

## Repository structure

- `app/`: the FastAPI service. See [`app/README.md`](app/README.md) to run it.
- `diagrams/`: architecture diagrams, one per session.
- `sessions/`: a short write-up per session, what we built, what we decided, what's next.
- `scripts/`: checks that prove a session's claim, rather than trusting it.
- `Dockerfile`, `docker-compose.yml`: containers for the API and Postgres.

## Sessions

| # | Focus | Notes |
|---|---|---|
| 1 | HLD: client, API, datastore, HTTP methods, status codes | [diagram](diagrams/session1-hla-method-req-res.png) |
| 2 | Session 1's HLD as a running FastAPI service, containerized, role-based auth on delete | [session-2](sessions/session-2.md), [app docs](app/README.md) |
| 3 | Durable state: Postgres on the request path as the source of truth | [session-3](sessions/session-3.md), [app docs](app/README.md) |
| 4 | Error contracts: 422 / 404 / 409 gates on `PUT`, 204 on success | [session-4](sessions/session-4.md), [app docs](app/README.md) |
| 5 | The first automated test: an independent check that a missing user is a 404 | [session-5](sessions/session-5.md), [app docs](app/README.md) |

## What comes next

There is no fixed session count or running order. Each session is motivated by a limitation the
previous one exposed, so what comes next depends on what breaks first. Publishing a numbered plan
would contradict the principle below.

Topics on the table, roughly in the order these constraints tend to surface:

- API lifecycle and correctness: validation, error contracts, duplicate handling
- automated tests and CI
- logging and metrics, and what "observable" actually requires
- latency and capacity estimation
- more than one API instance, and load balancing in front of them
- caching, and invalidating it
- queues, retries, and idempotency
- rate limiting
- orchestration with Kubernetes
- deliberate failure testing

## Core principle

> Infrastructure exists to support application flows. Understand the flow before designing the
> infrastructure around it.
