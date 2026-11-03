# Fix-effectiveness annotation for feedback reason rates

Part five of the self-reporting loop (`dream-feedback-remediation.md`,
`agent-defect-reports.md`, `feedback-postmortem.md`,
`agent-failure-telemetry.md`, `feedback-fix-effectiveness.md`). Design only —
no code in this change.

## Problem

A fix ships for a failure mode — say the summary-omission bug behind
`summary_incomplete`. Three weeks later the question "did it work?" is an
investigation: someone queries the ledger by hand, picks a before/after date
that is probably the merge date rather than the rollout date, forgets the
mobile app lags the backend by weeks for client-side reasons, and presents a
number nobody trusts. Meanwhile the daily report's `counts_by_reason` keeps
counting as if no fix had ever shipped.

This document designs the missing piece: a declarative registry that binds a
shipped fix to the reason classes it claims to address, and a read path that
turns before/after into one query. This is what converts the loop from
self-*reporting* to self-*fixing*: report → fix → measured effect → the fix
registry's claim confirmed or falsified.

## Current state

More of the substrate exists than the idea assumes — the design's job is
mostly to stop re-deriving it:

- **Provenance is already captured at write time.** `FeedbackEvent`
  (`models/feedback.py`) carries `app_version`, `app_build`,
  `backend_release`, `model_name`, `model_version`, `prompt_name`,
  `prompt_commit`, `langsmith_run_id`, `trace_id`, `correlation_id`. The
  mobile idempotent path merges `backend_release` / `model_version` from
  server-known values (`routers/mobile_feedback.py`); the desktop chat path
  captures prompt coordinates off the rated message
  (`utils/feedback.py record_chat_message_feedback`). Every event is
  therefore already cohortable by release and prompt revision — the before/
  after *split* is free; what is missing is the record of *which release is
  the boundary for which reason*.
- **The aggregate is already materialized.** `feedback_reports/{date}`
  carries `counts_by_reason` / `counts_by_surface` per UTC day
  (`backend/jobs/feedback_daily_report.py`); `total_negative` covers days
  where entries were truncated.
- **The owner-level loop already half-exists.** Dream proposals that came
  from feedback will carry `feedback_event_id` in their Review `source`
  (`dream-feedback-remediation.md`, following the existing `dream_origin`
  precedent in `database/review_store.py`); Undo is tracked with demotion
  (`dream_store.demoted_types`, `Caps.undo_rate` / `undo_min_samples`,
  `database/review_changes.py set_undone`).
- **The config-as-data precedent.** `config/plan_catalog.json` +
  `scripts/generate_plan_catalog.py --check --base-ref origin/main`: a
  checked-in data file with a validator that fails CI on drift. Fix
  declarations want exactly this shape.

## Proposed design

### The fix registry

`backend/config/feedback_fixes.json`, validated by a small checker
(`scripts/check_feedback_fixes.py`, wired like the plan-catalog check so a
malformed or dangling entry fails preflight):

```json
{
  "fixes": [
    {
      "fix_id": "fix-2026-11-summary-omission",
      "scope": {"surfaces": ["conversation_summary"],
                 "reasons": ["summary_incomplete"]},
      "boundary": {"field": "backend_release", "since": "…"},
      "rolled_out_at": "2026-11-14",
      "expected": "reason_rate_down",
      "owner": "backend",
      "notes": "One line. What the fix changed.",
      "retired_at": null
    }
  ]
}
```

- `scope.reasons` uses the ledger's own enum values (`FeedbackReason`,
  `MobileFeedbackReason`); the checker rejects unknown values — the same
  anti-dilution discipline the taxonomies themselves enforce.
- `boundary.field` is one of the provenance fields that actually appears on
  events (`backend_release`, `app_version`, `prompt_commit`, `model_version`);
  the registry never invents a boundary the ledger cannot evaluate. A fix
  whose rollout is gradual picks `rolled_out_at` as the boundary instead
  (time-window cohort).
- `retired_at` supersedes rather than edits: a reverted fix is retired with a
  successor `fix_id`, so historical effectiveness answers stay stable.

### Effectiveness as a query, not an investigation

One reader, two surfaces:

- **`database/feedback.py` query helper** (design): `reason_rate(fix, window)`
  → two cohorts over a shared lookback (default 14 days each side): events in
  scope before the boundary vs. after, rate-normalized per surfaced day (a
  plain count would credit a fix for a quiet week). Returns counts, rates,
  and the denominators — never a bare percentage, so a reviewer can see an
  n=3 "improvement" for what it is.
- **Admin endpoint** (design): `GET /v1/admin/feedback/fixes` and
  `GET /v1/admin/feedback/fixes/{fix_id}/effectiveness` in
  `routers/feedback_admin.py`, behind the existing `X-Admin-Key` gate. The
  response embeds the registry entry (so the claim travels with the number)
  and a `verdict` the caller can dispute: `improved | flat | regressed |
  insufficient_data` with the threshold stated inline.

The daily and weekly reports consume the same helper:
`feedback_reports/{date}` gains an `active_fixes` block (fix ids in force
that day — one line, so a spike reader immediately knows a fix *should* have
been active), and `agent_failure_reports/{week}` (per
`agent-failure-telemetry.md`) gains the before/after delta for fixes whose
boundary fell inside the week.

### Annotation, not ledger mutation

The pitch's `fixed_in_release` tag on "affected report entries" deliberately
becomes a **read-time join, not a stored tag**:

- The ledger is append-only by design (`models/feedback.py` docstring: the
  moment the answer disappointed is the thing worth reviewing). Back-filling
  tags onto historical rows — or re-writing report documents to gain a field
  — creates a second, mutable history of the same events and a migration
  every time a fix id is corrected.
- The registry *is* the annotation: it is declarative, versioned in git,
  reviewable in the PR that ships the fix, and evaluates against any past or
  future event without touching it. "Which entries did fix X address?" is
  answered by the same scope filter the effectiveness query runs.
- Where a *stored* link is load-bearing, it is forward-looking and
  event-granular: post-mortem findings record `fix_ids[]` when a finding is
  later claimed by a fix (`feedback-postmortem.md`), and Dream Review items
  carry `feedback_event_id` (`dream-feedback-remediation.md`). Those are new
  writes, not rewrites.

### The owner-level half

Population reason-rate is the primary metric; the registry also enables the
per-owner confirmation loop: for a fix with `expected: reason_rate_down`,
query Review items whose source `feedback_event_id` points at an in-scope
event and whose kind matches the fix's remediation mapping — applied and
not-undone after 30 days counts as owner-confirmed. That query reuses
`review_changes` + the Undo window and feeds the weekly report's fix section
as `owner_confirmations: n/total`. It is a secondary signal (selection bias
is real: only owners who kept Review items are counted) and is labeled as
such in the report.

## Data-model deltas (proposed, not implemented)

- New file `backend/config/feedback_fixes.json` + checker script; no schema
  authority beyond it.
- `models/feedback.py`: `FeedbackReport` gains optional `active_fixes` (list
  of fix ids); nothing on `FeedbackEvent`.
- `routers/feedback_admin.py`: two read-only routes; the effectiveness
  computation lives in `database/feedback.py` next to `list_negative_events`
  so the query and its index needs stay in one place.
- Indexes: effectiveness cohorts reuse the existing
  `NEGATIVE_FEEDBACK_EVENTS_QUERY` time-range shape plus post-filtering on
  reason/surface/provenance in the checker — no new composite until the
  query is measured slow; the registry keeps scopes small, and the admin
  endpoint is low-QPS by construction.

## Privacy stance

Nothing new crosses the pointer line. The registry holds reason-class names
and release identifiers — no event content. Effectiveness outputs are
aggregate counts and rates; the admin endpoints sit behind the same key gate
and audit logging as every other feedback-admin route. No owner appears in
any effectiveness artifact (the owner-level half counts items, never ids,
and only inside the existing admin surface).

## Rollout and kill switch

The registry is inert data until a reader uses it: land the checker + the
`active_fixes` daily-report block first (no behavior beyond one report
field), the admin endpoints second, the weekly-report join third alongside
`agent-failure-telemetry.md`. Nothing to kill-switch — there is no behavior
change anywhere in the loop, only reads. The checker failing preflight on a
registry referencing an unknown reason value is the only enforced gate, and
it fails closed at PR time, not in production.

## Open questions

- Attribution across two moving boundaries: a week where both a backend fix
  and an app update ship can attribute the same improvement twice. The
  registry's one-line `notes` plus `owner` field is the honest first tool;
  is a formal conflicts rule (earliest boundary wins) worth encoding, or is
  it over-engineering for a registry that will hold tens of entries?
- Should `verdict` thresholds be per-reason (a `recording_*` class with tiny
  volume needs different n than `too_verbose`) — likely yes at implementation
  time, defaulted from the observed per-reason daily volume in `detect`-style
  fashion rather than guessed here.
- Prompt-level fixes (`prompt_commit` boundaries) churn faster than release
  boundaries; does the registry want a `kind: hotfix | prompt | release`
  distinction for review triage, or is `owner` enough?
