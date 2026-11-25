# What the data showed

All numbers come from the local run over GH Archive hours 2026-11-01T00 to 2026-11-24T19 (572 hours; the last 4 were not yet published when fetched), plus three older hours for the old payload format: 2025-09-30T14, 2025-09-30T15 and 2025-09-08T15 (the brownout day). Queries are in `src/repostream/gold.py` and reproducible with `make up && uv run repostream fetch ... && silver && gold`.

## 1. The archive shrank by an order of magnitude, and its capture rate swings
| Hour sampled (15:00 UTC on the 15th) | File size |
| --- | --- |
| 2025-01 | 134.0 MB |
| 2025-09 | 99.9 MB |
| 2025-10 (after the 7 Oct payload change) | 38.1 MB |
| 2026-11 | 5.7 MB |

Within November 2026, daily event counts range from 66,534 to 795,179 (4.35M in total). Pull-request opens per day stay between about 9,000 and 19,000 over the same days, so the swings are mostly in push events: the archive captures event types unevenly.

**Capture index.** GitHub event ids come from global sequences, so `captured / (max_id - min_id + 1)` within an hour shows what share of that id range the archive holds. Since the change, push events have their own id sequence. November 2026 medians: 0.29% (push) and 0.07% (everything else). The id space also includes events the archive can never see, so this is a relative index, not completeness. It explains the 22 Nov spike: push capture density more than doubled that day.

## 2. GitHub's Events API change broke two metrics silently
GitHub removed payload detail from the Events API on 7 Oct 2025 (changelog of 8 Aug 2025; brownout on 8 Sep 2025). In the archive:
- PushEvent lost `commits` and `size`. PullRequestEvent's `pull_request` went from the full object to `{url, id, number, head, base}`, and a merge became its own action, `merged`, instead of `closed` with `merged: true`. The contract detects the format from the payload's shape and maps both to one vocabulary.
- **New repositories disappeared.** `CreateEvent` with `ref_type = repository` gave 12,716 new repos on 2025-09-30 and zero on every November 2026 day: only branch creates remain. The `new_repos_continuity` quality check flags this.
- **Time-to-merge needs a join now.** In the old format every merge event carried `created_at` and `merged_at`. Now the opened and merged events must both be in the archive. Of 293,344 merges captured in November, 3,494 PRs have their `opened` event captured too (among 350,543 PRs opened in the window). Distributions:

| | PRs | Median hours to merge | p90 hours |
| --- | --- | --- | --- |
| Old format, one event (2025-09 sample, 14,210 merges) | 14,210 | 0.06 | 97.3 |
| New format, both events captured (Nov 2026) | 3,494 | 0.20 | 15.7 |

The new-format sample is censored to PRs merged inside the 24-day window and requires two independently sampled events, so slow PRs are under-represented (the p90 shrinks from 97 h to 16 h). Per-repo merge-time metrics from the current archive are not trustworthy, so the API does not offer them.

## 3. Smaller real-data facts
- 69 of 4,831,018 lines failed the contract, all `repo_id_invalid`: ForkEvents whose `repo` is `{}`.
- 37 events appeared twice inside the same hourly file; none repeated across files.
- Every event's `created_at` falls inside the hour of the file that carries it (arrival lateness 0 h for all 4.83M), so the late-event handling only matters for the stream replay.
- Accounts ending in `[bot]` produced 26.9% of captured events in November (daily range 24.3% to 35.0%).
- Hours on 23 Nov fell to 15-20% of their trailing 24 h median (for example 09:00 UTC: 4,713 events against a median of 24,388). That is the archive's capture, not GitHub going quiet.
