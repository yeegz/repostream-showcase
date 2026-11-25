# Security review

Scope: this repository's code, containers, local stack and Terraform design. Reviewed 25 Nov 2026 by the author with automated scanners. Not an external audit or penetration test.

| Area | What is in place | Evidence |
| --- | --- | --- |
| Secrets | Local passwords generated randomly (`make secrets`), stored in git-ignored files with mode 600, passed to containers as Docker secrets (files, not env vars). Cloud design: Secret Manager mounted as a file. No secret appears in logs: the DSN is built in memory and never printed. | `infra/compose.yaml`, `config.py`; `git ls-files infra/secrets` lists only `.gitkeep` |
| Network exposure | Every published port binds to 127.0.0.1. Consumers publish no ports; Prometheus reaches them on the internal Docker network. The API binds to 127.0.0.1. Cloud SQL design has no public IP and requires TLS. | `compose.yaml`, `cli.py serve`, `main.tf` |
| SQL injection | All values are bound parameters. Identifiers that must be in SQL text (table names in `gold.py`/`serving.py`, Parquet paths in DuckDB views) pass `sqlsafe.ident` / `sqlsafe.path_literal` allow-list checks. The one user-chosen identifier (leaderboard metric) is checked against a fixed set. | `sqlsafe.py`, `serve/api.py` |
| Input handling | Every archive line goes through the contract; anything else becomes a quarantine row or a dead letter with a reason. Property-based tests feed random JSON (found and fixed one crash). Quarantine keeps at most 8 KiB of each raw line. | `contracts.py`, `tests/unit/test_contracts.py` |
| Resource exhaustion | API: `statement_timeout` 2 s, read-only transactions, pool max 10 with a 5 s wait, row caps, 7-day window cap. Consumers: bounded batches (2,000), container memory limit 512 MiB, lag kept in the broker rather than in memory. Fetch: 4 connections, timeouts. | `api.py`, `consumer.py`, slow-sink experiment memory readings |
| Containers | Non-root user (uid 10001), read-only root filesystem, all capabilities dropped, `no-new-privileges`, slim pinned base image (Debian 13), Trivy config scan clean (Dockerfile and infra). Image scan on 25 Nov 2026: the pinned base had 78 fixable HIGH/CRITICAL OS findings, so the build applies Debian security updates; after that, 0 fixable remain and 53 have no Debian fix released yet (52 "affected", 1 "fix_deferred"). CI fails the build on any fixable HIGH/CRITICAL. | `Dockerfile`, CI `image` job |
| Least privilege | API uses read-only transactions; a `repostream_reader` role exists with SELECT only. Cloud design: separate service accounts, bucket-level role for the batch job only. | `sql/001_schema.sql`, `main.tf` |
| Dependencies | `uv.lock` pins every version; `pip-audit`: no known vulnerabilities (25 Nov 2026). | CI `lint-and-unit` job |
| Model files | MLflow's skops loader refused our HistGradientBoosting model as an untrusted type. We trust exactly that one type, only for models trained in the same process; downloaded models must never be loaded this way. | `ml/volume.py` |
| Privacy | Logins dropped at silver; no per-person table or endpoint; results published only as aggregates; raw downloads stay local. | `contracts.py`, README "Data and privacy" |

## Known gaps
- 53 HIGH/CRITICAL OS-package findings in the image have no upstream fix yet. A distroless or Chainguard Python base would shrink that surface; not done.
- The API has no authentication. It binds to localhost; before exposing it anywhere it needs auth and rate limiting (for example behind Cloud Run IAM).
- The API connects as the owner role in read-only transactions, not as `repostream_reader` (which is created NOLOGIN). Giving it its own login role is the next step.
- Postgres traffic inside the Docker network is not TLS-encrypted (acceptable on one host, not across hosts).
- Redpanda runs with no authentication (dev-container mode), reachable only on localhost.
- Quarantined raw lines may contain logins; they are local-only and should get a retention limit.
