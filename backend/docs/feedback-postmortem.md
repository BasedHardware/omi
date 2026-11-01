# Threshold-triggered feedback post-mortem

Part three of the self-reporting loop (`dream-feedback-remediation.md`,
`agent-defect-reports.md`, `feedback-postmortem.md`,
`agent-failure-telemetry.md`, `feedback-fix-effectiveness.md`). Design only —
no code in this change.

## Problem

The daily negative-feedback report (`backend/jobs/feedback_daily_report.py`)
aggregates the prior UTC day across *all* owners. An owner having a bad day —
five thumbs-down in a row on summaries, a burst of memory discards — is a few
rows in that global document, reviewed the next morning by a human who must
open each pointer window one at a time through the admin context endpoint.
Nothing looks *across* one owner's bad day and answers "what happened to this
person?" The original product idea was a feedback popup that would apologize
to the user; this design deliberately drops the popup (no proactive nag UI)
and keeps the investigation.

One owner, N negatives in a UTC day → one post-mortem agent run over that
owner's feedback and resolved context windows → one structured report an
operator reads instead of twenty pointer-clicks.

## Current state

Everything the trigger and the inputs need exists:

- Ledger + pointers: `database/feedback.py` (`feedback_events`,
  `list_negative_events`), `utils/feedback_context.py` with the split that
  makes this design possible — `resolve_context` builds an ids-only
  `FeedbackContextPointer` under a Firestore field mask
  (`_METADATA_FIELDS`) so the nightly job never receives encrypted bodies;
  `hydrate_context` decrypts one event's window per admin request
  (`routers/feedback_admin.py
  GET /v1/admin/feedback/events/{event_id}/context`) and persists nothing.
  Per-target collapse (`_collapse_per_target`) makes "N negatives" countable
  without double-counting the tap-then-reason write race.
- Report materialization: `jobs/feedback_daily_report.py generate_report`
  (entry cap 500, raw fetch 4×, 800 KiB document budget) writing
  `feedback_reports/{YYYY-MM-DD}`; admin read/backfill routes in
  `routers/feedback_admin.py`, all behind the `X-Admin-Key` +
  `X-Admin-User` attribution gate.
- k-anonymized developer patterns: `database/dream_feedback.py
  aggregate`/`read_patterns()` (epoch-scoped, HMAC-distinct users, k ≥ 20) —
  the sanctioned shape for anything developer-facing that originates in
  owner data.
- Job pattern to copy: `backend/services/conversation_selfheal.py` +
  `backend/modal/conversation_selfheal_job.py` — `SELFHEAL_MODE`
  `off|detect|nudge|heal` (default `off`), structured `selfheal_tick`
  stdout JSON, a rotated CAS scan cursor, and operator-manual scheduling
  (no deployment made in that change). `backend/services/capture_wedge.py`
  contributes the fail-closed Logging-read discipline (bounded pages;
  truncation or error suppresses all actions for the tick).
- Rollout cohort machinery: `config/rollout_cohorts` (`dream-agent` cohort)
  and `config/dream_agent.py eligibility` (`all|paid|allowlist`).
- Agent defect reports (`agent-defect-reports.md`, proposed) and Dream
  feedback dispositions (`dream-feedback-remediation.md`, proposed) are the
  other inputs a post-mortem will eventually join; this design works without
  them and treats them as enrichment when present.

## Proposed design

### Trigger

A small sweep (same shape as the selfheal tick: Cloud Run Job, mode-gated,
operator-scheduled) counts, per owner, the prior UTC day's collapsed negative
targets via the owner-scoped index introduced in
`dream-feedback-remediation.md`
(`feedback_events_negative_by_uid_created_at`). Counting **collapsed targets,
not raw rows** reuses `_collapse_per_target` semantics so a reasoned
thumbs-down (two rows) counts once, and counting **targets, not events**
stops one angry session from tripping the threshold by itself.

At N ≥ `FEEDBACK_POSTMORTEM_THRESHOLD` (default 3, config) the sweep writes
one idempotent work item `feedback_postmortem_queue/{uid}:{YYYY-MM-DD}` —
created-once (Firestore `create`), so scheduler retries and overlapping ticks
cannot mint a second run for the same owner-day. Global bounds per sweep: at
most 50 queued owner-days, oldest-first; overflow is counted and logged, not
carried — a fleet-wide bad day (release regression) is the weekly aggregate's
(`agent-failure-telemetry.md`) problem, not fifty post-mortems.

### The run

One bounded model run per work item — a dedicated
`backend/services/feedback_postmortem.py`, **not** a Dream pass. Dream's
capability layer exists to mutate owner data under verification; a
post-mortem produces an operator-facing report, a different authority with no
Review queue and no proposals. Reusing `run_pass` would drag in admission,
edits-per-pass, Review attention slots and Undo machinery that are all wrong
for a read-only run.

Inputs, assembled with the pointer machinery only:

1. The day's collapsed negative events for the owner (envelope fields; no
   text).
2. Resolved pointer windows (`resolve_context` per event — ids, senders,
   timestamps, follow-up counts).
3. When `FEEDBACK_POSTMORTEM_HYDRATION=ephemeral` (see privacy): the
   hydrated windows, decrypted in-memory exactly as `hydrate_context` does,
   fed to the model and discarded. Nothing hydrated is ever persisted.
4. Optional enrichment, when present: the owner's agent defect reports
   (`agent-defect-reports.md`) and Dream `feedback_dispositions`
   (`dream-feedback-remediation.md`) for the same day.

Output: one structured document `feedback_postmortem_reports/{date}:{uid}`
mirroring the envelope discipline of `feedback_reports` (counts and pointers,
plus findings):

```
date, uid, generated_at, trigger: {collapsed_targets, by_surface, by_reason},
findings: [{finding_class, severity, event_ids[], evidence: pointer-only,
            remediation_class, links_to_dream_proposals[]}],
model_usage: {tokens, cost_usd}, truncated
```

`remediation_class` is a closed enum (`dream_capability` — Dream can act,
with the mapping in `dream-feedback-remediation.md`; `product_fix` — fix
registry candidate per `feedback-fix-effectiveness.md`; `data_issue` —
owner-specific, no product action; `unclear`). `links_to_dream_proposals`
references Review item ids when Dream already proposed something for the same
event, so an operator sees at a glance that the loop is already closing or
already failed to.

Budget: token cap per run (default sized like a light Dream bucket — this is
a single-digit-model-call job, not an agentic search), one retry on provider
failure, hard wall-clock 300s. A failed run marks the work item `failed` and
stops; it does not retry the day (the events are still in the ledger and the
daily report; a post-mortem is an accelerator, not a durable record).

### Consumption

- Admin surface: extend `routers/feedback_admin.py` with list/get routes for
  post-mortem reports (same `_verify_admin_key` gate; same audit logging of
  `admin:{key_hash}/{user}`).
- The daily report document gains a `postmortem_count` integer so a reviewer
  landing on `feedback_reports/{date}` knows deeper investigations exist.
- Developer-facing aggregates never leave the k-anon gate: weekly, the
  finding-class distribution joins `dream_feedback`-style patterns
  (component = `finding_class`, k ≥ 20, epoch-scoped). A finding class seen
  for fewer than 20 distinct owners in the epoch is not published to the
  developer copy at all.

## Data-model deltas (proposed, not implemented)

- New collections: `feedback_postmortem_queue` (work items, TTL'd after
  terminal state) and `feedback_postmortem_reports` (90-day TTL; operator
  data like `feedback_reports`, outside the user tree, plaintext envelopes
  with pointers only).
- New index: none beyond the owner-scoped negative-events index already
  proposed; the queue is drained by document scan of `status == 'pending'`
  (small, TTL'd).
- `models/feedback.py`: no change. A `FeedbackPostmortemReport` model joins
  the module's pointer-only family.

## Privacy stance

The report is pointer-only, exactly like `feedback_reports`: event envelopes,
ids, timestamps, counts, closed enums. The one genuinely new surface is
**ephemeral hydration**: `hydrate_context`-grade decryption performed by a
job rather than an admin request. It is opt-in (`FEEDBACK_POSTMORTEM_HYDRATION
= off|ephemeral`, default `off` — without it the run reasons from metadata
and pointer shape only, which is materially weaker but violates nothing),
and when on it is bound by the same rules the admin route already follows:
one event window at a time in memory, nothing persisted, and an audit log
line per run (`postmortem_hydrated uid=<hash> events=<n>`) mirroring the
admin context route's attribution line. The posture: decryption moves from
"admin-initiated, per-event" to "job-initiated, per-event, allowlisted
owners first, logged the same way" — and the rollout sequence below exists
to make that a reviewed step, not a quiet one.

## Rollout and kill switch

Modes, in order, each a config value (`FEEDBACK_POSTMORTEM_MODE`, default
`off`, registered per `backend/docs/feature-flag-registry.md`):

1. `off` — inert.
2. `detect` — trigger counting only; writes queue items with
   `would_run: true` and no model call. Validates thresholds against real
   distributions before any spend.
3. `metadata` — full runs with hydration `off`.
4. `ephemeral` — full runs with in-memory hydration.

Owner eligibility starts at the `dream-agent` rollout cohort (reuse
`config/rollout_cohorts`; post-mortems have no owner-facing surface, so the
cohort is a spend/privacy control, not a UX one) before `all`. Kill switch is
the mode value; the queue drains naturally and pending items expire. The
sweep ships unscheduled like the selfheal job did — an operator provisions
the Cloud Scheduler entry after review, and until then every code path is
inert.

## Open questions

- Threshold 3: is that right? `detect` mode exists to answer this with data;
  the daily report's per-owner distribution (queryable now from
  `feedback_events`) should set it before `metadata` ships.
- Should a post-mortem run be able to *seed* Dream for the next pass (marking
  targets dirty) when `remediation_class = dream_capability`, closing the
  loop automatically? Tempting; deferred — Dream's next scheduled pass
  already ingests the same events per `dream-feedback-remediation.md`, so
  the seed-marking would only buy latency.
- If an owner's bad day is caused by an active incident (STT outage →
  `recording_poor_transcription` burst), post-mortems multiply telling the
  same story. Cheap dedupe: skip queueing when the day's findings would
  collapse to one incident-class signal — needs an incident signal source to
  be useful; parked.
