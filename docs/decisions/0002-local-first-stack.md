# ADR 0002: DuckDB + Parquet for batch, Postgres for serving, Redpanda for the stream

**Status:** accepted, 25 Nov 2026

## Decision
| Need | Choice | Alternatives considered |
| --- | --- | --- |
| Raw landing | The archive's own `.json.gz` files, unchanged, plus a sha256 manifest | Re-encoding raw to Parquet "bronze": duplicates bytes without adding information |
| Validated layer | Parquet (zstd), partitioned by event date, one file per source hour | Delta/Iceberg: ACID tables and time travel, but more machinery than one writer per path needs |
| Batch transforms | DuckDB SQL over Parquet | Spark (cluster overhead for ~5M rows), Polars (fine, but SQL is easier to review and test), dbt (adds lineage docs; deferred, see below) |
| Serving | Postgres 17 with indexes chosen from the API's queries | Serving straight from DuckDB: one writer at a time, no concurrent readers during a rebuild |
| Stream | Redpanda (Kafka API) in one container | Apache Kafka (JVM and KRaft setup, same API), NATS/Redis Streams (different semantics from what most data teams run) |
| Orchestration | A small CLI with explicit checkpoints, run by make/cron, or Cloud Scheduler in the cloud design | Dagster or Airflow: real benefits (asset lineage UI, retries, backfill UI) that matter more with many pipelines and people |

## Why this shape
The workload is a few GB per month on one laptop. Every component runs locally with no paid service. Column store for scans, row store for point lookups is measured, not assumed (docs/results/bench/engines.json).

## Deferred
- dbt for the gold models (tests and lineage graph). The SQL in `gold.py` is already split into one statement per model, so porting is mechanical.
- An orchestrator, once there is more than one pipeline.
