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
   - The hard cap is four hours from the episode's recorded `started_at`.
     Moment count only bounds the stored presentation list; it cannot close an
     occasion. A continuing conversation stays with its original episode after
     the cap or an explicit close. Only a different conversation opens the next
     episode. Finalization retains the original member's evidence and reconciles
     its provisional items on that owner.

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
   navigation pointers alone. Membership is singular and checked in the same
   transaction as each link write, including live commits, updates and reopens.
   A capture crossing the cap stays in its starting episode, whose visible
   recorded window stops at four hours or the following episode. All retained
   speech (including the tail beyond the cap) is recovered once into that owner;
   recovery cannot substitute an upload-time `finished_at` for recorded activity.
   The timeline fence and metadata-window guard reject overlapping recorded
   windows before any writes.
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

## Composed summary (David, 2026-10-31)

The live notes above are a preview. Once an episode is closed and every retained
member conversation has finished processing, `composer.compose` writes the
episode's final notes in one `episode_composer` call (gpt-6-luna, low effort):
- Input: each member's own summary (title, overview, action items) plus the
  episode's full transcript with clock times. Above `COMPOSER_MAX_TRANSCRIPT_CHARS`
  (about 60k tokens; the 4h cap makes this rare) the densest 10-minute windows
  are kept in time order and the gaps are marked.
- Output (v2) replaces `title`, `emoji`, `lede` (one or two sentences; also
  `bullets` = [lede] for released clients), `follow_ups`, `people` and `moments`:
  1-8 chapters, each with 2-5 `points` (text plus up to a few `details`). The
  episode page renders each chapter as a section, like a conversation summary,
  and opens it in its conversation's transcript via `start_offset`/`end_offset`.
  Transcript labels and chapter times are HH:MM:SS; a chapter without an end runs
  to its recording's last line before the next chapter. Placeholder or
  out-of-span chapters are dropped. Member ends move `member_activity`, so a late
  member extends the episode's end. `lede` and `follow_ups` live in the encrypted
  `content` blob with the other notes.
- `composer_version` changes recompose an episode once on read.
- `composed_fingerprint` covers retained members, every member's transcript text
  and timing, and its own summary and action items. Unchanged evidence never
  spends a second call; a late member, a sync upgrade, a transcript edit or a
  discard recomposes. `summary_needs_regeneration` forces it. An episode with no
  speech is stamped once instead of retried.
- `composed_notes` hashes the composed title, notes and moment headings. A later
  per-moment write over them (a closing conversation's tail, a sync replay) still
  records membership as before, and the next compose sees the drift and rewrites
  the notes. `composed_member_ids` lets a read notice a member discarded or
  deleted directly on its conversation after the compose.
- One paid call per evidence across replicas: a `compose_lease` (fingerprint,
  150 s) is claimed by CAS before the model call. After the call the members are
  re-read; changed evidence returns `superseded` without writing (its own trigger
  composes again). Failures count `compose_failures`; the read-side net backs off
  10/20/40 minutes and stops after four until the evidence changes.
- Chapter clock times are mapped on the same clock as the transcript labels and
  must fall inside the episode's transcript span (two-minute slack).
- Triggers: close, every member finalize (including `sync_update`), and a
  read-side safety net in `home_read.project_episodes` for a closed episode that
  is uncomposed, drifted or whose visible members changed, closed over a minute
  ago (at most two per read, each episode at most every ten minutes per process).
  Runs on a small background pool, one run per episode at a time; never raises.
- Kill switch `EPISODE_COMPOSER` (on unless set off): off restores the live
  notes as the final notes. Telemetry: `omi_episode_compose_total{outcome}` and
  `omi_episode_compose_seconds`; usage adds `composer_*` counters.

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

## Live integrity and grouped completion

A confirmed capture-group join schedules one canonical recovery, including
`desktop` groups, with the admitted `capture_group` trigger. Other members join
as hidden duplicates and contribute no additional moments or model work. Metadata attachment runs
before short-tail/model checks, and completed finalizer replays repeat the hook.
Grouping and primary-note refresh never substitute for episode membership.

Known discarded/deleted/absorbed captures cannot open an episode or update its
activity. Per-member recorded clocks let a later discard remove only that
member's contribution without a stale notes CAS restoring it. A retained hidden
membership does not extend the quiet window. API visibility suppresses episodes
with no retained members independently of the occasion-relevance kill switch.

## Recorded span and time index (Phase A)

Conversation storage writes `recorded_start`, `recorded_end`, `arrival_at` and
`clock` for all channels, before compressing/encrypting transcript. The flat
API fields come from `models.recorded_span.RecordedSpan`. `conversation_span`
is the sole legacy derivation: placed transcript/frame offsets, then a sync
recording receipt or named speech end, then an imported extent. A live empty
stub is a point; its processing end never proves audio. Legacy derivation is
read-only and tagged `legacy`; an old row's creation/admission timestamp is only
an arrival estimate. There is no backfill. Live segment and sync CAS writes
refresh the span with the accepted transcript, preserving first arrival.

`utils.episodes.service.episode_at(uid, T)` answers recorded ownership without
opening or closing anything. `episodes_between(uid, start, end)` returns ordered
overlapping windows, paging on the built-in `started_at` index. Windows are
half open; quiet ownership ends at last recorded activity plus 30 minutes,
clipped to the four-hour cap. Explicit boundaries stay closed. Candidate
queries used for placement still allow a late prefix to join the same occasion.
New historical episodes retain their recorded member intervals. A late bridge
or earlier prefix recomputes that component in recorded order in one fenced
transaction, including its four-hour cuts. This makes cap placement independent
of arrival order. Old episode IDs redirect to the resulting window. Existing
live/user/calendar boundaries stay authoritative; no historical scan/backfill
is performed outside intake. Member/window/query budgets fail closed.

Each membership CAS writes `conversation.episode_id` alongside its overlay
link. A conversation crossing the cap stays with its starting episode; only
a different conversation starts the next window. An attach-before-create
link is adopted by the conversation create transaction without fabricating a
conversation. Episode writes retain `EPISODES_CLIENT_CHANNELS` admission; span
writes are global. No new composite index or reconciliation is required.

Boundary arithmetic cannot read ambient wall time. Pollers supply `arrival_at`
to evaluate recorded quiet deadlines; recorded coordinates determine edges and
activity. Moment buffering receives both recorded time and arrival explicitly;
only cache eviction uses arrival. Live conversation cap checks and reconnect/
calendar-continuation admission consume the same span; continuation timers
receive explicit `arrival_at`. Missing recorded origins are never reconstructed
from a creation/arrival timestamp. End-only legacy metadata keeps its declared
legacy fallback until a normal writer supplies recording evidence. Missing live cap-hold capture coordinates
fail closed before acknowledging audio custody.

`LIFECYCLE_V2_MODE` remains: the flag registry still says pending/default-shadow
with zero default serve percent, and it also gates recovery/executor behavior.
Typed-span readers do not depend on this unfinished rollout. No runtime flag or
production state is read or modified by this change.

Read-only Phase B sizing: `omi_conversation_llm_calls_total{feature,outcome}`
counts observed LangChain completions/errors and direct Jev dispatch attempts
in processing, live-moment and smart-merge conversation scopes regardless
of the revision-reuse flag. Content-free `repeat_work` log joins identify each
conversation using an account-scoped hash. `omi_episode_survivor_refreshes_total`
counts actual refresh processing attempts by assigned/unassigned membership;
`episode_survivor_refresh` logs hash conversation and episode IDs for per-episode
counts. Retries count as attempts. These measurements do not change LLM work,
read production data, or add persistent measurement writes. Labels have fixed
vocabularies; no user/conversation/episode ID appears in a metric label.

Recorded-component membership reads use batches of at most 50 inside the same
transaction, before any writes, so a busy component can retain all reverse
links. Relevance and duplicate-capture discovery widen legacy `finished_at`
prefilters by the shared clock-skew tolerance; recorded spans still decide
adjacency and overlap, including delayed ingestion.

Explicit closes store `recorded_end` from retained members' typed recorded spans,
clipped to the hard cap and the next recorded episode. `closed_at` remains the
close event time; it is never a new recorded ownership edge. The time index and
all overlap guards use `recorded_end` for explicit closes. The existing hard-cap
kill switch also disables the live activity clamp and automatic cap close.
A late discard removes that member's moments and items, clears the mixed summary,
and marks it for regeneration before later valid speech can reuse it.

### Occasion membership and late discard repair

`occasion_retention` returns `occasion_member` only after a metadata-only,
recorded-timeline transaction claims that exact episode and writes both
`episode_links/{conversation_id}` and the conversation's `episode_id`. This
runs inside relevance, before desktop `client_finalize` fanout can delay or
skip its post-finalization hook. A changed owner or failed claim retains the
clip as `occasion_lookup_unavailable`; it never reports uncommitted membership.
The write requires episode cohort admission, the capable-client marker and the
recorded-time switch. Without admission, read-only proof still keeps content as
`occasion_context`, without claiming membership. The normal desktop and pendant
finalize hooks remain idempotent safety nets. A changed past-cap owner is rejected
before the immutable-owner shortcut can report success.
Claims into automatic historical episodes also update `recorded_members` in the
same transaction, so later canonical repartition retains the claimed capture.

`sync_relevance` is intake's `keep`/`review` hint, not the final keep/discard
verdict. It can remain `keep` when a later model assessment discards content.
Episode attachment, recorded activity, finalization and API visibility use the
shared final-discard predicate (`fragment_visibility.is_relevance_discarded`),
including restore authority, instead of interpreting that hint as visibility.
A discard CAS re-reads retained members' recorded spans and recomputes the
start and end for live and closed episodes, applying the cap from the retained
start. Recompute only when the discarded set changes or membership changes in an
episode with discarded members; notes-only updates reuse the repaired bounds.
Discard repair retries with a fresh episode after
a notes CAS wins the race. Legacy compressed/encrypted transcript evidence is
decoded before deriving spans; processing `finished_at` is never used to
reconstruct a legacy member's end. Reconstruction uses the new attachment's
clipped recorded boundary, so retained spans cannot extend it across the next
episode. Hidden memberships remain for
recovery and single ownership; they contribute no clocks or visible row.

Recorded attachment preserves a cross-source overlap interval before adding the
new member/source. Both recovered content and the desktop finalization tail skip
segments fully inside the original device's recorded interval, even when relevance attached
first. Earlier prefixes and later segments beyond that interval remain eligible for notes; confirmed
capture groups continue to use their canonical member.

A historical episode whose start advanced after discard keeps its original ID.
Canonical partitioning checks every destination document before writing and uses
a deterministic displaced ID when an unrelated episode or redirect occupies it.
It never overwrites that episode's retained members, notes or reverse links.

When atomic sync intake appends meaningful speech, its new content revision
invalidates an older automatic model/Jev/deterministic discard. Transport replays
and content still needing fragment review retain the assessment; user decisions remain authoritative.
The final-discard predicate continues to ignore the intake hint itself.
