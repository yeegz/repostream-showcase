# repostream: engineering report

> Copied from the private source repository on 25 Nov 2026. File paths such as `src/...`, `bench/...` and `experiments/...` refer to that repository; the raw result files are in this repository's [results/](../results) folder.

25 November 2026. Everything here ran on one laptop: Apple M1 Pro (8 cores), 16 GB RAM, macOS, Docker through colima (a Linux VM), Python 3.12.16, Postgres 17.6, Redpanda 25.2.9, DuckDB 2.0.1, PyArrow 26. Every number links to the file that holds the raw result. Tables marked "generated" are rendered from those files by `experiments/tables.py`, not typed by hand.

**What kind of numbers these are.** Real data: GH Archive files as published. Replayed stream: those same events pushed through Redpanda at a fixed 4,000 messages/s, not a live feed. Synthetic: the fault injections, and the drops injected into the ML test set. Estimates: the cloud cost table. Nothing was deployed; there are no users.

## 1. Summary
- **Data:** 572 hourly files (1–24 Nov 2026, 2.77 GB compressed) plus 3 hours in the pre-October-2025 format. 4,831,018 events read, 4,830,912 accepted, 69 quarantined, 37 duplicates removed. 10 quality checks: 0 errors, 2 warnings that point at real upstream problems.
- **Two paths, one answer:** for a full day (150,695 events), the streamed result in Postgres equals the batch result on every (repo, hour, event type) key, in every experiment where no input was deliberately replaced, including consumer kills, a frozen database and a broker restart.
- **Bugs found by testing, then fixed:** a watermark that flagged 1,461 good events as late; a contract crash on malformed nested fields (found by property-based testing); three monitoring mistakes (self-reported lag that freezes with the process, a 60 s broker lag interval, an SLO rule that fired forever when idle).
- **Negative ML result:** a gradient-boosted volume model lost to "same as last hour". The kept monitor is persistence plus split-conformal intervals.

## 2. Data pipeline results
Batch path on the full dataset (`docs/results/runs/`):

| Step | Result |
| --- | --- |
| Fetch | 576 hours requested: 570 fetched + 2 already present, 4 not yet published (recorded as missing), 0 failed; 2,769,313,391 bytes in 284.9 s |
| Silver | 575 files, 4,831,018 lines: 4,830,912 valid, 69 quarantined (`repo_id_invalid`: ForkEvents with an empty `repo`), 37 in-file duplicates |
| Gold | 2,564,537 repo-day rows, 371,948 PRs with an observed open, 26 ecosystem days, 775 hourly capture rows |
| Quality | 10 checks; errors 0; warnings: hourly volume collapsed on 7 hours of 23 Nov; "new repos" zero on all 24 November days |

Batch throughput, repeated (generated from `results/bench/batch.json`):

<!-- TABLE:batch -->
| Job | Runs (wall s) | Median (s) | Peak RSS (MiB) |
| --- | --- | --- | --- |
| silver_force_6_workers | 20.11, 19.27, 17.3 | 19.27 | 356.9 |
| silver_force_1_worker | 80.94 | 80.94 | 388.4 |
| gold_full | 16.82, 17.03, 15.57 | 16.82 | 2227.9 |
<!-- /TABLE -->

What the data itself showed is in [results/data-findings.md](data-findings.md): the archive shrank by more than 20x since January 2025, capture swings by event type, GitHub's payload change silently removed one metric and made another (time-to-merge) biased.

## 3. Streaming and failure experiments
Setup: 3 consumer containers (512 MiB, 1 CPU each), a 6-partition topic, batches of 2,000, all of 2026-11-20 replayed at 4,000 msg/s (150,701 messages: 150,695 valid events + 6 real invalid records). After each run, `repostream reconcile` compares Postgres with the batch path key by key. Alerts are read from Prometheus's API during the run. Raw results: `results/experiments/*.json`; harness: `experiments/stream_faults.py`.

Generated:

<!-- TABLE:experiments -->
| Experiment | Fault injected | Sent | Caught up (s) | p50 / p99 latency (s) | Peak broker lag | DLQ | Late flagged | Alerts fired (s after start) | Stream = batch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | none | 150,701 | 39.9 | 0.69 / 4.13 | 3,860 | 6 | 8 | none | exact (131,181 keys) |
| consumer_kills | SIGKILL a consumer every 6 s, 6 times | 150,701 | 65.5 | 20.38 / 51.75 | 25,918 | 6 | 1,399 | ProcessingLatencySLOBurn 79.0 | exact (131,181 keys) |
| duplicates_and_reordering | 10% re-sent, shuffled in a 20,000-message window | 165,659 | 44.4 | 0.69 / 3.85 | 3,417 | 8 | 69,714 | none | exact (131,181 keys) |
| poison_messages | 1% replaced by malformed or invalid messages | 150,701 | 39.5 | 0.65 / 3.57 | 3,586 | 1,489 | 0 | DeadLetterRateHigh 46.7 | differs by 1,483 events = the 1,483 replaced |
| postgres_outage | `docker pause` Postgres for 45 s | 150,701 | 59.1 | 26.63 / 59.33 | 113,091 | 6 | 144 | ConsumerStalled 44.9, ConsumerLagHigh 59.1 | exact (131,181 keys) |
| broker_restart | restart Redpanda mid-stream | 150,701 | 39.6 | 0.70 / 4.48 | 4,555 | 6 | 11 | none | exact (131,181 keys) |
| slow_sink_backpressure | consumers sleep 2.5 s per 2,000-message batch | 150,701 | 82.4 | 22.23 / 58.84 | 76,956 | 6 | 920 | ProcessingLatencySLOBurn 50.8, ConsumerLagHigh 60.8 | exact (131,181 keys) |
<!-- /TABLE -->

Reading the table:
- "Latency" is produce-to-commit, estimated by Prometheus from histogram buckets (edges at 1, 2, 5, 10, 30, 60 s), so values between edges are interpolated.
- "Late flagged" events are still counted. They come from replaying 24 hours in about 40 seconds: 2 hours of event time pass in about 3 seconds, so small fetch-order differences between partitions cross the 2 h lateness bound. The source data has no late events.
- Kills: each kill hands that consumer's partitions to the others only after the 10 s session timeout, which is where the higher latency comes from. Nothing was lost or double counted.
- Duplicates: 14,958 extra copies were sent; none was counted twice. The DLQ holds 8 there because 2 of the 6 real invalid records were among the re-sent copies.
- Peak broker lag is Redpanda's own per-group measurement (sampled every 5 s), read from Prometheus for each run's consumer group.
- Alerts: the database freeze fired ConsumerStalled and ConsumerLagHigh; the slow sink fired the latency burn and the lag alert; poison fired DeadLetterRateHigh. Kills fired the latency burn (each kill leaves partitions unowned until the 10 s session timeout); the replica alert only went to "pending", because each replica was back within about 2 s, under its 15 s `for` window, which is the intended behaviour. The broker restart caused about 4.5 s p99 latency and no alert.
- The poison run replaces 1% of messages, so those events never reach the stream. The stream total plus the replaced count equals the batch total exactly, and every replaced message is in the DLQ.
- The experiments ran on the image built before two late changes (insert ordering against deadlocks, Debian security updates). The baseline was rerun on the final image: exact match again, caught up in 39.6 s (`results/experiments/final-image-check/`).
- Earlier runs of the same experiments, before the monitoring fixes, are kept in `results/experiments/superseded-2026-11-25/` together with the first baseline (`baseline-before-watermark-fix.json`), which shows the watermark bug.

Integration tests against Postgres (`tests/integration/`) cover the sink directly: redelivered batches add nothing, 8 concurrent writers with overlapping shuffled batches converge without deadlock, partitions are created safely under concurrency, and `EXPLAIN` shows partition pruning.

## 4. Database and storage measurements
Postgres serving queries with only the primary key vs with the indexes chosen from the API's access patterns. 300 calls per query, parameters drawn from real repos and dates with a fixed seed, identical for both runs, after a warm-up. Generated from `results/bench/pg_serving.json` (which also holds the `EXPLAIN (ANALYZE, BUFFERS)` output):

<!-- TABLE:pg -->
| Query | PK only p50 / p99 (ms) | With indexes p50 / p99 (ms) |
| --- | --- | --- |
| repo_history | 32.972 / 35.214 | 0.568 / 1.242 |
| repo_by_name | 250.258 / 297.206 | 0.559 / 1.051 |
| daily_top_stars | 11.506 / 37.674 | 0.492 / 1.087 |
| window_top_merged | 318.524 / 605.255 | 298.821 / 559.544 |

Table + index bytes: PK only 563,945,472; with indexes 766,427,136.
<!-- /TABLE -->

The 7-day leaderboard was the one query indexes did not fix. Its plan showed a hash aggregate over about 675k rows spilling to disk, so the first guess was memory. Generated from `results/bench/pg_window_query.json`:

<!-- TABLE:window -->
| Variant (100 random 7-day windows) | p50 (ms) | p95 (ms) |
| --- | --- | --- |
| A. indexes from table above | 271.17 | 441.74 |
| B. A + work_mem 128 MB | 269.4 | 405.98 |
| C. `prs_merged > 0` + partial covering index | 23.33 | 26.41 |

Same top-20 lists A vs B: True; A vs C: True. Partial index size: 11,034,624 bytes.
<!-- /TABLE -->

Raising `work_mem` removed the spill and changed nothing, so the spill was not the cost; reading and grouping every row of the week was. Skipping rows with zero merges (they cannot reach a top 20 by merges) with a partial covering index made it an index-only scan over about 81k rows. That index is now part of `serving.py`.

API load (`bench/api_load.py`, client and server on the same laptop). Generated from `results/bench/api_load.json`:

<!-- TABLE:api -->
4,000 requests, 8 closed-loop clients, 11.62 s (344 req/s), status codes {'200': 4000}.

| Route | Requests | p50 (ms) | p99 (ms) |
| --- | --- | --- | --- |
| leaderboard | 734 | 3.8 | 10.63 |
| by_name | 812 | 3.69 | 12.44 |
| repo_daily | 1,660 | 3.72 | 11.36 |
| week_merged | 794 | 98.31 | 178.54 |
<!-- /TABLE -->

The weekly route costs about 24 ms when run alone (index-only scan); under 8 concurrent clients it queues for CPU in the Docker VM with the other requests, hence the higher figures above. The first version of that endpoint also aggregated `repo_name`, which forced heap reads; it now ranks inside the index and fetches names for the top rows only.

Row store vs column store, same 2.56M-row table, 20 timed runs after 3 warm-ups. DuckDB runs in-process; Postgres is reached over a socket into the Docker VM, which is part of the real trade-off. Generated from `results/bench/engines.json`:

<!-- TABLE:engines -->
| Query | DuckDB p50 (ms) | Postgres p50 (ms) |
| --- | --- | --- |
| ecosystem_rollup | 1.949 | 119.101 |
| window_top_stars | 24.592 | 1489.866 |
| repo_history | 3.889 | 0.561 |

Storage, one day (150,695 rows, 17 columns):

| Format | Bytes | vs Parquet zstd |
| --- | --- | --- |
| raw_archive_gz_all_fields | 121,019,375 | 22.5x |
| ndjson_gzip | 6,882,119 | 1.3x |
| csv | 23,332,422 | 4.3x |
| parquet_snappy | 7,183,756 | 1.3x |
| parquet_zstd | 5,372,335 | 1.0x |
| postgres_heap | 23,699,456 | 4.4x |
| postgres_heap_plus_pk_index | 27,107,328 | 5.0x |
<!-- /TABLE -->

## 5. MLOps
Task: flag hours whose captured volume is implausibly low (a partially captured file looks like a valid one). Data: hourly counts for two event-id families, 1–24 Nov 2026. Split by time: train to 17 Nov, validation 18–20 Nov, test 21–24 Nov (111 family-hours). Full output: `results/ml/volume-monitor.json`; MLflow run in `results/ml/mlflow.db`.

| Model | Test MAE, log scale | 90% interval coverage |
| --- | --- | --- |
| Persistence (last hour) | **0.130** | n/a |
| Same hour yesterday | 0.509 | n/a |
| Trailing 24 h median | 0.314 | n/a |
| Gradient boosting, level target, quantile intervals | 0.353 | 0.450 |
| Persistence + split-conformal band | 0.130 | 0.892 |
| Gradient boosting on the change from last hour + conformal band | 0.151 | 0.892 |

The boosted level model is worse than persistence by 0.224 (95% block-bootstrap interval over days 0.072 to 0.430). The test days contain a capture regime change (population stability index between training and test up to 7.3 on the rolling-std feature, far above the usual 0.25 alarm level).

Detection, with synthetic drops injected into 20 of the 111 test hours (sensitivity to drops of a known size, not real-world precision):

| Detector | Recall at 30% / 50% / 80% drop | False-positive rate on clean hours |
| --- | --- | --- |
| Persistence + conformal (champion, v1) | 0.90 / 1.00 / 1.00 | 0.066 |
| Boosted change model + conformal | 0.90 / 1.00 / 1.00 | 0.044 |
| Boosted level model + quantile band | 0.35 / 0.55 / 0.95 | 0.154 |

The two conformal detectors differ by about 2 false alarms in about 90 clean hours, which is within noise at this sample size, so the simpler one is the champion. It is versioned in `models/volume-monitor/registry.json` with its data fingerprint; `repostream ml promote|rollback|score` manage it, and scoring wrote 746 scored hours with 67 flagged to `gold.volume_flags`. The flag rate (9%) is above the 5% one would expect from a symmetric 90% band, which again reflects drift.

## 6. Infrastructure, CI, security
- Compose stack with health checks, pinned images, localhost-only ports, Docker secrets, and a hardened consumer image (non-root, read-only filesystem, no capabilities). `make up` is the whole setup.
- CI (`.github/workflows/ci.yml`): ruff, mypy, unit tests, pip-audit, integration tests on a Postgres service container, image build with Trivy image and config scans, Terraform fmt + validate. All four jobs passed on GitHub Actions on 25 Nov 2026 (run 45547044772, commit after the first run failed on three CI-setup mistakes: pip-audit tripping on the project package itself, the integration job collecting ML-dependent unit tests, and a non-existent action tag).
- Terraform for Google Cloud: validated and Trivy-clean, **never applied**. Design and cost estimate (roughly USD 55–65 a month, mostly the database) in [cloud.md](cloud.md).
- Security review and known gaps: [security.md](security.md). `pip-audit`: no known vulnerabilities on 25 Nov 2026.
- Prometheus alert rules checked with `promtool`; Grafana dashboard provisioned from the repo.

## 7. Tests
48 tests, all passing on 25 Nov 2026 (`make test`: 40 unit; `make it`: 8 integration against the compose Postgres). Parametrized cases count once per case.

| File | Tests | What they prove |
| --- | --- | --- |
| `unit/test_contracts.py` | 17 | both payload eras normalize to one vocabulary (real anonymized fixtures); 8 contract violations each give the right reason; two Hypothesis property tests (one found a real crash) |
| `unit/test_fetch.py` | 10 | against a local misbehaving HTTP server: 503, short bodies, flipped bytes and missing gzip trailers are retried; persistent corruption never publishes a file; 404 is not retried; re-runs skip; tampering is detected |
| `unit/test_batch_layers.py` | 9 | line accounting, late rows land in their own date, forced re-runs are byte-identical, stale outputs are removed, cross-file dedup, incremental gold rebuilds only touched dates, PR censoring, quality checks fail when a file disappears |
| `unit/test_ml_monitor.py` | 4 | conformal rank formula, no feature reads the current hour, PSI detects a shift, promote/rollback |
| `integration/test_sink.py` | 8 | redelivery adds nothing, partial overlap counts only new rows, 8 concurrent overlapping writers converge (failed 3 of 3 before the lock-order fix), late flags, partition creation and pruning, idempotent migrations |

Not covered by automated tests: the streaming worker loop as a whole (covered by the experiments instead), the API (smoke and load tested by hand with `bench/api_load.py`), and the Terraform (validate and scan only).

## 8. What did not work
1. **Per-worker watermark.** 1,461 false late flags in a clean run. Fixed with a per-partition minimum (ADR 0004).
2. **Self-reported lag.** Frozen with the process during the database pause, so no alert fired. Fixed by alerting on broker lag and on stalled commits (ADR 0005).
3. **Broker lag collected every 60 s** by default: alerts saw stale values. Set to 5 s.
4. **SLO burn rule fired forever on an idle system** (0/0 treated as 100% slow). Rewritten to evaluate only while events flow.
5. **Experiment harness credited stale alerts** from the previous run to the next fault, and once included its own waiting time in "caught up" times. Fixed; all experiments rerun from a clean state.
6. **Level forecasting model.** Lost to persistence (section 5).
7. **Time-to-merge from current archive data.** Not usable per repository (data findings, section 2).

## 9. Limitations
- One machine. Consumers, broker and database share 8 cores, so absolute throughput says little about a real cluster; the relative results (exact reconciliation under faults, recovery behaviour, index and engine comparisons) are what carry over.
- The stream is a replay at a fixed rate, not a live feed. Idle partitions, live late data and long-running operation are not tested.
- GH Archive is a sample of GitHub, and since Oct 2025 a small and varying one. Every metric means "as captured by GH Archive".
- Latency percentiles come from histogram buckets, not exact per-event timings.
- The ML test set is 111 family-hours and the detection labels are synthetic.
- Cloud: design and cost estimate only. Backups were tested locally only: on 25 Nov a dump of the three serving tables (70.7 MB, 6 s) restored into a new database in 13 s with identical row counts and sums. Point-in-time recovery is designed (Cloud SQL), not tested.
- Built with an AI assistant. What Yousof can explain unaided is tracked in the private repository's study guide.
