# Episodes (`utils/episodes`)

An episode is one occasion of the user's day (a meeting, a dinner, a work
session) as the mobile app shows it: a live row on Home while it is happening,
a live detail page with running notes, and the conversation detail once it is
over. It is a presentation and processing overlay over existing conversations.
It never rewrites, merges or deletes a conversation, and never writes a task or
a memory. Not to be confused with the notes pipeline's "episode evidence"
(`utils/conversations/episode_*.py`, `utils/llm/episode_*.py`), which is about
one capture window's evidence.

## Units

- **Conversation**: unchanged. Live capture still splits on silence, finalization
  jobs, leases, smart merge and per-conversation processing keep their contracts.
- **Moment**: a stretch of speech inside a conversation. It ends on a pause
  (`MOMENT_PAUSE_SECONDS`), a word-budget rollover (`MOMENT_MAX_WORDS`), a move to
  another conversation, or the conversation's finalization.
- **Episode**: the moments and conversations of one occasion, with a compact
  state: topic, running bullets, people, open questions and provisional items.

## Flow

1. `live.py` sees every batch of final segments through
   `utils.app_integrations._async_trigger_realtime_integrations` (pusher, or the
   listen fallback) and buffers them per user in process (TTL + size cap).
2. When a moment ends, `service.record_moment` runs on `postprocess_executor` as
   a tracked background task:
   - **Boundary** (`policy.boundary`): the hard cap (`MAX_EPISODE_SECONDS`), a gap at
     or above `CLOSE_GAP_SECONDS`, and two different calendar events close
     deterministically. An overlapping capture from another device continues and
     adds a source without feeding its text twice. A gap of at least
     `CONTINUE_GAP_SECONDS`, or a device change, asks Jev
     (`incremental.ask_same_occasion`, lane `episode_boundary`) from the compact
     state, the gap, the device and the voice-set change. Only a confident
     "moved on" (`MOVED_ON_THRESHOLD`) closes. No answer falls back to the cheap rules.
   - **One cheap update** (`incremental.run_incremental_update`, feature
     `episode_incremental`, gpt-5-nano): the previous compact state
     (`state.render_state`, at most `MAX_STATE_CHARS`) plus only this moment's
     new text. The earlier transcript is never re-read. The fixed instruction
     prefix comes first and the clock, state and new speech come last.
   - **Compare-and-swap store** (`database/episodes.py`): speech-derived fields are
     sealed with the user's key. A lost race retries once.
3. After a conversation's finalization job completes,
   `utils/conversations/finalizer.py` calls `service.on_conversation_finalized`
   (bounded, fail-open, after `complete_finalization_fanout`):
   - It applies trailing text the live stream never delivered (dedupe by the
     per-conversation applied offset).
   - It repoints a smart-merge donor to its survivor.
   - It reconciles the provisional items heard in that conversation against the
     tasks its normal processing saved: each becomes `kept` (with the task id)
     or `dropped`.
   - A pending "Wrap up now" for that conversation closes the episode.

## Provisional items (INV-TASK-2)

The cheap model's tasks and reminders are shown live (inline in the transcript
and in the live episode) and kept out of the Tasks list: they are never written
as action items or Candidates. The conversation's normal processing remains the
only writer, under its conservative prompt. Reconciliation is the shadow precision
metric that tells whether the cheap pass could ever be trusted to replace
per-moment extraction. Undo marks an item `dismissed`.

## Close and wrap-up

The close reasons are `user`, `gap`, `idle`, `hard_cap`, `source_change`,
`calendar_boundary` and `moved_on`.
- `POST /v1/episodes/{id}/wrap-up` with the conversation being finished waits for
  that conversation's finalization. That is the normal processing pass, run once
  through the client-finalize trigger. Without a conversation, it closes now.
- A read that finds an episode idle for `CLOSE_GAP_SECONDS` closes it lazily
  (`idle`). No scheduler is involved.

## Kill switch and cohort

`config/episodes.py`:
- `EPISODES_ENABLED` defaults on and is the kill switch.
- `EPISODES_PERCENT` (default 0, so only the allowlist is admitted until a ramp step sets it) and `EPISODES_UID_ALLOWLIST` are for the ramp.

Off makes `/v1/episodes/*` report `enabled: false`. Apps keep today's
per-conversation UI, and no episode read, write or model call happens anywhere.

## Telemetry

`metrics.py`:
- `omi_episode_moment_updates_total{trigger,outcome}`
- `omi_episode_moment_tokens_total{kind}`
- `omi_episode_moment_cost_usd_total` (an estimate; the gateway ledger is authoritative)
- `omi_episode_moment_update_latency_seconds`
- `omi_episode_closed_total{reason}`
- `omi_episode_provisional_items_total{outcome}`
- `omi_episode_wrapup_latency_seconds`
- `omi_episode_boundary_total`
