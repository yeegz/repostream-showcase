# ADR 0005: Measure lag from the broker and alert on stalled commits

**Status:** accepted, 25 Nov 2026, after the `postgres_outage` experiment

## Context
The first alert set used `repostream_consumer_lag_messages`, a gauge each consumer updates in its poll loop. During a 45 s `docker pause` of Postgres, the consumers sat inside a query that never returned (a frozen server sends no error), so the gauge stopped updating and neither ConsumerLagHigh nor SinkErrors fired. The data was fine (exact reconciliation), but nobody would have been told.

## Decision
- Lag alerts use the broker's own metric, `redpanda_kafka_consumer_group_lag_sum`, with the collection interval lowered from 60 s to 5 s (the default made the second run's lag look like 46,701 when it was about twice that).
- New alert ConsumerStalled: the time since the newest offset commit across consumers is over 20 s while the broker reports lag. The commit timestamp gauge is served by the metrics thread, which keeps answering scrapes while the main loop is stuck.
- Sink connections get `statement_timeout=15s` and TCP keepalives, which turn lock waits and dead peers into retried errors. They cannot help with a frozen server process; the stall alert covers that case.

## Result
Rerun: ConsumerStalled fired 40.7 s after the experiment's alert watch started (the pause began earlier), and the run still reconciled exactly.
