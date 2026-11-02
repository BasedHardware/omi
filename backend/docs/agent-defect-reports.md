# Agent defect reports (harness self-reporting)

Part two of the self-reporting loop (`dream-feedback-remediation.md`,
`agent-defect-reports.md`, `feedback-postmortem.md`,
`agent-failure-telemetry.md`, `feedback-fix-effectiveness.md`). Design only —
no code in this change.

## Problem

When a harness session fails its owner quietly — retrieval returned nothing
useful, a tool errored, the data it read was ambiguous, the capability it
needed does not exist — the failure is invisible unless the owner bothers to
thumbs-down, and even then the *cause* is only knowable to the agent that
experienced it. The user-facing ledger (`models/feedback.py`) records verdicts
about outputs; nothing records the agent's own account of what went wrong.

This document designs the agent→system reporting direction: a structured
defect report the harness can file during a session, with evidence as refs
never text, reaching both an owner-scoped store (for the post-mortem and
Dream remediation loops) and the existing k-anonymized developer-pattern
store.

## Current state — most of this already exists

The surprising finding is that the payload, the privacy gate, and the
aggregation are all built; only the tool is missing.

- `models/dream_agent.py Feedback` — the historical anonymous feedback
  payload: closed enums `component` (`transcription`, `notes`, `memory`,
  `people`, `entities`, `tasks`, `dream`), `failure_class` (`spelling`,
  `duplicate`, `missing_evidence`, `stale_state`, `routing`, `budget`,
  `success`, `none`, `ok`), `severity` (`info`, `warning`, `error`), plus
  `count`, `latency_ms`, `error_rate`, and a `reproduction` string ≤ 500
  chars. Its docstring says "planning lives in dream_harness".
- `database/dream_feedback.py` — the full privacy pipeline:
  `validate()` (via `utils/agent_capabilities/guards.py
  feedback_rejection`) rejects quoted input, storage ids, uid strings and
  vocabulary/name overlap using n-gram checks across field boundaries;
  `store()` writes epoch-scoped (`%G-W%V`) rows keyed by an HMAC'd
  `distinct` (salt: `DREAM_AGENT_FEEDBACK_SALT`, ≥ 32 chars) and a pattern
  hash — uid never in path or payload; `aggregate()`/`read_patterns()` publish
  only groups with ≥ k distinct users (`Caps.anonymous_k`, default 20, env
  `DREAM_AGENT_FEEDBACK_K`).
- `utils/dream_report.py project_run` already projects
  `proposed.feedback` rows (`component`, `failure_class`, `severity`,
  `count`) into the owner-facing run report (`models/dream_report.py`).
- What does **not** exist: no tool in `models/agent_tools.py TOOLS` produces
  a `Feedback`; `run_session`'s `report['proposed']` has keys only for
  `edits`/`questions`/`vocabulary`; `dream_feedback.store` has no production
  caller (tests only: `backend/tests/unit/test_dream_guards.py`,
  `test_dream_quality.py`).

Separately, the deterministic half of this idea is already measured
server-side and should stay there:

- Tool rejections: `session.rejections` lands in the run report as
  `rejected` with `tool_counts` (`utils/dream_agent.py`).
- Search degradation: `utils/agent_capabilities/search.py` counts
  `failed_paths` and calls `record_fallback(component='agent_tools',
  from_mode='agent_search', to_mode='remaining_paths', …)` per the fallback
  telemetry contract (`.github/agent-docs/fallback-telemetry.md`).
- Chat-lane tool failures: `utils/retrieval/agentic.py _execute_tool`
  fails a `ClientJourneyAttempt` for memory-retrieval tools; the broader
  counter coverage is `agent-failure-telemetry.md`'s subject.

## Proposed design

### One tool, judgment classes only

A new harness tool `report_defect` joins `TOOLS` in `models/agent_tools.py`
alongside `ask` and `learn_term`:

```python
class ReportDefect(Strict):
    component: Literal['retrieval', 'tools', 'data_quality',
                       'capability_gap', 'instructions', 'other']
    failure_class: Literal['retrieval_miss', 'tool_error', 'ambiguous_data',
                           'capability_gap', 'instruction_conflict',
                           'other']
    severity: Literal['info', 'warning', 'error']
    evidence: list[str]          # owner refs the session already read, ≤ 4
    detail: str                  # ≤ 300 chars, gated like Feedback.reproduction
    count: int = 1               # occurrences this session, ≤ 100
```

`retrieval_miss` and `tool_error` are accepted from the model only as
*corroborated* claims — the session cross-checks them against
`session.rejections` / search `counts.failed_paths` and stamps
`corroborated: false` when the counters show no such failure. An
uncorroborated defect report is still stored, flagged; the model blaming its
tools is a known failure mode and the flag is cheaper than suppressing the
report. `ambiguous_data` and `capability_gap` — the classes only the model
can judge — need no corroboration.

Naming deviation from the pitch: the brief proposed `agent_self_report`.
"Self-report" is already taken in this codebase —
`config/dream_agent.py self_report_enabled()` gates the owner-facing Dream
run report (`utils/dream_report.py require_owner`, `GET /v1/dream/runs`).
Reusing the word for a second concept in the same package is a support
incident waiting to happen; the tool is `report_defect` and the mechanism is
"agent defect reports" throughout.

### Deviation from the pitch: not a FeedbackSurface

The brief proposed a new `FeedbackSurface` value plus agent-specific reasons
in the product ledger. That shape conflicts with the ledger's design on two
points:

1. `feedback_events` rows are *user verdicts about outputs* — the daily
   report query is `value == -1` over user ratings, and
   `models/feedback.py` deliberately keeps each surface's reason taxonomy
   undiluted (the desktop notification reasons were "added alongside the
   mobile five rather than folded into them"). Agent self-assessments are a
   different speech act with a different trust level; mixing them in makes
   `counts_by_reason` meaningless and doubles the "negative feedback" the
   report claims to count.
2. The ledger's target kinds point at user-visible artifacts. A defect
   report's evidence is *refs the agent read*, and its subject is the
   agent's own process — there is no honest `target_kind` for it.

Instead: a separate owner-scoped collection `agent_defect_reports`, document
id uuid4, shape mirroring the ledger's envelope discipline (ids and enums,
no content):

```
uid, agent ('dream' | 'chat'), run_or_session_id, created_at,
component, failure_class, severity, count, corroborated,
evidence_refs[]   # validated owner refs; chat sessions excluded (below)
detail            # stored ONLY if it passes the dream_feedback.validate() gates
```

The write path is best-effort like `record_feedback_event` (never fails the
session), rate-capped at 5 reports per session (a session flooding defect
reports is itself a defect — the cap breach is logged as a counter).

### Two destinations

- **Owner-scoped copy** (`users/{uid}/agent_defect_reports`, encrypted like
  other owner data via the `database/helpers.py` read/write decorators):
  consumed by the post-mortem run (`feedback-postmortem.md`) and surfaced in
  the Dream run report next to the projected `feedback` rows that
  `utils/dream_report.py` already renders.
- **Developer copy** (existing `dream_feedback` collection, unchanged):
  `database/dream_feedback.store()` with the defect's enums and the gated
  detail text. Read through `read_patterns()` (k ≥ 20, epoch-scoped). The
  `component`/`failure_class` enums need widening to cover the new classes —
  `Feedback`'s enums describe pipeline components; defect reports describe
  harness failure modes. Proposal: keep `Feedback` as-is for the legacy
  payload and let `store()` accept the defect enums too, deriving the stored
  `pattern` hash from whichever enum pair it was given.

### Where it sits in the harness contract

`report_defect` is a *report*, not an effect: it stages nothing, applies
nothing, and does not cross the verification boundary
(`utils/dream_verify.py` verifies staged edits and questions; there is
nothing to verify here — the corroboration stamp is the integrity check).
Like `finish`, it is counted (`session.counters['tool:report_defect']`) and
bounded. Chat mounting later reuses the same schema; the `agent` field keeps
the copies distinguishable. Evidence refs must be refs the session already
`read` or `search`-granted — the session's seen-refs set enforces this the
same way `learn_term` grounds vocabulary.

## Data-model deltas (proposed, not implemented)

- `models/agent_tools.py`: `ReportDefect` model + `TOOLS` entry.
- `models/dream_agent.py` or a sibling: defect-report enums (or widen
  `Feedback`).
- New collection `users/{uid}/agent_defect_reports`; no changes to
  `feedback_events`, `FeedbackSurface`, or `FeedbackReason`.
- `dream_feedback.store()`: accept defect-report payloads.

## Privacy stance

The pointer rule is inherited, not reinvented: evidence is refs (already
enforced against the session's seen-refs), and the free-text `detail` may
leave owner scope only through `dream_feedback.validate()` — the gate that
already rejects quoted input, storage ids, uids and vocabulary overlap. The
owner-scoped copy may hold refs and gated text but never decrypted record
bodies. Chat-turn refs are excluded from evidence entirely: the same
"chat messages are not agent-reportable artifacts" rule as
`dream-feedback-remediation.md`.

## Rollout and kill switch

The tool ships inert: `TOOLS` declarations reach the model only through a
session's toolset, so mounting it for Dream first (chat later) is the
rollout. A per-agent config flag (`DREAM_DEFECT_REPORTS_ENABLED`, default
`false`, registered in `backend/docs/feature-flag-registry.md`) gates the write path
so a chatty model cannot fill storage while the consumers
(`feedback-postmortem.md`, `feedback-fix-effectiveness.md`) do not yet
exist. The developer copy rides the existing salt/k-anon requirements —
if `DREAM_AGENT_FEEDBACK_SALT` is unset, `store()` already refuses, and the
owner-scoped copy is unaffected. Kill switch order: unset the flag (stops
new reports), then the retention TTL below cleans up.

Retention: owner-scoped reports carry a 90-day TTL (consistent with review
receipts' 30-day Undo window times review latency; post-mortems consume them
within a day, so 90 days is generous headroom).

## Open questions

- Should `chat` sessions get the tool in the same PR as Dream, or only after
  the Dream copy proves non-noisy? The corroboration stamp only exists where
  session counters do — chat sessions have thinner counters.
- Is 300 chars of `detail` worth storing owner-scoped at all, given refs +
  enums already drive the post-mortem? The post-mortem may prefer deriving
  its own narrative from evidence and treat `detail` as optional.
- Do `capability_gap` reports deserve a direct escalation path into the fix
  registry (`feedback-fix-effectiveness.md`) rather than waiting for
  aggregate thresholds?
