# Dream reads the owner's feedback ledger

Part one of the self-reporting loop (`dream-feedback-remediation.md`,
`agent-defect-reports.md`, `feedback-postmortem.md`,
`agent-failure-telemetry.md`, `feedback-fix-effectiveness.md`). Design only —
no code in this change.

## Problem

The owner's thumbs-down lands in the product feedback ledger and then waits
for a human to read the daily report. Every capability needed to *act* on that
signal already exists in the Dream agent — retire, merge, supersede, correct,
close — but Dream never sees the signal. Dream's only feedback input today is
its own Undo receipts: `utils/dream_seed.py` builds `recent_feedback` from
`review_changes` rows where `change.undone` is true. The owner saying "this
memory is wrong" (memory discard), "this summary is inaccurate"
(`summary_inaccurate`), or "already done" (`already_done` on a task
notification card) is invisible to it.

This document designs the wiring: which ledger rows Dream may ingest, what each
reason class maps to, what rate limits apply, and what happens on conflicting
signals.

## Current state

The ledger (`models/feedback.py`, `database/feedback.py`):

- `feedback_events` — one append-only row per rating action, shape
  `FeedbackEvent`: `uid`, `surface`, `target_kind`, `target_id`, `value`
  (-1/0/1), `reason`, coordinates (`chat_session_id`,
  `target_created_at`), and provenance (`app_version`, `prompt_name`,
  `prompt_commit`, `langsmith_run_id`, `backend_release`, …).
- Surfaces (`FeedbackSurface`): `chat_text`, `chat_voice`,
  `conversation_summary`, `chat_notification`, `memory`,
  `recording_quality`. Target kinds (`FeedbackTargetKind`): `chat_message`,
  `conversation`, `memory`, `recording`.
- Two reason taxonomies, deliberately kept apart: `FeedbackReason` (the five
  mobile chat reasons plus five desktop notification-card reasons:
  `not_about_me`, `already_done`, `wrong_facts`, `bad_timing`, `not_useful`)
  and `MobileFeedbackReason` (`summary_*`, `recording_*`).
- Writers: `record_chat_message_feedback` (`utils/feedback.py`, called from
  `routers/chat.py`, `routers/chat_sessions.py`, `routers/users.py`),
  `record_memory_feedback` (`routers/memories.py`
  `POST /v3/memories/{memory_id}/review` — the discard also flips
  `user_review` on the memory document itself), and the idempotent mobile
  path `database/feedback.py:record_feedback_event_idempotent`
  (`routers/mobile_feedback.py`).
- The only negative-event read that exists today is the global daily-report
  query `NEGATIVE_FEEDBACK_EVENTS_QUERY`
  (`database/firestore_index_registry.py`, identifier
  `feedback_events_negative_by_created_at`): `value == -1` ordered by
  `created_at`, no uid filter.

Dream (`utils/dream_agent.py`, `config/dream_agent.py`,
`utils/agent_capabilities/`):

- One bounded session per admitted owner (`run_pass` → `run_session`), six
  tools (`models/agent_tools.py` `TOOLS`: `search`, `read`, `propose_edit`,
  `ask`, `learn_term`, `finish`).
- Capability kinds (`utils/agent_capabilities/registry.py` `KINDS`) include
  `retire_memory`, `supersede_memory`, `merge_memories`, `title`, `overview`,
  `spelling`, `close_task`, `retire_task`, `merge_conversations`,
  `dismiss_person`, `merge_people`, `vocabulary`.
- Proposals flow propose → two independent verifiers (`utils/dream_verify.py`)
  → auto-apply or Review queue (`utils/dream_review_policy.py`
  `suggest_edit`/`ask` → `database/review_store.py
  enqueue_review_proposal`). Review items already carry a `dream_origin`
  marker and a `dream_suggestions` daily budget
  (`config/dream_agent.py SUGGESTIONS_PER_DAY = 3`).
- Search reads exactly four collections (`models/agent_tools.py`
  `Search.collections`): `conversations`, `memory_items`, `action_items`,
  `people`. **Chat messages are not readable by Dream.** The rated turn's text
  is reachable only through the admin context endpoint
  (`routers/feedback_admin.py` → `utils/feedback_context.py
  hydrate_context`), which Dream must not call.
- Seed budget: `utils/dream_seed.py` caps the serialized seed at 8,000 bytes
  (empty/light) or 24,000 (medium/heavy) with ordered eviction.

What does not exist: any path from `feedback_events` into a Dream seed,
proposal, or Review item.

## Proposed design

### Ingestion

Dream's seed gains one section, `negative_feedback`, built in
`utils/dream_seed.py` next to `targets`. Each entry is a pointer, not content:

```json
{"event_id": "…", "surface": "memory", "reason": null,
 "target_ref": "memory_items/…", "chat_session_id": null,
 "event_created_at": "…", "value": -1}
```

Query: new registry spec `feedback_events_negative_by_uid_created_at`
(uid equality + `value == -1` + `created_at >=` last completed pass), sibling
of `NEGATIVE_FEEDBACK_EVENTS_QUERY`, declared in
`database/firestore_index_registry.py` per the Firestore guide
(`.github/agent-docs/firestore-queries-and-indexes.md`) before the
first deploy. Rows resolve to `target_ref` through the same
`target_kind`/`target_id` mapping the report uses; `chat_message` targets
carry no resolvable ref for Dream and keep only their coordinates.

Caps: at most 8 entries per seed, newest first, inside the existing byte
ceiling (the `append`/eviction machinery needs no change; `negative_feedback`
joins the eviction order after `previous_notes`). A pass that hits the cap
marks the seed `negative_feedback_truncated: true` so the instructions can say
"more exist; do not treat the list as exhaustive".

### Reason → capability mapping

Dream proposes only what it can ground in records it can already read. The
mapping is therefore per *surface*, and the honest answer for several reason
classes is "no capability — report, don't mutate":

| Ledger signal | Dream action | Kind |
|---|---|---|
| `memory` discard (value -1 on `/v3/memories/{id}/review`) | Hunt sibling failures: same source conversation or near-duplicate content among unreviewed memories; propose retiring/merging those — the maintenance job already owns a rejected-memory hunt query to model this on (`RECENT_REJECTED_MEMORY_FEEDBACK_QUERY`, `database/firestore_index_registry.py`). The discarded memory itself is already gone from the product's view — never re-propose it. | `retire_memory`, `merge_memories` |
| `conversation_summary` + `summary_inaccurate` / `summary_wrong_context` | Re-read the conversation transcript (already a readable collection) and propose a corrected `overview`/`title` where the summary contradicts captured speech. | `overview`, `title` |
| `conversation_summary` + `summary_incomplete` | Propose an `overview` extension only when the transcript contains a listed, datable item the summary omitted. | `overview` |
| `chat_notification` + `already_done` | The card's underlying task is findable via the rated message's coordinates → `action_items` search; propose completing it. | `close_task` |
| `chat_notification` + `wrong_facts` / `not_about_me` on a memory card | Locate the memory and propose retire/supersede against captured speech. | `retire_memory`, `supersede_memory` |
| `recording_quality` + `recording_fragmented_or_duplicated` | Propose linking the duplicate captures. | `merge_conversations` |
| `chat_text`/`chat_voice` + `didnt_follow_instructions`, `too_verbose`, `incorrect_or_hallucination`, `not_helpful_or_irrelevant` | **No mutation.** The rated turn is unreadable by Dream and no capability edits chat behavior. These rows are marked consumed-for-reporting and left to the post-mortem (`feedback-postmortem.md`) and the fix registry (`feedback-fix-effectiveness.md`). | — |

This is the main deviation from the idea as pitched, which suggested
`didnt_follow_instructions` → "spelling/vocabulary edit". Vocabulary and
spelling fixes are grounded in *captured speech*, not in chat instructions;
the only case where the mapping is real is a `didnt_follow_instructions` row
whose comment or follow-up turns show a misrecognized name — and the follow-up
turns are chat text Dream cannot read. Forcing the mapping would produce
ungrounded proposals, which the verifier layer would (correctly) reject.

### Disposition of each entry

The instructions (`utils/dream_instructions.py`) gain one rule block: every
seeded `negative_feedback` entry ends the pass in exactly one of three
recorded states — `proposed` (an edit/question citing the event id in its
reasoning), `no_action_grounded` (searched, nothing defensible), or
`not_actionable` (reason class with no mapping). `finish` already requires
reporting tool-reported outcomes; the run report (`dream_store` run document)
gains a `feedback_dispositions` counter keyed by state. An entry is never
silently dropped.

### Conflicting signals

- **Ledger-internal races** (bare tap vs. reasoned chip arriving out of
  order): collapse per target with the report's existing rule —
  `jobs/feedback_daily_report.py _collapse_per_target` /
  `_is_more_informative` (a reasoned row beats a bare one; ties break on
  `created_at`). Dream collapses the same way before seeding.
- **Thumbs-down then thumbs-up on the same target**: the collapse keeps the
  most informative *negative* row, so re-derive at seed time from all rows in
  the window; if the latest event for a target is non-negative, the target
  drops out entirely. Append-only means both rows stay in the ledger; Dream
  reads state, not history.
- **Feedback vs. Dream's own prior work**: if the target already has a
  pending Review proposal with the same `edit_key`
  (`review_store.enqueue_review_proposal` returns `already_suggested`), the
  entry is dispositioned `proposed` with no new item — the signal is already
  pending owner judgment.
- **Feedback vs. Undo**: an auto-applied feedback-derived edit that the owner
  undoes demotes exactly as today (`dream_store.demoted_types` drives
  `auto_apply_kinds(uid) - demoted`), and the undo receipt keeps the
  `feedback_event_id` provenance below so the demotion is attributable to
  feedback-sourced work in aggregate.

### Rate limits

No new knobs. Feedback-derived proposals compete inside every existing
ceiling: `SUGGESTIONS_PER_DAY = 3` Review attention slots, the per-pass
`offered[:3]` top-by-value cut, `Caps.edits = 25`, pass/admission budgets,
and verifier capacity. A feedback-derived proposal is not special at the
effect boundary, which is the point: the fences that make Dream safe exist
 upstream of any input source. The only feedback-specific bound is the seed
 cap (8 entries), which limits how much of a bad day can chase the owner into
 Review.

### Provenance

`suggest_edit`/`ask` accept an optional `feedback_event_id`; when present,
the Review item's `source` dict records it next to `dream_origin`
(`database/review_store.py` already stamps `dream_origin: true`). This is the
hook `feedback-fix-effectiveness.md` uses to measure whether feedback-derived
proposals survive owner review.

## Data-model deltas (proposed, not implemented)

- `database/firestore_index_registry.py`: one new query spec,
  `feedback_events_negative_by_uid_created_at`.
- `utils/dream_seed.py`: new seed key `negative_feedback` (+ truncation
  flag). No persisted schema change — the seed is rebuilt per pass.
- Review item `source`: optional `feedback_event_id` string field; read-side
  tolerant of its absence.
- Run report dict: `feedback_dispositions` counter. Counts only, per the
  Dream telemetry rule (no refs, no content in metrics).

## Privacy stance

Dream is owner-scoped and ingests only its own owner's rows — the new query
filters `uid` first. The ledger row is itself the pointer: it contains no
conversation text, and Dream never resolves chat-turn text for it. Proposal
evidence must come from records Dream can already read under the existing
`reads.py` visibility boundary; a proposal whose only evidence is a feedback
row is invalid by construction (`propose_edit` requires read records).
Free-text comments on events are **not** seeded — `comment` can hold user
text and stays out of the model's context unless a future design puts it
behind an explicit gate.

## Rollout and kill switch

`DREAM_AGENT_ENABLED` + the operator document `dream_control/global.enabled`
already gate admission, dispatch and effects; ingestion inherits both and
needs no separate kill switch to go dark. For graduated rollout, one config
flag `DREAM_FEEDBACK_INGEST_ENABLED` (default `false`, registered per
`backend/docs/feature-flag-registry.md`) gates only the seed section, so the
capability can ship dark and ride the existing `dream-agent` rollout cohort
(`config.rollout_cohorts`) before `all`. Verification of the mapping needs no
new machinery: the two-verifier pass and the canary
(`backend/scripts/dream-replay.py`, synthetic owner) already exercise
grounding; a replay fixture with a seeded feedback row is the acceptance
test.

## Open questions

- Should `chat_notification` rows with `bad_timing`/`not_useful` feed
  notification-ranking (a scheduler signal) rather than Dream at all? They
  describe *when*, not *what* — no capability addresses timing.
- Is 8 seed entries per pass right for a heavy owner who mass-discards
  memories after a bad extraction day? The daily cap of 2 passes bounds the
  follow-through either way.
- When a `conversation_summary` fix is auto-applied and the summary later
  regenerates from the same transcript, does the regeneration respect the
  applied `overview` fence or does the feedback loop repeat? Needs a check
  against summary-source invalidation before this mapping goes live.
