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
4. **Recorded time owns the timeline (David, 2026-10-29).** Every device
   uses `timeline.episode_owning_recorded_time(uid, at, ended_at=...)`: one
   read-only function an agent or service can call to ask which episode owns
   recorded time T. `database.episode_timeline.recorded_candidates` reads a
   complete metadata window (single-field `started_at` index, at most 128 rows;
   a full page raises rather than proving no owner). The pure
   `choose_recorded_episode` policy ranks overlap before adjacency, closes at
   thirty minutes of **recorded** quiet and bounds an episode to four hours.
   Source/device and processing order do not partition occasions. A user or
   hard boundary forbids extending beyond its recorded end; speech inside its
   existing recorded window can still join.
5. Intake and finalization call the same policy inside
   `database.episode_timeline.attach_recorded`. A per-user timeline fence
   serializes historical create/attach with live episode commits; competing
   captures re-read membership and the metadata query before any writes.
   A covering closed episode remains closed. A covering live episode receives
   only recorded activity; old audio cannot replace current activity with
   ingestion time. With no covering episode, sync creates a **closed** episode
   at its recorded start/end and leaves both `current` and `last_closed`
   navigation pointers alone. Retry membership is stable inside its recorded window and notes still
   use the existing transactional content receipts. A later append extends
   the same member's recorded window before notes recovery. A conversation that
   crosses a four-hour or existing explicit boundary remains one storage row
   referenced by successive closed windows, just like a live cap rotation.
   Its membership link records all windows and names the latest one. Recovery
   assigns each placed segment to its start window once, clamps moment clocks
   at the cap, and retains unplaced evidence in the first window. Receipts
   remain global to the conversation, so retries cannot duplicate the text.
   A later **fresh live** capture may resume a silence-closed owner under the
   timeline/current-pointer fence; late intake never calls that transition.
   Explicit closes and the four-hour boundary stay closed. Finalization
   reconciles provisional items in every capped window.
6. Realtime input derives its start/end from the conversation origin and
   placed segment offsets. Late batches use recorded-time attachment rather
   than the live tracker; unplaced text supplies no boundary. Timely moment
   buffers use recorded speech time as well. Listen batches whose recorded
   end is at least the shared conversation silence gap (120 seconds) behind
   processing use ordinary sync temporal assignment and its durable hold /
   enrichment outbox. They do not stamp the carrying socket as their target,
   and they do not feed realtime episode or pusher hooks a second time.
   Sync assignment stores `sync_recorded_end_at` as proof of the incoming
   audio extent (including a silent tail). A live target without that receipt
   contributes placed speech only; its processing-time `finished_at` cannot
   expand the temporal search or the stored end. Older pure-WAL extents remain
   recorded-time inputs.
7. Smart-merge donor links and content receipts still move to their survivor;
   finalization reconciles provisional items with the ordinary saved tasks.
   Episodes never merge or delete conversations themselves.

The episode hard cap is **four hours** (`MAX_EPISODE_SECONDS = 14400`). The
quiet close remains **thirty minutes** (`CLOSE_GAP_SECONDS = 1800`). Arrival
and processing time are bookkeeping (`created_at`, update timestamps), never
speech boundaries, episode activity, gap distance or elapsed-time anchors.
The additive `timer_started_at` wire field sends the current live episode's
recorded start. Current apps replace cached capture/restart anchors on every
poll, including corrections to the same episode; layout is unchanged.

Rollback switches (ship on): `LATE_AUDIO_SYNC_INTAKE_ENABLED`,
`EPISODE_RECORDED_TIME_ENABLED`, `EPISODE_LIVE_TIMER_START_ENABLED`. Set a switch
to false to restore that legacy path. Existing historical episodes stay closed
and durable enrichment obligations drain; rollback does not rewrite history.

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

## Occasion-aware relevance (David, 2026-10-29)

`CONVERSATION_OCCASION_RELEVANCE_ENABLED` is an independent default-on kill
switch. Intake preserves every sync fragment until temporal assignment and
its processing hold have assembled the canonical span. Rule-only filler is
marked for review, never independently hidden at intake. Finalization runs
relevance on that assembled span. Recorded-time episode ownership (live or
closed), or a kept neighbor inside the shared conversation join gap, retains
its evidence before deterministic or paid discard tiers. The occasion's notes
are the aggregate assessment; an individual member's low relevance cannot
remove evidence from that occasion. Lookup failure cannot prove isolation and
retains content. Standalone rejection remains available only after both
ownership and neighbor lookups establish isolation.

A neighbor is context, never proof that content was absorbed. The discard
prompt cannot drop a continuation on proximity alone. Only a successful merge
transaction writes an `absorbed` relevance receipt and the canonical redirect;
content, tasks and notes follow the existing survivor refresh protocol. Donor
membership and consumption receipts follow the survivor in closed historical
episodes as well as live ones. All original evidence remains reachable from
one occasion, including short answers and acknowledgments. A discarded
isolated clip does not join an episode; related content is retained before
that verdict can be produced. Provisional task suggestions may be dropped
when not confirmed at finalization; their source conversation content remains
in the occasion. No historical records are rewritten.

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
- A client ending a conversation closes its live episode at once; the next
  recorded words can open a new one (`attach_conversation`). Automatic
  conversation finalization preserves the episode until thirty minutes of
  recorded quiet. The server never creates an empty live episode.
  - A client finalize (`client_finalize`: the app's Wrap up, a pendant double-tap,
    desktop's finalize) closes it with `user`. Both finalize routes close with the
    request; the durable finalizer repeats the close when its job starts.
  - The server ending an occasion conversation (`capture_end` on silence,
    `server_recovery` after a disconnect) closes it with `gap` only after the
    thirty-minute quiet window, unless another conversation joined after it
    (a rollover, a second device). Desktop capture,
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
per-conversation UI, and episode lifecycle reads, writes and model calls stop.
The independent occasion-relevance policy may still read existing ownership
metadata to retain captured evidence; its own kill switch controls those reads.

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
