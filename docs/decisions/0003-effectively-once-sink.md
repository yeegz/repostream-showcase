# ADR 0003: At-least-once delivery + idempotent sink, not Kafka transactions

**Status:** accepted, 25 Nov 2026

## Context
Consumers write to Postgres, which is outside Kafka. Kafka's exactly-once (transactions plus `read_committed`) covers Kafka-to-Kafka pipelines; it cannot make a Postgres commit and an offset commit atomic.

## Decision
- Commit offsets only after the Postgres transaction commits (at-least-once).
- Make the sink idempotent: `INSERT ... ON CONFLICT (event_id, created_at) DO NOTHING RETURNING`, and increment the hourly aggregate only from the returned (newly inserted) rows, in the same transaction.

## Alternatives
- Store offsets in Postgres in the same transaction and seek on assignment. Also correct; it gives exactly-once without needing a natural key. Rejected because events already carry a unique id, and dedup on the id also absorbs duplicates the *producer* sends, which offset storage would not.
- Aggregate in the consumer's memory and flush periodically: fewer writes, but a crash loses the buffer or double-counts it.

## Consequences
- A redelivered message costs one wasted insert attempt. Measured: the `consumer_kills` and `duplicates_and_reordering` experiments reconcile exactly against the batch path.
- The `events` table is partitioned by `created_at`, so its unique key must include it. That is safe because an event's `created_at` never changes.
- Both statements take locks in key order: event rows are inserted `ORDER BY event_id, created_at` and aggregate upserts sort their keys. The first version sorted only the aggregate keys; an integration test with 8 concurrent writers on overlapping ids deadlocked on the `events` unique index (3 of 3 runs) until the insert was ordered too (0 of 3 after). In the consumer a deadlock is also retried as a transient error, so this was a liveness problem, not a correctness one.
