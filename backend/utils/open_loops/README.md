# Open loops (PR 1: extraction + card writer)

Open loops are follow-ups the account owner may later be asked about ("did it
happen?"): what the owner delegated, what others committed to the owner, the
owner's own commitments going stale, plus one narrow observed work defect or
errand blocker. This PR extracts them in the existing notes call, persists
them server-only, and provides the deterministic review-card writer. The
daily pass, loop store with expiry, task-aware dedupe and Review surfacing
arrive in later PRs.

## Modules

- `prompts.py` — `OPEN_LOOP_EXTRACTION_RULES`, appended to the one-shot notes
  instructions while `OPEN_LOOPS_ENABLED` is on (default on; `config/open_loops.py`).
  The rules never touch the action-item rules.
- `extraction.py` — the mutable sink contract plus the persistable payload
  shape; `capture_into_sink` is the only writer.
- `card.py` — `build_card` (deterministic template, no model) and
  `build_review_card` (same interface, optional single polish call behind
  `OPEN_LOOPS_CARD_POLISH_ENABLED`, default off, feature key `open_loop_card`
  on gpt-5-nano with usage tracking). A card must be self-contained: names who
  and what in recognizable words, says which conversation and weekday it came
  from, and why now ("due Monday", "no follow-up since Tue"); question +
  context stay within ~180 characters, with no internal jargon and no
  relationship/medical/legal inference. Any polish failure keeps the template.

## Storage contract

The extractions persist as `open_loop_extractions` on the conversation
document — a top-level server-only field like `relevance_decision`, never on
the `Conversation` client wire model (the pydantic model filters it on every
read path). `database/conversations.py` protects it through
`_prepare_conversation_for_write` exactly like `user_corrections`: compressed,
and encrypted for enhanced-protection users, with the
`open_loop_extractions_compressed` marker. The only intended reader is
`database.conversations.get_open_loop_extractions`.

Write semantics from conversation processing:

- Fresh notes parse with content → the payload dict (`version`, the three
  fields).
- Fresh notes parse with nothing → an explicit `null`, so a reprocess clears
  a stale prior value.
- Dedupe reuse, quiet-minimum, or the switch off → the field is omitted, so a
  Firestore merge keeps any previously stored value.

## Schema placement

The fields live on subclasses (`OpenLoopNotesOutput`,
`OpenLoopStructuredExtraction`, `OpenLoopAgentNotesSubmission`) selected only
while the switch is on, following `RichStructuredExtraction`: the base-schemas'
format instructions are embedded in the shared static prompt, so the flag-off
prompt bytes must not change. Known gap: the agentic lane's hand-written
`submit_notes` tool does not request these fields yet, so agent-written
meetings currently extract none.

## Tests

`tests/unit/test_open_loops_schema.py` (parsing/back-compat),
`test_open_loops_prompt_gating.py` (kill switch),
`test_open_loops_persistence.py` (write shape, server-only wire),
`test_open_loops_card.py` (card writer cases).
