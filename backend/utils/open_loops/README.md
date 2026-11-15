# Open loops (PR 1: extraction + card writer; PR 2: daily pass + loop store)

Open loops are follow-ups the account owner may later be asked about ("did it
happen?"): what the owner delegated, what others committed to the owner, the
owner's own commitments going stale, plus one narrow observed work defect or
errand blocker. PR 1 extracts them in the existing notes call, persists them
server-only, and provides the deterministic review-card writer. PR 2 adds the
per-user loop store with expiry, the daily pass over the recap job,
task-aware dedupe and deterministic ranking — the cards are stored but not
served yet; Review surfacing and the mobile UI arrive in PR 3.

## Modules

- `prompts.py` — `OPEN_LOOP_EXTRACTION_RULES`, appended to the one-shot notes
  instructions while `OPEN_LOOPS_ENABLED` is on (default on; `config/open_loops.py`).
  The rules never touch the action-item rules. `OPEN_LOOPS_DAILY_RULES` is the
  daily pass's system prompt, adapted from the offline-validated merged daily
  prompt (2026-10-26 blind labels: 94% right items, 47% unreadable without
  context, stand-in dedupe wrongly dropped 7/12 wanted cards, 2–3 slots/day).
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
- `store.py` — pure domain rules: stable-key identity (normalized
  who+what+kind), expiry windows (no signal: 7 days default, own_commitment
  10, owed_to_user 14; terminal docs deleted after 14 more days; open-store
  cap 60), loop/task matching (token overlap requiring **both** Jaccard ≥ 0.6
  and containment ≥ 0.8, and the same `who` when both sides name one — the
  documented seam a Jev-based matcher replaces via `find_task_match`),
  duplicate merging (same normalized `who`, Jaccard ≥ 0.7 **and** containment
  ≥ 0.8; a task-linked survivor beats a plain one; a matching task is linked,
  never dropped), terminal-loop protection (resolved/dropped/expired loops
  never update, merge or revive; the same follow-up opens a new loop only
  after `REMENTION_COOLDOWN_DAYS` = 14), the two-day re-ask cooldown
  (re-armed by due_soon), snoozes, and the slot ranking (value ≥ 3, due_soon
  first, work first, at most 3).
- `daily.py` — the daily pass: one structured call per user per local day
  (feature key `open_loop_daily`, gpt-6-luna, usage-tracked), fail-open and
  **off the recap critical path**: the recap worker finishes summary, push,
  backfill and webhook first and only returns a pass request, which the
  coordinator dispatches onto the dedicated `open_loops_executor` under
  `OPEN_LOOPS_PASS_BUDGET_SECONDS` (45 s) — a slow or failing pass never
  spends recap budget, delays the webhook or counts toward recap
  timeouts/abandoned users (`utils/other/notifications`). The day is rendered
  with the recap's own deserializer, char budget and renderer — the same view
  of the day, not a byte-shared prompt prefix — and leads the prompt; the
  JSON state (extractions, ≤20 carried loops, ≤40 open tasks, the day's
  recap) follows. The model proposes statuses/resolutions/rankings;
  deterministic post-processing decides, with defensive caps on the model
  output (`MODEL_LOOPS_CAP`, ≤3 surface entries). Before the model call an
  atomic per-day claim (`open_loop_claims`, create-if-absent, ≤2 attempts)
  makes retried ticks, abandoned workers and the locked-retry path pay at
  most once; the per-day cards document still marks the day as run.
  `OPEN_LOOPS_ENABLED` off or a no-signal day (no extractions and no open
  loops, or no conversations and nothing due soon) spends nothing.
- `service.py` — the PR 3 Review source functions: `list_pending_cards`
  (defaults to the recap's most recently completed local day — the recap's
  noon-split rule) and `answer_card` (done → resolved, plus task completion
  **only** through a strong link — `task_link='model'` (the model asserted
  `from_task_id`) and the answered card's text actually naming the task; the
  completion goes through the app's own path, `mark_action_item_completed` +
  reminder reconciliation #5085. Heuristic links stay ask-only: Done resolves
  the loop, never the task; remind → snooze +2d in the user's timezone; drop
  → dropped + negative example kept on the loop). No route serves them yet.

## Storage contract

### Extractions (PR 1)

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

### Loop store + cards (PR 2)

- `users/{uid}/open_loops/{loop_id}` — one document per loop; the whole loop
  dict is one derived JSON blob, zlib-compressed and AES-encrypted for every
  user (conversation quotes ride the enhanced-protection shape
  unconditionally), plus a plain `status`/`last_activity_at` triage mirror.
  Loop ids are stable keys (`ol-<hash>`), or `task-<task_id>` for task-linked
  loops. The collection is streamed whole and filtered in code — no queries,
  no new indexes; expiry, terminal retention and the open cap keep it small.
- `users/{uid}/open_loop_cards/{date}` — the local day's surfaced cards
  (state pending|done|remind|dropped), same protection. Its existence — even
  with an empty list — marks the pass as run for that day.
- `users/{uid}/open_loop_claims/{date}` — the plain, tiny spend guard for the
  pass: claimed atomically (create-if-absent) before the model call, `state`
  claimed|ran|failed, `attempts` ≤ 2 (one genuine retry after a failure; a
  stale claim from an abandoned worker may be taken over after 10 minutes).

The daily pass skips merge-donor conversations (`sync_merged_into`), locked
and discarded rows, and rows the recap's own eligibility rule excludes from
derived consumers.

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
`test_open_loops_card.py` (card writer cases),
`test_open_loops_store.py` (identity, expiry, dedupe, cooldown, ranking,
encrypted store roundtrip),
`test_open_loops_daily.py` (pass guards, ingestion, linking, slots, claims,
terminal-loop cool-off),
`test_open_loops_service.py` (answer transitions incl. strong-link-only task
completion),
`test_open_loops_recap_integration.py` (post-recap dispatch, pass budget,
fail-open),
`test_open_loops_replay.py` (70-day synthetic replay: bounded store, resolved
loops stop surfacing).
