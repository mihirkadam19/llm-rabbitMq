# Asynchronous LLM Tailoring Platform

A backend that takes a job description and a resume and returns a tailored resume and cover letter from an LLM. Model calls are slow, costly and failure prone, so the system accepts work instantly, runs it in the background and lets each tier scale on its own.

## Architecture

```
   Client ──── login ────▶ Keycloak
     │                        │ public keys
     │ bearer token           ▼
     ▼                ┌────────────────┐
┌──────────────────┐  │                │      ┌─────────────┐
│ Ingestion Service│ ───────────────────────▶ │  Postgres   │
│ token and tenant │ ◀─────────────────────── │ job state   │
│ check, stateless │                          │ checkpoints │
└────────┬─────────┘                          └──────▲──────┘
         │ publish job                               │ status, result, graph state
         ▼                                           │
   ┌───────────┐   consume    ┌───────────────┐      │      ┌──────────────┐
   │ RabbitMQ  │ ───────────▶ │  LLM Worker   │ ─────┴────▶ │ LLM Provider │
   └───────────┘              │ async, graph  │             └──────────────┘
                              └───────────────┘
```

Every piece runs as its own container and can be replaced or multiplied without touching the others.

## Components

**Ingestion service.** The only entry point for clients. Middleware verifies the bearer token before any route runs. The service then records the job as queued, publishes it to the broker and returns a request identifier. It keeps no state, so any replica can serve any request.

**Keycloak.** The identity provider. It issues signed tokens that carry a tenant claim. The ingestion service checks the signature, issuer, audience and expiry against Keycloak's public keys and rejects any token whose tenant differs from the tenant the deployment serves. Routes sit under a tenant specific URL prefix.

**RabbitMQ.** A durable work queue. Messages survive a broker restart and are acknowledged only after the result is stored. If a worker dies mid job, the broker redelivers the message. A burst of traffic becomes a longer queue instead of an overloaded model tier.

**LLM worker.** An async consumer that runs many jobs at once on one event loop. Each job runs through a LangGraph workflow with two nodes, one for the resume and one for the cover letter. A conditional edge skips the cover letter when the user opts out. Nodes carry a bounded retry policy, and the model client, database writes and checkpointer are all non blocking.

**Postgres.** One store with two roles. It holds the status and result of each job, and it holds the graph checkpoints that LangGraph saves after every node. The queue answers what work remains, and the database answers what happened to a given request.

## Request lifecycle

1. The client logs in at Keycloak and receives a token.
2. The client submits a job with the token and gets a request identifier within milliseconds.
3. The ingestion service stores the job as queued and publishes it.
4. A worker takes the message, marks the job processing and runs the graph, saving a checkpoint after each node.
5. The worker stores the result, marks the job completed and acknowledges the message. A failure is recorded as failed with the error.
6. The client polls with its identifier until the job is complete.

## Reliability

Delivery is at least once, so a job can run twice if a worker crashes after finishing but before acknowledging. Status updates are plain overwrites, which keeps a repeat harmless. Transient provider errors are retried inside the graph with a bounded number of attempts. Jobs that fail permanently are rejected without requeue and recorded as failed, so a poison message never blocks consumers. Truncated model output is treated as a failure and never stored as a result.

## Scaling

Each tier scales on its own signal.

* **Ingestion** is stateless and scales horizontally behind a load balancer.
* **Workers** are competing consumers on one queue, so adding workers adds throughput with no coordination. They spend almost all their time waiting on the network, so queue depth is the right autoscaling signal and CPU is not.
* **Concurrency per worker** is set by the broker prefetch count. Throughput equals workers multiplied by concurrency per worker, divided by average job duration.
* **The provider is the real ceiling.** Rate limits and token budgets are reached long before infrastructure limits, so the maximum worker count is capped by the provider.
* **Postgres** takes small writes bounded by job count. Polling is the read hot spot, and the answers are caching in flight status, read replicas and a connection pooler.

## Tenancy

Isolation is enforced at the edge. The tenant comes from the verified token and never from the request body, and every route lives under the tenant prefix. A deployment serves one tenant today. The path to shared deployments is a queue per tenant for backlog isolation, plus a tenant column on every job row with all reads filtered by it.

## Roadmap

* Resume a failed job from its last checkpoint instead of from the start
* Dead letter queue with replay tooling
* Transactional outbox to close the gap between writing the record and publishing the message
* Queue depth based autoscaling for workers
* Shared rate limiting against the provider
* Server pushed updates in place of polling
* Queue per tenant and a shared multi tenant deployment
