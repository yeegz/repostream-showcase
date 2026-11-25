# ADR 0001: GH Archive hourly files as the source

**Status:** accepted, 25 Nov 2026

## Context
The project needs real, public, high-volume event data with realistic failure modes, that can be replayed and that costs nothing to fetch. Options: GitHub REST/GraphQL Events API, GH Archive (hourly gzip NDJSON of the public events timeline at data.gharchive.org), the GH Archive BigQuery dataset, or a synthetic generator.

## Decision
Use GH Archive hourly files over HTTPS.

## Why
- It is the public GitHub events timeline, already batched per hour: a natural unit for idempotent, checkpointed ingestion.
- No credentials and no API rate limits for bulk download. The REST Events API returns at most 300 events per feed and is rate-limited, so it cannot provide history.
- BigQuery would move the interesting work (parsing, dedup, partitioning) into a managed warehouse and costs money per byte scanned.
- The data contains real faults: an upstream schema change (7 Oct 2025), capture-rate swings, records with empty `repo` objects, files not yet published.

## Consequences
- The archive is a *sample* of GitHub activity, and since Oct 2025 a small and varying one. Every metric is labelled "as captured by GH Archive", never "on GitHub". See docs/results/data-findings.md.
- Licensing: GH Archive publishes no explicit data licence (the site text is CC-BY-4.0, and the underlying content is GitHub users' public activity). We keep the data local, do not redistribute it, drop logins at the silver layer and publish only aggregate results.
