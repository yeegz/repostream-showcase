# ADR 0004: Event-time hourly aggregates with a per-partition watermark

**Status:** accepted, 25 Nov 2026 (revised the same day after the baseline experiment)

## Decision
Aggregates are keyed by event time (the hour in `created_at`), so out-of-order events still land in the right hour. A watermark marks which hours are "final": `min over assigned partitions of (max event time seen in that partition) - allowed lateness (2 h)`. Events older than the watermark are still counted, and also recorded in `late_events`, so a consumer of the numbers knows a "final" hour changed.

## Revision
The first version used one maximum per worker. The baseline replay flagged 1,461 of 150,695 events as late although the source contains no late events: partitions are fetched at different speeds, so one fast partition pushed the watermark past events still waiting in a slower one. Taking the minimum across partitions (as Flink and Kafka Streams do) reduced that to tens. The remaining flags are real event-time skew created by replaying 24 h of events in about 40 s (2 h of event time is about 3 s of replay), not data problems.

## Consequences
- An idle partition would hold the watermark back forever; with a live source that needs an idle timeout. Not needed for replay, recorded as a limitation.
