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
- `Dockerfile`, `docker-compose.yml`: containers for the API and, from session 2, a Postgres datastore.

## Sessions

| # | Focus | Notes |
|---|---|---|
| 1 | HLD: client, API, datastore, HTTP methods, status codes | [diagram](diagrams/session1-hla-method-req-res.png) |
| 2 | Session 1's HLD as a running FastAPI service, containerized, role-based auth on delete | [session-2](sessions/session-2.md), [app docs](app/README.md) |

## Roadmap

Participants start with the fundamentals of application communication (clients, APIs, requests
and responses, HTTP methods, status codes, component and sequence diagrams), then build the first
version of the service using FastAPI and process-local memory. Later sessions introduce durable
persistence, API lifecycle and correctness, automated testing and CI, logging and metrics, latency
and capacity estimation, containers, PostgreSQL, multiple instances, load balancing, rate
limiting, caching, queues, retries and idempotency, Kubernetes, and failure testing, across 16
sessions total.

## Core principle

> Infrastructure exists to support application flows. Understand the flow before designing the
> infrastructure around it.
