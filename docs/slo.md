# Service levels

These SLOs describe the local replay system and the cloud design. Nothing here serves production users; the numbers are targets to alert and test against, and the "measured" column comes from the experiments in `results/experiments/`.

| SLI | Definition | SLO | Measured (local, 3 consumers, 4,000 msg/s replay) |
| --- | --- | --- | --- |
| Processing latency | Share of events committed to Postgres within 5 s of being produced (`repostream_event_processing_lag_seconds`) | 99% over 30 days | baseline p99 about 4 s (Prometheus histogram estimate, bucket edges at 2 s and 5 s) |
| Correctness | Replay windows whose stream counts equal the batch counts on every (repo, hour, type) key (`repostream reconcile`) | 100% | 7 of 7 runs where no input was replaced; the poison run differs by exactly the 1,483 replaced messages |
| Dead letters | Share of consumed messages sent to the DLQ | under 0.1% | 6 of 150,701 (0.004%) on a clean day: real archive records with an empty `repo` |
| Batch freshness | Age of the newest complete hour in gold | under 3 h | quality check `freshness_hours` |
| Batch quality | Error-severity quality checks failing | 0 per run | 0 of 10 on 4.83M events |

## Alerts and why they exist
| Alert | Fires when | Runbook |
| --- | --- | --- |
| ConsumerReplicasBelowDesired | fewer than 3 consumer replicas scrape for 15 s | runbooks/consumer-down.md |
| ConsumerLagHigh | broker-measured group lag over 50,000 for 30 s | runbooks/consumer-lag.md |
| ConsumerStalled | no offset commit for 20 s while the broker reports lag | runbooks/postgres-unavailable.md |
| SinkErrors | any database write errors in the last minute | runbooks/postgres-unavailable.md |
| DeadLetterRateHigh | over 0.1% of messages dead-lettered for 30 s | runbooks/dead-letters.md |
| ProcessingLatencySLOBurn | the 5 s latency SLO burns at 14.4x (2% of a 30-day budget in an hour) | runbooks/consumer-lag.md |

The burn-rate rule follows the multiwindow approach in Google's SRE Workbook (chapter "Alerting on SLOs"), simplified to one window because experiments last minutes, not days.
