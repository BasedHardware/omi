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
  another conversation's next moment (the buffer carries forward), or explicit
  finalization / Wrap Up.
- **Episode**: the moments and conversations of one occasion, with a compact
  state: topic, running bullets, people, open questions and provisional items.

## Flow

1. `live.py` sees every batch of final segments through
   `utils.app_integrations._async_trigger_realtime_integrations` (pusher, or the
   listen fallback) and buffers them per user in process (TTL + size cap).
   - **Structure first** (`service.attach_conversation`): a conversation's first
     words attach it to the live episode by the cheap rules, with no model call.
     The app gets the episode, its real start and its member conversations at
     once, so live splits, short fragments and parallel captures hide under one
     row instead of waiting for the first notes. An ambiguous gap joins
     provisionally (`pending_boundary`); the conversation's first moment asks Jev
     and, on a confident "moved on", splits it into the next episode.
   - A moment also ends after `MOMENT_MAX_SECONDS` of steady speech (`interval`).
     A conversation rollover carries the buffered segments into the next moment
     when both conversations belong to the same episode; a pusher session end
     retains the buffer for one `MOMENT_PAUSE_SECONDS` reconnect window, then
     flushes the tail if no reconnect arrives. Finalization and Wrap Up flush it
     sooner when they run.
   - The first episode moment is checked against the episode's original start
     across every member conversation. At `MAX_EPISODE_SECONDS`, the old episode
     closes and continued speech starts a new one at the cap boundary. Provisional
     items for a continuing member transfer to the successor for finalization
     reconciliation. While an episode is live, the Home row timer uses its
     `started_at`; during rotation it holds the prior anchor until the successor
     row is visible.
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
     new text, including any carried segments from the same episode. The earlier
     transcript is never re-read. Model bullets are rejected when at least ten
     words have 80% ordered overlap with the transcript, or they start with a
     speaker label; short quotations and concise summaries are allowed. One
     bounded repair call is allowed, after which the moment is rejected as
     `quality_error` and the previous “So far” remains visible. The fixed instruction
     prefix comes first and the clock, state and new speech come last.
     One output language is resolved for every moment (`output_language.py`,
     kill switch `EPISODE_OUTPUT_LANGUAGE_PIN`): the user's explicit preference,
     then the conversation's dominant language tag or, for `multi`/`auto`, the
     weighted dominant language of the in-memory segment batch — never the
     episode's previous output deciding on its own. Conversation language and
     user preference are cached for the episode/session, so later moments do
     not repeat Firestore reads. The prompt pins that language; the episode only
     stamps `output_language` when local detection confirms the resulting state.
     An unstamped or wrong-language state is detected and repaired on its next
     moment. The same kill switch also covers provisional topic, recap and
     proactive-notification prompt changes.
   - **Compare-and-swap store** (`database/episodes.py`): speech-derived fields are
     sealed with the user's key. A lost race retries once.
3. When a conversation's finalize starts, pending live speech flushes before its
   episode closes (`service.close_on_finalize`, through `finalize.close_now`; see
   "Close and wrap-up").
4. A sync (WAL) conversation joins the episode covering its span the
   moment intake persisted it (`service.attach_synced_intake`, through
   `finalize.attach_synced_at_intake`, called from the sync pipeline's
   `complete_sync_intake`). The join is the cheap parallel-capture one below,
   so Home folds the clip under the live row from its first appearance instead
   of only after its enrichment finalizes; a clip whose covering episode
   already closed on silence rejoins it exactly as in the finalize-time hook.
   Fail-open and gated on the same admission and client-capability markers as
   the finalize-time hook.
5. After a conversation's finalization job completes,
   `utils/conversations/finalizer.py` calls `service.on_conversation_finalized`
   (bounded, fail-open, after `complete_finalization_fanout`). The synchronous
   `POST /v1/conversations` route runs the same hook off the request path
   (`finalize.schedule_after_finalization`). The sync lane runs it too, off its
   own lane, after WAL processing persists the conversation
   (`ProcessingTrigger.SYNC_UPDATE`). The hook:
   - It applies trailing text the live stream never delivered (dedupe by the
     per-conversation applied offset), to the conversation's own episode even
     when that one has closed.
   - A sync-finalized conversation that never attached (no realtime stream
     carried it, and intake did not or could not join it) joins the episode
     covering its span first, as a parallel capture: a member whose
     recovered speech merges into the existing compact notes through a
     `sync_recovery` moment. A transactional content receipt per segment
     snapshot makes repeated intake/finalization idempotent, including text
     inserted behind an earlier placed offset. Overlap alone never proves
     that the live stream heard the recovered words. Stable segment slices and
     bounded batches keep every word inside the prompt budget before recording
     consumption. It never
     closes the live episode and never opens one; a discarded conversation
     never joins. Its speech extends the
     episode's `last_activity_at`, so an idle close cannot fire while sync
     speech keeps landing late. A clip that started
     before the episode's recorded start still joins when its span reaches the
     episode or it began within `CONTINUE_GAP_SECONDS` of that start (the
     pendant and the phone clock separately); one that ended earlier belongs
     to an occasion already over.
   - A clip that lands after its covering episode closed on silence (`gap` or
     `idle`, never a user close, wrap-up or hard boundary) rejoins it
     (`policy.rejoinable_closed_episode`): the clip's span overlaps the closed
     episode's `started_at..closed_at` window, or starts within
     `CONTINUE_GAP_SECONDS` of its end. When the closed episode is the most
     recent one and no newer episode exists it reopens
     (`database.episodes.reopen_episode`, transactional; the recap link stops
     advertising it as last closed); when a newer episode owns the now the clip
     attaches as a member of the closed one without reopening it. A user,
     wrap-up or boundary close stays closed.
   - It repoints a smart-merge donor to its survivor.
   - It reconciles the provisional items heard in that conversation against the
     tasks its normal processing saved: each becomes `kept` (with the task id)
     or `dropped`. A discarded conversation's items are dropped.
   - It closes the episode if the close at finalize start never ran.

Live and recovery updates share content-revision receipts in a separate
`content-v1:{conversation_id}` key of the existing receipt store. Complete
live prompt input is recorded alongside its state, so attaching WAL to that
same canonical row feeds only unconsumed content, including gaps behind the
cursor. Existing unplaced-ID receipts remain consumption proof. Older placed
cursor-only state has no exact content proof; its first recovery conservatively
merges the retained snapshot once instead of dropping a potentially new gap.
Sync donor repointing transfers both receipt namespaces in the membership CAS,
and that repoint runs inside the three-attempt retry owner at intake/finalize.

Sync attachment retries lost compare-and-swap commits up to three times with
jitter and fresh membership/boundary reads. Saturated synchronous intake and
finalize hooks enter a bounded deferred queue on the same executor; a released
slot retries admission without a later append or a retry thread. At 64 deferred
calls synchronous producers backpressure. This queue, like the executor's
ordinary queue, is process-local and cancels on process shutdown.

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
- Before close, recovered members' stored transcripts are checked for unapplied
  content. Their recovery moments merge into the existing notes; receipts and
  state commit together. Failed model calls consume no receipt, so close or a
  later finalize can retry. A late recovery targets its exact member episode,
  including a closed episode, and cannot open or move to a newer one.
- Ending a conversation ends its live episode at once, and the next words open
  a new one (`attach_conversation`); the server never creates an empty episode.
  - A client finalize (`client_finalize`: the app's Wrap up, a pendant double-tap,
    desktop's finalize) closes it with `user`. Both finalize routes close with the
    request; the durable finalizer repeats the close when its job starts.
  - The server ending an occasion conversation (`capture_end` on silence,
    `server_recovery` after a disconnect) closes it with `gap`, unless another
    conversation joined after it (a rollover, a second device). Desktop capture,
    which still splits on short silences, keeps its episode until the rules above.
  - The ended conversation is the episode's `closing_conversation_id`. Its items
    stay provisional until its processing reconciles them, and it never reopens
    the episode or opens or joins another: a late live moment is
    `skipped_closed`, and a re-attach is a no-op. A second close is a no-op.
- `POST /v1/episodes/{id}/wrap-up` closes at once (`user`), recording the
  conversation being finished as the closing one when given, after flushing the
  pending live buffer. An episode an older server left live with
  `wrap_up_requested_at` is closed on its next read.
- A read that finds an episode idle for `CLOSE_GAP_SECONDS` closes it lazily
  (`idle`), dated when the quiet reached the gap rather than when the read
  happened. No scheduler is involved.

## Kill switch, cohort and client capability

`config/episodes.py`:
- `EPISODES_ENABLED` defaults on and is the kill switch.
- `EPISODES_PERCENT` (default 100) and `EPISODES_UID_ALLOWLIST`
  select the admitted cohort. The allowlist bypasses the percentage.

Off makes `/v1/episodes/*` report `enabled: false`. Apps keep today's
per-conversation UI, and no episode read, write or model call happens anywhere.

**Client channel (the cohort).** The app sends `X-Omi-App-Channel` on every
request (`app/lib/utils/app_channel.dart`). It sends `beta` from an iOS
TestFlight install (sandbox App Store receipt) or a non-production build
profile, and `store` otherwise. That includes every Play install, since internal
and production tracks look the same on device, and any install it can't
classify. The episodes API admits a call only when its channel is in
`EPISODES_CLIENT_CHANNELS` (default `beta`). Any other call answers
`enabled: false` (404 for writes) and leaves no marker, so that client keeps
today's UI. A missing or unrecognised header (old builds, desktop, web) is
never admitted. Expanding to store users is the flip `beta,store`.

Admission alone costs nothing. `client_gate.py` infers whether the user's app
can show episodes, with no app change: a capable app calls `/v1/episodes/live`
at startup and polls it while a live surface is on screen, and old mobile
builds, the desktop app and web never call any `/v1/episodes` route.
- Every admitted episodes API call (cohort and channel) leaves the Redis marker
  `episodes:client_seen:{uid}` (`CLIENT_SEEN_TTL_SECONDS`, 14 days). It is
  rewritten at most once per `CLIENT_SEEN_REFRESH_SECONDS` (an hour) per uid: an
  in-process memo skips Redis between refreshes, and the marker's remaining TTL
  tells a replica that another one already refreshed it.
- Listen (`live._moment_if_client_seen`, one Redis read on `db_executor` per
  ended moment), the finalizer (`service.on_conversation_finalized`, the absorb
  hook) and the mentor state run only with admission and the marker. Without
  the marker an ended moment is dropped and counted, and nothing is read from
  or written to the episode store.
- The API stays available to every admitted uid, since it is what sets the
  marker. The allowlist does not bypass the marker, so an allowlisted user on
  an old client also costs nothing.
- Reads fail closed: a Redis fault means no capable client, so no spend.

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
- `omi_episode_moments_skipped_no_client_total{trigger}`: admitted moments (and
  finalization tails, `trigger=finalize`) skipped because no capable client was seen
- `omi_episode_live_sessions_total{client_seen}`: admitted live conversations at
  their first ended moment; `client_seen="true"` over the total is the share of
  active listen sessions with the marker
- `omi_episode_client_requests_total{channel,outcome}`: episodes API calls by
  channel (`beta|store|unknown`) and outcome (`admitted|channel_closed|not_admitted`)

The shared `utils.metrics` exporter imports these collectors, so the backend,
listen and pusher `/metrics` routes expose the same bounded-label families.
