# Asynchronous LLM Tailoring Platform

A backend platform that takes a job description and a resume and produces a tailored resume and cover letter using a large language model. It is built as an asynchronous, queue driven system so that slow, costly and failure prone model calls never block the API, never lose work and scale independently of the rest of the stack.

## The problem

An LLM call is unlike a typical backend dependency. It takes many seconds, its latency swings with output length, it is rate limited and billed per token, and it fails in unusual ways such as truncated output, malformed structure and transient capacity errors. Holding a web request open for the whole call wastes server capacity, collides with gateway and browser timeouts, and loses the work if the connection drops. The platform treats every request as a background job and separates accepting work from doing work.

## Design goals

* Acknowledge every request in milliseconds regardless of model latency.
* Never lose an accepted job when a component crashes or restarts.
* Scale the API tier and the model tier independently, each on its own signal.
* Keep the model provider replaceable and its cost observable.
* Leave room for richer agent workflows without redesigning the surrounding system.

## Architecture

```
   Client
     │  submit and poll
     ▼
┌──────────────────────┐        ┌────────────┐
│  Ingestion Service   │ ─────▶ │  Postgres  │
│  stateless and fast  │ ◀───── │  job state │
└──────────┬───────────┘        └─────▲──────┘
           │ publish job              │ status and result
           ▼                          │
     ┌───────────┐  consume    ┌──────┴───────┐       ┌──────────────┐
     │ RabbitMQ  │ ──────────▶ │  LLM Worker  │ ────▶ │ LLM Provider │
     └───────────┘             └──────────────┘       └──────────────┘
```

Four runtime pieces cooperate. The ingestion service is the only thing clients talk to. RabbitMQ carries jobs between the two halves of the system. The LLM worker does the slow work. Postgres holds the state of every job and is the single source of truth for what a client sees. Each piece ships as its own container, so it can be replaced, restarted or multiplied without touching the others.

## Components

**Ingestion service.** It validates input, mints a unique request identifier, records the job as queued, publishes it, and returns immediately. It holds no state of its own, so any replica can serve any request and a load balancer can spread traffic freely. The record is written before the message is published, so a client that polls right away always finds its job.

**Message broker.** RabbitMQ serves as the work queue. The queue and its messages are durable, so a broker restart does not erase pending jobs. Workers acknowledge a message only after the job has finished and its result is stored. If a worker dies mid job, the broker notices the dropped connection and hands the message to another worker. The broker also acts as a shock absorber, because a burst of submissions becomes a longer queue instead of an overloaded model tier.

**LLM worker.** Each worker consumes one job at a time and runs it through a graph based workflow with a bounded retry policy. The graph currently tailors the resume and the cover letter according to the request flags. The graph abstraction is deliberate. It supplies retry handling today and lets the workflow grow into parallel branches, review loops and tool calls without changing the queueing or storage design around it. The worker also guards against truncated model output, so a half finished document is treated as a failure and never stored as a success.

**State store.** Postgres keeps one row per job with a status that moves through queued, processing, completed and failed, plus the result or the error. Separating state from transport is a core decision. The queue answers what work remains. The database answers what happened to a given request. A message that has been acknowledged is gone from the broker, so without the database no client could ever retrieve a result.

## Request lifecycle

1. The client submits a job and receives a request identifier within milliseconds.
2. The ingestion service stores the job as queued and publishes a message carrying the identifier and payload.
3. A free worker takes the message, marks the job as processing and calls the model.
4. On success the worker stores the result, marks the job completed and acknowledges the message.
5. On failure the worker records the error and marks the job failed.
6. The client polls with its identifier and reads the current status and, once ready, the result.

## Reliability

Delivery is at least once. A job can run twice if a worker crashes after finishing but before acknowledging. Status updates are plain overwrites, so a repeat is harmless to correctness, and a status check before starting work keeps repeated delivery from spending tokens twice.

Transient provider errors are retried inside the worker with a bounded number of attempts, so a brief provider hiccup stays invisible to users and a persistent failure cannot loop forever. Jobs that fail permanently are rejected from the queue and recorded as failed with the error, which keeps a poison message from ever blocking the consumers. Routing rejected messages to a dead letter queue with replay tooling is the planned next step for operations.

Writing the record and publishing the message are two separate operations. The narrow window between them is closed with a transactional outbox, where the message is written in the same database transaction as the record and relayed to the broker by a separate process. This is on the roadmap.

## Scaling

Every tier scales on its own signal, which is the main payoff of the design.

**Ingestion tier.** It is stateless and cheap per request, so it scales horizontally behind a load balancer. The first limit to appear is connection churn, which is solved with long lived broker channels and pooled database connections.

**Broker tier.** Queue depth and the age of the oldest message are the key health signals. A single queue on a single node is plenty for early traffic. Beyond that the path is a clustered broker with replicated queues for availability, then sharding work across several queues for throughput. A managed queue service is a realistic substitute because the platform needs only simple work queue semantics.

**Worker tier.** Workers are competing consumers on one queue, so adding workers adds throughput with no coordination. They spend nearly all their time waiting on the network, so CPU is a poor autoscaling signal and queue depth is the right one. A useful sizing rule is that throughput equals workers multiplied by concurrency per worker, divided by average job duration. With a 30 second average job and 10 concurrent jobs per worker, one worker clears about 20 jobs a minute and 10 workers clear about 200. Fetching one message at a time keeps work fairly distributed when job durations vary, and concurrency inside a worker is raised through async or threaded execution once utilisation matters more than fairness.

**The provider is the real ceiling.** Adding workers eventually hits provider rate limits and token budgets long before it hits infrastructure limits. Operating at scale calls for a global concurrency cap, a token bucket shared across workers, backoff on rate limit responses, and fair sharing so one heavy user cannot starve the rest. Priority queues let interactive work jump ahead of bulk work. Cost grows linearly with traffic, so per job token accounting is part of the design.

**Back pressure.** When the queue grows past a threshold the ingestion service can slow intake, return a retry later response, or shed low priority work. This keeps latency promises honest instead of letting the backlog grow without bound.

**Database tier.** Writes are small and bounded by job count. Polling is the read hot spot, since many clients ask repeatedly about few rows. The short term answers are caching the status of in flight jobs, adding read replicas and fronting Postgres with a connection pooler. The structural answer is replacing polling with server pushed updates, while keeping the database as the record clients can recover from after a disconnect. Old rows are archived or partitioned by time to keep the hot table small.

## Observability

Every log line and metric carries the request identifier, so one job can be followed across the ingestion service, the broker and the worker. The metrics that matter are queue depth, oldest message age, job latency percentiles, failure rate by cause, retry counts, and tokens and cost per job. Alerts belong on a growing backlog and a rising failure rate, since those are the earliest signs of a provider problem or a bad deploy.

## Security and data handling

Resumes contain personal data, so the platform assumes encryption in transit and at rest, no payload content in logs, and a retention policy that deletes stored results after a defined period. Provider keys live in a secret manager and reach only the worker tier. Authentication, authorization and per user quotas sit at the ingestion edge, which also gives a natural place to enforce the rate limits described above.

## Key decisions and tradeoffs

A queue was chosen over a synchronous call because model latency is long and variable, traffic is bursty, and retries must not depend on a client staying connected. RabbitMQ was chosen over a log based broker because the workload is a classic task queue that needs per message acknowledgement and simple redelivery, not replay of an event history. Polling was chosen over push for the first release because it needs no extra infrastructure, with the cost being read load and a small delay. A graph workflow was chosen for the worker so complexity can grow inside the worker while the outer system stays unchanged.

## Roadmap

In order of value, the next steps are a transactional outbox, a dead letter queue with replay tooling, queue depth based autoscaling for workers, shared rate limiting against the provider, server pushed updates in place of polling, parallel graph branches so the resume and the cover letter are generated concurrently, authentication with per user quotas, and a managed broker for high availability.
