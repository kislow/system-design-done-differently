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

## Session 7.1: from concurrency concepts to measured load

Run the standalone Python example (no dependencies required):

```bash
python3 scripts/concurrency-vs-parallelism.py
```

It compares synchronous waiting with asynchronous concurrency on one thread, then compares
sequential CPU work with parallel work in separate processes. See the
[session 7.1 write-up](sessions/session-7.1.md) for what the measurements prove and, importantly,
what they do not say about the API's capacity yet.

The follow-on exercise applies those terms to the running API:

```bash
python tools/load_test.py \
  --url http://localhost:8000/users/123 \
  --requests 300 \
  --concurrency 10
```

See the [load-test record](sessions/session-7.1-measuring-under-load.md) for the observed RPS,
p50/p95, timeout behaviour, and the connection-pool bottleneck that led into Session 8.

## Sessions

| # | Focus | Notes |
|---|---|---|
| 1 | HLD: client, API, datastore, HTTP methods, status codes | [diagram](diagrams/session1-hla-method-req-res.png) |
| 2 | Session 1's HLD as a running FastAPI service, containerized, role-based auth on delete | [session-2](sessions/session-2.md), [app docs](app/README.md) |
| 3 | Durable state: Postgres on the request path as the source of truth | [session-3](sessions/session-3.md), [app docs](app/README.md) |
| 4 | Error contracts: 422 / 404 / 409 gates on `PUT`, 204 on success | [session-4](sessions/session-4.md), [app docs](app/README.md) |
| 5 | The first automated test: an independent check that a missing user is a 404 | [session-5](sessions/session-5.md), [app docs](app/README.md) |
| 6.1 | Observability, part 1: why "which request" is hard at scale, and request/correlation IDs | [session-6.1](sessions/session-6.1.md), [diagram](diagrams/session6-see-what-service-is-doing.png) |
| 6.2 | Payload security: does the request need to contain all of it? hash vs. tokenise vs. encrypt, mask before output | [session-6.2](sessions/session-6.2.md), [diagram](diagrams/session6.2-payload-security-flow.png) |
| 7.1 | Measuring before scaling: concurrency vs. parallelism, then RPS, p50/p95, timeouts, and the connection-pool limit under real load | [concepts](sessions/session-7.1.md), [demo](scripts/concurrency-vs-parallelism.py), [load-test record](sessions/session-7.1-measuring-under-load.md), [tool](tools/load_test.py) |
| 8 | Replaceability before replication: percentile caveats, durable state, liveness, and readiness | [session-8](sessions/session-8.md), [percentile recap](diagrams/session8-percentiles-recap.png), [failure scenario](diagrams/session8-instance-failure-and-p50.png) |

## What comes next

There is no fixed session count or running order. Each session is motivated by a limitation the
previous one exposed, so what comes next depends on what breaks first. Publishing a numbered plan
would contradict the principle below.

Topics on the table, roughly in the order these constraints tend to surface:

- API lifecycle and correctness: validation, error contracts, duplicate handling
- automated tests and CI
- logging and metrics, and what "observable" actually requires
- load testing, latency, and capacity estimation
- more than one API instance, and load balancing in front of them
- caching, and invalidating it
- queues, retries, and idempotency
- rate limiting
- orchestration with Kubernetes
- deliberate failure testing

## Core principle

> Infrastructure exists to support application flows. Understand the flow before designing the
> infrastructure around it.
