# Explicit reminders: first slice

LIFECYCLE: permanent

Implements the proposal's **Smallest first slice behind a kill switch**, with the
relevant **One extractor, explicit intent and evidence**, **Remind me dates and
notification behavior**, and creation-only **Durable origin and mutation contract**
boundaries. PR #24415 already owns the general legacy/V2 reminder, errand and
current-session-command prompt safeguards. This slice does not copy those edits.

The existing notes call emits a typed reminder claim and the exact spoken date
expression. No second extraction/classifier call is added. Deterministic checks
require cited turns, direct reminder intent, and grounded date text. They may
reject or retain review work; they cannot invent a task omitted by notes.

The existing desktop staged workflow owns ingress, generation/deletion fences,
Candidate expiry, semantic claims, acceptance and integration outbox delivery.
Acceptance remains a separate explicit gesture. An unresolved speaker is a
pending review Candidate, with zero ownership confidence and a review label;
acceptance confirms that the owner wants that task. The `speaker_evidence` adapter
consumes existing source-role decisions and is the only identity seam. It never
promotes a bare `is_user`, name or cluster number into identity.

`due` distinguishes none, local date, explicit instant and unresolved expression.
Date-only reminders keep `due_at=null`; there is no notification hour or scheduling
intent. Web task rows/cards and note next steps render the all-day date; grouping
uses that date's IANA timezone. Old clients can ignore additive fields: due_at is explicitly null in storage
and on the wire, and notes carry the date in their existing context field.
Owner-editable task descriptions stay exact. A legacy date edit clears
old precision; owner edits and completion survive extraction replay.

Dates use the recording's source timestamp plus cited offsets and
`capture_timezone`, an optional source input persisted with CreateConversation.
The current account timezone is never used as capture-time evidence. Existing
producers/legacy rows without this evidence retain an unresolved expression.
The bounded first grammar supports ISO dates/times, English month/day (including
ordinals and omitted years), today and tomorrow. Unsupported or ambiguous wording
needs review. DST gaps/folds need a valid explicit offset. Delayed extraction
preserves an overdue explicit date. Date/instant interpretation is not model recall.

Reminder Candidates store source/extraction time, input and speaker-evidence
revisions, policy revision and immutable exact source refs. Retry keys include
source revisions, while semantic claims coalesce repeated supporting reminders
within the same conversation and due precision. Equal descriptions in unrelated
conversations/days do not merge. Cross-device common-event/alias authority remains
with the separate segmentation work; this slice never guesses event identity.

Acceptance commits the task, a creation-only actor receipt on both the retained
Candidate and task, and the existing integration outbox together. Receipts contain
field/status metadata and evidence refs, no task content. They attribute the
separate acceptance to the authenticated owner, with conversation as source.
History coverage is `reminder_creation_only`. Manual, import, integration, MCP and
other task writers do not gain mutation receipts in this slice; historical
completers remain unknown. This is not completion-history migration.

## Kill switch and handoff

`ACTION_ITEM_REMINDER_REDESIGN_ENABLED` is **on by default**; `false` removes the
new notes instructions and stops reminder validation/admission before Candidate
writes. Already-created tasks, manual state, due precision and receipts remain
readable. Dispatch checks stop only undelivered outbox intents tagged
`explicit-reminders-v1`, including claimed work before provider attempt. Delivered
or ambiguous provider outcomes retain the existing reconciliation contract.
No task, date or history is deleted/reset. There is no new UID or memory gate.

The task integration lane owner owns rollout; the lead owns explicit release
approval. Before release: qualify with synthetic/consented labels, then a full
24-hour side-effect-free shadow window on existing notes output, without extra
paid calls. Use the existing workflow/cohort authority for consenting dogfood,
then 1%, 10%, 50%, 100% of eligible traffic, with a full 24-hour window and at least
100 labeled reminders at each step. Gate on >=95% reminder recall, >=99% accepted
precision, 100% deterministic date correctness, zero wrong-owner/quoted/current
command autoaccepts and zero duplicate exports/notifications. Measure vendor and
cloud costs; zero extra extraction calls is the call budget. Report uncertainty.
Review expansion within 48 hours of passing evidence and escalate a cohort stuck
seven days. Any wrong owner, invented instant, duplicate delivery or overwritten
manual state stops expansion. Guards arm only after the new state's full window.
No rollout, model score or live result is established by this PR.

Broad call inference, labeled waiting-on lists, the legacy/V2 promises difference,
completion/history migration, all-writer receipts, source alias resolution, summary
refresh, and speaker identity are outside this slice. The legacy/mobile automatic
writer cannot consume new reminder claims: that would bypass staged acceptance.
