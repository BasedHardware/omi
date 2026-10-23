# Agent silent-failure telemetry and weekly aggregate

Part four of the self-reporting loop (`dream-feedback-remediation.md`,
`agent-defect-reports.md`, `feedback-postmortem.md`,
`agent-failure-telemetry.md`, `feedback-fix-effectiveness.md`). Design only —
no code in this change.

## Problem

An agent session that quietly degrades — a retrieval tool that errors and
lets the model answer from nothing, a search that returns empty page after
empty page, a proposal rejected five times for the same guard reason —
produces a plausible-looking answer anyway. The owner experiences a worse
Omi and thumbs-downs it (or just drifts away); nothing on the ops side
enumerates the failure until someone goes looking. What exists today is
either per-journey (did the HTTP request succeed), per-fallback (did a lane
switch), or inside per-run Dream reports nobody aggregates.

This document designs the counters that make silent failure *countable* on
the serving hosts, and one weekly job that turns them into a report, by
extension of the existing seams rather than a new telemetry system.

## Current state

The seams to extend, all verified present:

- **Journey metrics** — `utils/observability/journeys.py`: closed-journey
  `JourneyName` (`chat_response`, `pusher_session`, `capture_finalization`),
  one accepted + exactly one terminal outcome per attempt, duration
  histogram. In the chat agent, only memory-retrieval tools carry a
  `ClientJourneyAttempt('memory_retrieval', client_kind)` and only
  hard exceptions fail it (`utils/retrieval/agentic.py _execute_tool`).
  Label discipline is enforced by bounded enums from
  `utils/journey_metrics_contract.py`.
- **Fallback telemetry** — `utils.observability.fallback.record_fallback` →
  `omi_fallback_total` (`component/from/to/reason/outcome`, closed enums),
  mandated by `.github/agent-docs/fallback-telemetry.md` for any branch that
  changes provider, mode, correctness or fails open.
  `utils/agent_capabilities/search.py` already records
  `component='agent_tools', from_mode='agent_search',
  to_mode='remaining_paths', outcome='degraded'` per failed search path.
- **Dream per-run counts** — `utils/dream_agent.py` lands `tool_counts`,
  `rejected` (a `Counter` of tool-rejection reason codes, from
  `utils/agent_capabilities/session.py Session.rejections`) and verifier
  outcomes in each run report; `utils/dream_metrics.py record_pass` emits
  counts-only metrics. Nothing aggregates these across runs.
- **Search quality in-band** — every agent search returns
  `counts` (`failed_paths`, …), `complete`, `truncated`, `skipped_refs`,
  `unavailable_refs` (`utils/agent_capabilities/search.py`); the model sees
  degradation, ops does not.
- **The job pattern** — Cloud Run Jobs with structured stdout JSON and
  operator-provisioned scheduling: `selfheal_tick` / `selfheal_action`
  (`backend/services/conversation_selfheal.py`), and the fail-closed Logging
  reads in `backend/services/capture_wedge.py` (two filtered 10-minute
  `entries.list` reads, page cap 1000 / 10000 entries; truncation or error
  suppresses every action for the tick). The dashboards side of this pattern
  is documented in `backend/docs/omi-core-selfheal-dashboard.md` — metrics
  are *named* there, provisioning is an operator step.
- **The weekly-report precedent** — `backend/jobs/feedback_daily_report.py`
  materializes `feedback_reports/{date}` with counts-by dimensions; the
  same shape at week granularity is the deliverable here.

## Proposed design

### One emission seam, two sinks

A single helper owns agent-failure events,
`utils/observability/agent_failures.py`:

```python
record_agent_tool_outcome(agent, tool_class, outcome, *, detail_class=None)
```

- `agent`: `'chat' | 'dream'` (bounded, matches the defect-report agent field
  in `agent-defect-reports.md`).
- `tool_class`: bounded projection of the tool name — `retrieval`,
  `memory`, `tasks`, `calendar`, `integration`, `web_search`, `device`,
  `write`, `other`. Chat-side derivation maps `STANDARD_TOOL_NAMES`
  (`utils/retrieval/agentic.py`) through a fixed table and collapses app
  tools (`{appid}_*`, per `_extract_app_id`) into one class; unknown names
  fall to `other` and never become labels verbatim.
- `outcome`: `success | error | empty | degraded | rejected`.
  `empty` is the *legitimate* empty result (query matched nothing) — the
  denominator partner that makes an "empty-search rate" meaningful rather
  than a raw count. `degraded` marks incomplete-but-returned paths (search
  `complete == false`); `rejected` marks guard rejections (Dream side).
- `detail_class`: optional bounded secondary (e.g. Dream rejection reason
  codes bucketed through a closed set).

The helper writes both sinks in one call:

1. **Prometheus counter** `omi_agent_tool_outcome_total` (labels: the three
   fields above; static, low-cardinality — never uid or session, per the
   backend label rule).
2. **Structured stdout JSON** `{"event": "agent_tool_outcome", …}` on the
   serving host — the weekly job's data source, since a Cloud Run Job
   cannot read Prometheus. This is exactly the selfheal/capture-wedge
   arrangement: counters for dashboards, log entries for jobs.

Call sites — wrapping existing boundaries, no new instrumentation inside
tools:

| Site | What it counts |
|---|---|
| `utils/retrieval/agentic.py _execute_tool` | every chat-agent tool call: success / error (exception) / empty (result sentinel from the tool-result boundary) |
| `utils/agent_capabilities/search.py` | `degraded` when `complete` is false, in addition to its existing `record_fallback` call |
| Dream session close (`utils/dream_agent.py`, where `rejected` is already summarized) | one `rejected` event per `(tool_class, reason bucket)` — a summary emission, not a per-rejection log line |

Fail-open like every metric writer in `utils/observability/journeys.py`'s
`_record_fail_open` tradition: a recording error logs at a bounded rate and
never touches the product request.

### The weekly aggregate

`backend/jobs/agent_failure_weekly_report.py`, a Cloud Run Job following the
selfheal pattern (`AGENT_FAILURE_REPORT_MODE = off | detect | report`,
default `off`; operator-scheduled, e.g. Monday 06:00 UTC):

1. Read the trailing 7 days of `agent_tool_outcome` log entries with the
   capture-wedge discipline: filtered reads, paged, hard entry cap; any
   truncation or read error fails the tick closed (no partial report — a
   silently half-read week would look like an improvement).
2. Compute per `agent × tool_class`: error rate, empty rate, degraded rate,
   top `detail_class` buckets — all with denominators.
3. Join the week's `feedback_reports` documents for per-surface,
   per-reason user rates (`counts_by_reason`), and the active fix registry
   (`feedback-fix-effectiveness.md`) for before/after deltas on fixes that
   shipped mid-week.
4. Write `agent_failure_reports/{YYYY-Www}` — global, aggregate-only, no
   owner rows: a report document in the `feedback_reports` family (counts,
   rates, deltas, `data_complete: bool`), readable from the admin feedback
   surface (`routers/feedback_admin.py` family, same key gate).

Alerting stays where alerts live: the Prometheus counter plus a
dashboard-panel entry in `backend/charts/monitoring/dashboards/general/
omi-core-features.json` is the paging surface (rate-with-denominator alerts
only, per the fallback-telemetry doc); the weekly report is the
human-review surface. The report never pages anyone.

### Deviations from the pitch

- **No per-session rows.** The brief's "silent-failure counters for agent
  sessions" reads session-granular at first blush; sessions are the wrong
  cardinality for anything stored (uid-bearing rows would need the k-anon
  gate for a benefit the aggregates don't have). Sessions stay in the log
  stream where they already are; stored telemetry is aggregate-only.
- **Server-side, not model-reported.** Tool-error rates and empty-search
  rates are deterministic observations — the model-reported versions live in
  `agent-defect-reports.md` *corroborated against these counters*, so the
  two docs meet at one source of truth. This doc owns the truth.
- **One helper, not per-site counters.** Gotcha 10 in `backend/AGENTS.md`
  forbids inventing new `*_fallback_total` counters; the same rule applied
  here means one seam (`record_agent_tool_outcome`) owns the event family.

## Data-model deltas (proposed, not implemented)

- `utils/metrics.py`: one counter, `omi_agent_tool_outcome_total`.
- `utils/observability/agent_failures.py`: the seam (enum definitions,
  projection table, dual sink).
- New collection `agent_failure_reports` (global, one document per ISO week,
  18-month TTL — long enough for year-over-year comparison, short enough to
  forget).
- Tool-result boundary: chat tools need a machine-checkable empty/error
  sentinel if `utils/retrieval/tool_result_boundaries.py` does not already
  define one — audit at implementation time; if tools return free-form
  strings, the `empty` classification degrades to per-tool adapters for the
  bounded `retrieval` class only, and the rest ship `success|error`.

## Privacy stance

No uid, no session id, no refs, no content in any counter label or report
field — the Dream telemetry rule ("metric labels never contain owner IDs,
refs or content", `backend/docs/runbooks/dream-agent.md`) applied fleet-wide.
The weekly job reads only Omi's own structured log events, and the stored
report is global aggregates. Because there are no per-owner rows, the k-anon
gate is not needed *for this document*; anything that later wants
owner-scoped failure rows must go through `agent-defect-reports.md`'s
owner-scoped collection instead.

## Rollout and kill switch

`AGENT_FAILURE_REPORT_MODE` gates the job (`off` default; `detect` counts and
logs would-publish without writing; `report` writes). The emission seam is
always-on once shipped — counters and one log line per tool call are
negligible cost, and an emission that only runs in `report` mode would make
`detect` a different measurement rather than a dry run. Per-call-site rollout
lands the `_execute_tool` wrap first (chat is the volume surface), Dream
summary emission second, search `degraded` third (it already has the data in
`counts`). Kill switch: mode to `off`; the seam's failure mode without a
reader is bounded log volume, and the counter keeps dashboards working
independently of the job.

## Open questions

- Log volume: one JSON line per chat tool call multiplies serving logs by
  tool-call volume. If Cloud Logging cost controls
  (`backend/docs/runbooks/cloud-logging-cost-controls.md`) make that
  unacceptable, the fallback is log-based *metrics* (counters derived
  server-side by Logging, as the selfheal dashboard doc already assumes for
  job telemetry) sampled from the same line — the dashboards doc's
  "must be provisioned by an operator" path. Decide at implementation with
  numbers from `detect` mode.
- Should the weekly job also aggregate Dream run-report `rejected` counters
  from Firestore (per-run documents) as a cross-check against the log
  stream? Two sources for one number is usually a bug factory; the
  cross-check might be a one-time validation query instead of a permanent
  join.
- `tool_class` granularity for integrations (calendar vs gmail vs tasks as
  one `integration` class or separate) — start coarse, split only when a
  weekly report shows a class that needs action it cannot name.
