# Home live-owner cache evidence, 2026-11-08

Owner: home-overlap lane. Read-only GCP tier: `ro-prod` throughout. No user
records, raw log entries, secrets, or authenticated user API calls were read.
No IAM, runtime configuration, merge or deployment changes were made.

## Source revisions and consumer audit

At 2026-11-08T05:59:25Z, current `origin/main` was
`ec0e7afed79521a0510a38e691a1f2d087ed845f`; #24865 was still open at
`727cb8e24483faeac0dc6cda534aeb145958608e`. This follow-up starts on current
main and incorporates that head locally for executable integration coverage.
The PR targets main; it is dependent on #24865, and does not gate that PR.
Only the cache change commit is new follow-up work.

Rechecked the actual files on both revisions, not the older 028c78b snapshot:

- `backend/routers/pending_work.py`: main has the original single
  `pending_sync_jobs(uid)` call. #24865 has both the presentation call with
  `listed_conversation_ids=represented` and the raw call without that argument.
  Both remain unchanged by this follow-up. Pending-work continues using the
  fresh, uncached `live_owner` entrypoint.
- `backend/utils/sync/final_pass_rehome.py`: identical on main and #24865;
  `live_legacy_jobs` uses only `len(pending_sync_jobs(uid))`. It sees every live
  writer because no presentation argument is supplied.
- `app/lib/backend/schema/pending_work.dart`: both revisions read
  `conversation_ids`. Main does not yet have `recording_count`; #24865 adds its
  parser and defaults absent values to one. This follow-up changes no payloads
  or app code.
- `pending_sync_jobs` in #24865 folds `target_conversation_id` into the result's
  `conversation_ids` and adds `recording_count` when ownership is enabled.
  Raw writer probes retain all jobs; presentation calls dedupe represented jobs.

Approach B audit: `create_sync_job` stores `recording_ids` and nullable
`target_conversation_id`, but no live episode snapshot/ID. `update_sync_job`
and fenced variants merge job metadata; they likewise do not already receive
that live ownership proof. Resolving it at admission would introduce a lookup,
and jobs retain metadata for 24 hours. Approach A is the narrower bounded cache.

## Production measurement: blocked, not zero

Observation interval for requested daily measurement:
2026-11-07T00:00:00Z through 2026-11-08T00:00:00Z.
Investigation performed 2026-11-08T05:54Z–05:59Z using
`source ~/.local/bin/gcp-agent-env.sh ro-prod`.

- Monitoring descriptor inventory at
  `GET https://monitoring.googleapis.com/v3/projects/based-hardware/metricDescriptors`
  filtered to `prometheus.googleapis.com/` succeeds. Request metrics include
  external-list counts (developer/MCP routes), list conditional validators
  (`origin`, `validator`, `service_name`), and episode API requests (`channel`,
  `outcome`, `service_name`). None identifies unfiltered Home polls carrying
  capability plus exact episode/member acknowledgement. Source declarations:
  `utils/observability/external_lists.py`, `utils/list_version_check.py`,
  `utils/episodes/metrics.py`. Conditional counts also skip dynamically projected
  lists, so they cannot stand in for the requested population.
- `gcloud logging buckets list --project=based-hardware --location=global
  --format=json`: `_Default` and `_Required` have no analytics enablement.
  The us-central1 bucket list is empty.
- `gcloud logging sinks list --project=based-hardware`: Cloud Run logs export
  to `based-hardware.cloud_run_logs`. BigQuery table metadata listing succeeds;
  the dated `run_googleapis_com_requests_20261107` table is present. Schema
  access and a counts-only query both return HTTP 403 / `PERMISSION_DENIED`.
  No raw entries were requested. No permission changes were attempted.

Counts-only Standard SQL attempted via
`POST https://bigquery.googleapis.com/bigquery/v2/projects/based-hardware/queries`
with `maximumBytesBilled=2000000000` and `useLegacySql=false`:

```sql
SELECT COUNTIF(
  REGEXP_CONTAINS(httpRequest.requestUrl, r'/v1/conversations(?:\?|$)')
  AND NOT REGEXP_CONTAINS(httpRequest.requestUrl,
                        r'[?&](start_date|end_date|folder_id|starred|sources)=')
) AS unfiltered_conversation_list_requests
FROM `based-hardware.cloud_run_logs.run_googleapis_com_requests_20261107`
WHERE timestamp >= TIMESTAMP('2026-11-07T00:00:00Z')
  AND timestamp < TIMESTAMP('2026-11-08T00:00:00Z')
  AND httpRequest.requestMethod = 'GET'
  AND resource.labels.service_name = 'backend'
```

Even a successful query would be a broader list-request count, not proof of
capability/ack headers. No measured eligible poll rate N or production cache
miss/fallback rate m is available. Reporting either as zero would be false.

| Production path | Daily logical owner lookups | Evidence status |
| --- | --- | --- |
| Before | N × 1 | N unavailable; existing owner code is one lookup per eligible poll |
| After | N × m | N and m unavailable; no deployed cache measurement |
| Redis outage / switch false | N × 1 | Same fresh lookup as before |

A logical owner lookup is not necessarily one billed document read:
`database/episodes.py:get_current_episode` reads `episode_links/current`, then
an episode document when a link exists (redirects can require more). This cache
avoids that whole operation on a hit. Do not label logical calls as measured
Firestore document billing.

## Synthetic measurement, not production traffic

At 2026-11-08T05:59Z–06:01Z,
`test_measured_synthetic_five_second_poll_miss_rate` simulates a complete day:
17,280 polls, 2,880 Firestore calls, 2,880 cache fills. Measured synthetic miss
rate = 2,880 / 17,280 = 1/6. Before = 17,280 × 1 = 17,280 calls/day;
after = 17,280 × (1/6) = 2,880 calls/day for that synthetic schedule only.

Estimate / assumptions: one UID polling every five seconds continuously, a
healthy cache, no concurrent cold fills. This is not a measured production
schedule and supplies no production savings claim. TTL alone cannot determine
m: distinct owners, idle gaps, cold starts, concurrency and outages matter.

The new `omi_home_live_owner_lookups_total{source="cache"|"firestore"}` has
only fixed labels and covers this eligible Home path. Once deployed by the
Infra Rollout Coordinator and observed over a full day, use aggregate PromQL:

```promql
sum(increase(omi_home_live_owner_lookups_total[24h]))
sum(increase(omi_home_live_owner_lookups_total{source="firestore"}[24h]))
```

The first is N; second/first is m; before=N, after=N×m. Outages and cache-off
bypasses count as Firestore, so the effective read rate includes them.

## Local checks

Each file ran in its own command, from `backend`, with:
`/Users/dazheng/workspace/omi/bin/omi-heavy run -- .venv/bin/python -m pytest -q tests/unit/<file>.py`.

- `test_home_owner_cache.py`: 33 passed (final source, including synthetic day).
- `test_homesettle.py`: 58 passed, including missing/stale acknowledgement cases.
- `test_pending_work.py`: 50 passed, including raw writer-lease preservation.
- `test_episodes_finalizer_hook.py`: 32 passed, including detail intent and expiry.

Only the first file is added/changed by the follow-up itself. Other test-file
changes in a main-based diff belong to #24865. No real service acceptance or
production observation is claimed by these hermetic tests.

## Publication update, 2026-11-08T08:03:44Z

#24865 merged independently at 2026-11-08T07:00:42Z. Current main was refreshed
to `0b49927c68e9957a8302a1c2b2bc0d63a5071011` and integrated locally. All three
consumer files above are identical between that main revision and the #24865
head: both pending-work calls remain, the rehome probe still uses only length,
and the Dart parser still reads conversation IDs and defaults recording count
to one. This follow-up changes none of those payloads.

The complete shared local preflight passed 71 checks at `0c803611a9acff9136b36058d02f24c90529f603`,
including all 558 query-shape tests (556 seconds with the documented 900-second
per-file wall deadline) and 1,006 web tests. The independent backend typecheck
then found one optional-member narrowing error in the cache serializer. The
follow-up commit stores that dictionary value in a local before its datetime
check; runtime behavior and imports are unchanged. Cache tests pass again (33),
and the file's targeted Pyright run using the worktree Python reports zero
errors. Publication reruns full backend typing and the remaining push checks;
the already completed shared preflight is reused explicitly, not claimed as a
fresh full run of the final integration revision. Normal PR CI remains enabled.
