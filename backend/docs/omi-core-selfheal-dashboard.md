# Omi core self-heal dashboard (SCA-556)

Operational view for the conversation self-heal surfaces: the listen
accepted → first-audio → no-audio funnel, the durable recovery sweep, and
the pendant capture-wedge detector. This document names every metric,
selector, and log-metric so a dashboard can be assembled without guessing.

The existing dashboard JSON `backend/charts/monitoring/dashboards/general/
omi-core-features.json` is the dashboard these panels extend. No panels were
added to it in this change: the log-metric series below must be provisioned
in Cloud Logging by an operator first, and none of them exist today.

## Prometheus series (scraped)

| Panel | Query | Notes |
|---|---|---|
| Accepted listen sessions | `sum(rate(omi_listen_accepted_total[$__rate_interval])) by (transcription_source)` | Denominator of the funnel; every accepted `/v4/listen` socket. |
| First audio | `sum(rate(omi_listen_audio_outcome_total{outcome="first_audio"}[$__rate_interval])) by (transcription_source)` | Sessions that delivered at least one decodable frame. |
| No-audio teardown | `sum(rate(omi_listen_no_audio_teardown_total[$__rate_interval])) by (transcription_source)` | Accepted sessions that ended before any first-audio byte, all sources, VAD or not. Distinct from `omi_listen_audio_outcome_total{outcome="no_audio_teardown"}`, which is the phone-call-specific outcome. |
| True VAD zero-byte sessions | `sum(rate(omi_listen_zero_byte_session_total[$__rate_interval])) by (transcription_source)` | VAD-gated sessions with `bytes_received==0 AND chunks_total==0 AND session_duration_sec==0.0` — the wedge signature. |
| Finalization latency p50/p95 | `histogram_quantile(0.5, sum(rate(omi_journey_latency_seconds_bucket{journey="capture_finalization"}[$__rate_interval])) by (le))` and the same with `0.95` | Job-admission → terminal latency of the durable finalization job. Not capture end-to-end; capture duration before admission is outside this histogram. |

Labels `transcription_source` and `client_platform` are bounded enums; there is
never a uid or session label.

## Cloud Logging series (must be provisioned)

The self-heal job is a Cloud Run Job that Prometheus does not scrape, so all
job telemetry is structured stdout JSON (`jsonPayload.event`). Create these
log-based metrics before wiring panels:

| Log metric name | Filter | Aggregation |
|---|---|---|
| `omi_selfheal_tick` | `jsonPayload.event="selfheal_tick"` | one row per tick; read fields `scanned`, `content_holding`, `oldest_age_seconds`, `content_holding_over_12h`, `skipped`, `enqueued`, `verified`, `refused`, `errors`, `nudged`, `undeliverable`, `mode`, `exhausted` |
| `omi_selfheal_action` | `jsonPayload.event="selfheal_action"` | count by `outcome` (`enqueued`, `verified`, `skipped`, `refused`, `dry_run`) and bounded `reason` — the sweeper action/hour panel |
| `omi_selfheal_nudge` | `jsonPayload.event="selfheal_nudge"` | count by `outcome` (`sent`, `undeliverable`, `cooldown`, `dry_run`) |
| `omi_selfheal_wedge_first_seen` | `jsonPayload.event="selfheal_wedge_first_seen"` | count — the once-per-uid/day wedge cohort |
| `omi_selfheal_guard` | `jsonPayload.event="selfheal_guard" AND jsonPayload.outcome="refused"` | count — SERVER_RECOVERY runs the pre-persist structured guard refused (fields `reason`, `uid`, `conversation_id`); never carries transcript or title |
| `selfheal_wedge_candidate` | `jsonPayload.event="selfheal_wedge_candidate"` | diagnostic event (uid + streak_count); no metric required |
| `omi_sync_backfill_dead_letter` | `jsonPayload.event="sync_backfill_dead_letter"` | count — terminal backfill failures confirmed in the durable ledger (fields `job_id`, `uid`, `failure_code`, `outcome=confirmed`); operator-provisioned like the other log metrics |

`selfheal_tick` fields describe the scanned window only. `content_holding` is
stale (≥2h) content-bearing `in_progress` rows seen in the window — the age
gate runs before any transcript decoding, so young rows and empty old stubs
never enter the backlog. `oldest_age_seconds` is the oldest `finished_at` age
among those stale content-bearing rows, `content_holding_over_12h` the ones
past 12 hours, `exhausted` whether the cursor reached the tail. They are not
fleet-global snapshots — a window can legitimately be `exhausted=false` while
later pages are unexplored.

## Design deviations from the proposal

- **One recovery attempt, not two.** Durable `finalization_job_id` identity is
  `(uid, conversation_id, revision)`; a dead-lettered row cannot safely mint a
  second revision. Rows carrying any `finalization_job_id` are refused at the
  admission transaction and page for manual review instead.
- **Synchronous guard before persist, not compensation after.** A
  SERVER_RECOVERY run that produces only the deterministic minimum raises a
  typed error before the persist transaction and before any derived-effect
  fanout, preserving the row's in-progress/processing state and content.
- **Admission protects existing titles; output must still be rich.** A
  non-empty `structured.title`, conversation-level `user_title`, overview, or
  any derived list refuses admission even when the row would not count as
  rich — a useful title is never overwritten. Verification still requires
  rich output (overview or a derived list): a deterministic-minimum title
  alone is not a successful recovery.
- **Scan windows, not global snapshots.** The sweep examines at most 2000
  rows per tick on a rotated CAS cursor; every `selfheal_tick` count is
  explicitly the scanned window.
- **Existing dashboard, not a duplicate.** Panels extend
  `omi-core-features.json` rather than a new dashboard JSON.
- **No deployment manifests or workflows.** Only the job module is added;
  scheduling/Docker/CI wiring is a separate delivery step.
- **One in-flight backfill job per uid, default-on.** The proposal allowed two
  concurrent backfill jobs; the shipped guard claims a single
  `sync_backfill:inflight:{uid}` Redis NX slot (48h TTL, token = job_id) and
  refuses extra admissions with 429 `backfill_paced`. It is enabled unless
  `SYNC_BACKFILL_INFLIGHT_LIMIT=false`, independent of the legacy
  `SYNC_BACKFILL_ADMISSION_LIMITS` daily speech caps, and releases with the
  existing compare-delete owner's-token script.
- **Durable dead-letter ledger, unchanged client status.** Terminal backfill
  failures write `sync_dead_letters/{job_id}` (pending → dead_letter) before
  and after the Redis terminal publish. The app still sees only the existing
  `failed`/`partial_failure` statuses — no new `dead_letter` client status —
  and only ACKs `completed`, so a poll without a ledger record 503s instead of
  draining the WAL. A terminal failed/partial backfill task also leaves its
  staged blobs untouched: this is **not** durable server-side audio retention
  — the existing object-lifecycle expiry still applies — the client WAL stays
  the primary retry material.
- **Two filtered 10-minute Logging reads, not one broad 30-minute read.** The
  wedge detector first reads true zero-session `vad_gate_metrics` entries
  (`bytes_received=0 AND chunks_total=0 AND session_duration_sec=0`) over the
  trailing 10 minutes, then a second read of `bytes_received>0` entries
  restricted to the candidate uids (JSON-quoted). A single broad read could
  truncate under ordinary fleet volume and suppress every detection. Each
  filtered read pages at 1000 entries capped at 10000; truncation or an error
  on either read, or more than 50 candidate uids, fails the tick closed — no
  push, no cohort claims.
- **Zero/no-audio VAD telemetry is independent.** `omi_listen_zero_byte_session_total`
  and `omi_listen_no_audio_teardown_total` do not replace the phone-call
  `omi_listen_audio_outcome_total{outcome="no_audio_teardown"}`; the
  phone-specific outcome still fires exactly once where it did before.

## Operator runbook (manual, not deployed here)

The sweep entrypoint `backend/modal/conversation_selfheal_job.py` ships inside
the immutable existing backend image (`backend/Dockerfile` already copies
`backend/`). An operator runs it as a Cloud Run Job with:

```
python -m modal.conversation_selfheal_job
```

**No Scheduler or Cloud Run Job deployment was made in this change.** To
schedule it, an operator manually provisions a Cloud Scheduler job invoking
the job every 15 minutes (UTC) — e.g. cron `*/15 * * * *` — against the
deployed job resource. Until then the code paths are inert:
`SELFHEAL_MODE` defaults to `off`, and `SELFHEAL_MODE=nudge` or `heal` must
only be set after explicit approval — `detect` is the intended first mode
because it performs no user-data mutation and sends no pushes.
