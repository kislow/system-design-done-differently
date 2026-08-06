# System Design, Done Differently

A practical system design series for DevOps, Platform, SRE, Infrastructure, SWE, and MLOps engineers.

The goal of this series is not to turn infrastructure engineers into backend developers.

The goal is to build enough application-level understanding to reason about how systems actually work, how requests move through them, and why infrastructure components are introduced around them.

Before discussing Kubernetes, load balancers, caching, queues, scaling, or distributed systems, we first need to understand the application flow those components are supporting.

```text
Client → Service → Data Store
```

From there, the system evolves one requirement and one observed limitation at a time.

## What makes this series different

This is not a collection of disconnected system design diagrams.

Throughout the series, we build and evolve one running application: a **Deployment Request Service**.

Every session follows the same process:

```text
Understand → Draw → Build → Run → Observe → Explain → Evolve
```

Each session produces:

1. a diagram showing what we believe the system does;
2. running code or configuration showing what it actually does;
3. an observation or measurement explaining why the next change is needed;
4. a Git commit that becomes the starting point for the following session.

Technology is used to demonstrate concepts, not define them.

We do not add a database, cache, load balancer, queue, container, or Kubernetes cluster simply because a typical architecture diagram contains one. Each component must solve a requirement or limitation that we have already observed.

## What participants will learn

The series begins with the fundamentals of application communication:

- clients, APIs, services, and data stores;
- requests and responses;
- reads and writes;
- HTTP methods, paths, headers, query parameters, and request bodies;
- status codes and application behaviour;
- component and sequence diagrams.

Participants then build the first version of the Deployment Request Service using FastAPI and process-local memory. This creates a real system that can be run, tested, observed, and improved.

Across the later sessions, the same system gradually introduces:

- durable persistence;
- API lifecycle and correctness;
- automated testing and continuous integration;
- logs, request IDs, and metrics;
- latency, throughput, and capacity estimation;
- containers and configuration;
- PostgreSQL;
- multiple service instances;
- load balancing;
- rate limiting;
- caching;
- queues and workers;
- retries and idempotency;
- Kubernetes;
- failure testing and scaling.

The complete roadmap spans 16 sessions and deliberately defers advanced topics until the core foundations are understood.

## Core principle

> Infrastructure exists to support application flows. Before designing the infrastructure, we must understand the flow.

Participants are expected to explore the system, run commands, read small sections of code, draw diagrams, and explain what they observe. The purpose is system understanding, not framework expertise.

The structure will evolve as the running system becomes more capable.
