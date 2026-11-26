# Recording-derived conversations v3

The code default is `CONVERSATIONS_V3_STAGE=beta`, and the deployed source (`runtime_env/_base.yaml`)
is `beta` again since 2026-11-18 (it held at `cohort` on 2026-11-17 while reconcile commit
conflicts were fixed). Change the stage only there, never by a live-only env edit, which the next
workflow deploy would revert. `CONVERSATIONS_V3=off`
stops marking new mobile pendant documents. Stages are `cohort`, `beta`, `all`;
`rollout_cohorts/conversations-v3` is for named qualification accounts. Admission
needs a v3-capable app: only those builds call `GET /v1/conversations/live`, on any
channel, which refreshes the 14-day `conversations_v3:client_capable:{uid}` marker
(`utils/conversations/v3/client_capability.py`). Beta also needs the shared, refreshed
14-day episode client-seen marker (TestFlight); `all` needs only the capable marker.
The episode marker alone is not proof: code before #25500 wrote it for store-channel
episode callers too. Owners whose apps all predate v3 keep legacy intake: their builds
would show the raw recording a capture ends with as a blank card that 404s. An owner
with a v3 app on one device and a pre-v3 app on another gets that card on the old device.

Before a stage or kill-switch move, and before each service in its move order, check live prod against
`backend/deploy/activation/conversations-v3.yaml` (services and minimum commits, order, env, gateway
lanes, queue, scheduler jobs): `activation_collect.py` then `activation_check.py`; see
`backend/deploy/activation/README.md`.

Provision the dedicated queue on dev/prod before enabling admission; the prod
ops manifest declares its bounded concurrency/retry policy. The same stage must reach backend/API, backend-listen (including realtime role),
backend-sync, backend-sync-backfill, sync-backfill-worker, backend-integration,
and pusher wherever their deployed image can create or finalize pendant rows.
The desktop backend must use the same value for capability/episode responses;
its desktop creates remain one-to-one. Refresh the runtime image/service census
before rollout. `backend/deploy/runtime_env/_base.yaml` is the shared stage
source; composition binds Cloud Run services/jobs and desktop directly, and
backend-listen/pusher through the generated shared ConfigMap. The uninstalled
sync-backfill-worker pilot references that ConfigMap. STT-only parakeet workers
do not create/finalize/read conversation documents. A stage edit must be composed
and deployed to every relevant role; no runtime source was changed outside this
worktree. Leave `CONVERSATIONS_V3_FIRST_APP_BUILD` unset in source. At rollout,
lead2 sets it through the shared runtime source from the first TestFlight build
containing this PR; unset/invalid yields unknown and cannot qualify deletion evidence.

## Internal live recap beta

`CONVERSATIONS_V3_LIVE_RECAP_COHORT` controls the authenticated API detail
projection of saved live recaps and the live catch-up stream. Its default is
empty. The syntax is a comma-separated set of `uid:<uid>` entries. A missing
value, a malformed entry, a wildcard, or any percentage token closes the entire
cohort. The classic summary stream refuses rows eligible for live recap.
Finished summaries and the live Transcript tab keep their normal paths.

The released classic stream could store generated summary prose in the same
`structured.overview` field used for owner edits. Older overview-only rows
have no authoritative provenance that distinguishes the two. Denied LIVE
detail and list responses omit confirmed generated legacy sections while
retaining the ordinary editable overview and verified settled notes. The LIVE
recap surface reads only the separately attributed recap. No stored notes are
rewritten during rollout or rollback.

The Pipeline owner qualifies SCA-3062 and the Release owner applies approved
configuration through the managed deployment source for each API role serving
the conversation endpoints. Admit only the existing approved internal
TestFlight group. Keep the membership values in protected deployment
configuration and out of the public repository, issue comments, and logs.
Verify the exact serving release and build before starting the readback.
Broader release requires a server-enforced generation budget and separate
approval. The internal client cadence and telemetry do not enforce that budget.

Start with an approved member and a nonmember. Verify that the member can
retrieve a saved recap and explicitly request a live recap. Verify that the
nonmember's detail has no recap and the stream returns the typed
`live_recap_unavailable` refusal before a writer or provider call. Both must
still be able to read their transcripts and finished summaries. Use the
content-free recap events and gateway accounting receipts, described below,
to distinguish provider attempts from cache hits and lease conflicts. Exclude
deliberate first opens and retries from the automatic count. Record missing
receipts or unjoinable evidence as unknown and keep wider release closed.

Stop on the first confirmed automatic provider invocation outside an eligible
foreground Summary tab or the first window with more than one automatic
invocation for the same viewer in five rolling minutes. Use the approved
first-open-only path once it is verified serving, or disable admission by
clearing the cohort on all API roles. Record rollout or rollback with the exact
serving revision and UTC read time. Repeat the nonmember, Transcript, and
finished-summary checks on the serving revision. After a full five-minute
window on that revision, record the joined provider counts and verify that a
previously saved recap is unavailable when admission is disabled.

First filter provider-attempt timestamps to the trailing 300 seconds. Within
that window, join shared viewer aliases and deduplicate gateway attempt IDs.
Adjacent buckets intentionally overlap, so a shared alias alone cannot establish
elapsed time. Keep distinct request and foreground interval digests when grouping. Missing
or invalid diagnostics yield `join=unverified`. A `gateway_dispatch` records
intent to send. Existing gateway accounting must be enabled and healthy for
the readback interval. A `cache_hit` or `lease_conflict` with no dispatch
in that request contributes zero provider attempts. The live recap uses
transcript evidence and keeps deterministic relevance checks. It skips paid
relevance classification, task deduplication, optional account and screen
context, and pre-notes merge work. Finished notes keep the full path.

Only new `omi`/`phone` capture/sync creates become recordings. Existing documents
keep their layer through stage changes. A recording is not a product item;
`home_hidden` only removes a conversation from unfiltered Home and its count.
The derived fragment reaching an explicit manual cut is Home-visible regardless
of length or media/background classification. The normal delete, discard and
failed-summary filters still apply. A capture with no speech creates no window.
The persisted `manual_end` survives rebuilds and allows conversational notes
even below 20 words. Naturally ended media is hidden. Background hides only
with positive wearer recognition somewhere in the contributing recordings:
`is_user: true` or a segment-bound wearer label from authoritative speaker
evidence. Without it, background becomes conversation and uses the normal
150-word rule or the manual-end override. `kind`, `outline_kind` and the
classification reason remain available for analytics.
Set `CONVERSATIONS_V3_MANUAL_END_HOME_VISIBLE=off` on every service that runs the
v3 reconcile (`backend` for on-open rebuilds, `backend-sync`, `backend-sync-backfill`)
to restore classification-based hiding for manually ended media and recognized
background on subsequent projections. The service reads the switch and passes it to
the pure planner. Previously written rows keep their stored visibility until rebuilt.
A mobile capture is audio-only when the user finishes it: the transcript is produced by the
batch pipeline afterwards. The finalization worker closes such a recording through
`complete_server_batch_capture`, which stores `v3_manual_end_requested` for a `client_finalize` job.
Record admission promotes the request to `v3_manual_end` when the recording is a single batch unit,
so the window is cut and locked when its one transcript lands. A recording of several units (an
audio gap over 30 s, or over an hour) projects one unit at a time; cutting on the first would lock
a partial window, so it keeps the silence and lock timers unless the fast first transcript below
takes it. `omi_conversations_v3_batch_manual_end_total{outcome}` counts `promoted`, `fast_finish`,
`multi_unit_deferred`, `not_promoted` and `error`. Set `CONVERSATIONS_V3_BATCH_MANUAL_END=off` on
`backend` (finalization worker) and `backend-integration` (record admission) to stop both the
request and the promotion for later finishes. Stored markers remain.
`CONVERSATIONS_V3_FAST_FINISH` (default `cohort`: members of the `v3-fast-finish` rollout cohort,
added with `scripts/rollout_cohort.py --add`, no roll; `on` for every v3 owner; `off`) adds a first
transcript for a manually finished recording. When batch record admission stages the sealed audio,
`utils/conversations/v3/fast_finish.py` transcribes it once through the prerecorded provider for the
recording's language and writes the result with `update_conversation_segments`. That write marks the
recording pending and wakes reconcile, and the stored manual end cuts the window, so notes start
without waiting for the batch merge and delivery. The batch record projection later replaces the
provisional segments; once `record_projection_revision` is set the fast write is refused. Recordings
of more than nine chunks (about 44 minutes) or eight units, partial records, custom STT, locked rows and
private rows are skipped. `CONVERSATIONS_V3_FAST_FINISH_CHUNKED` (default `on`) splits each unit into
chunks of at most five minutes, cut at retained-audio silences where possible and otherwise at even
offsets with a 3 s overlap, and sends them to the provider concurrently on the six-worker
`fast_finish_chunk` pool: four in flight, three for a recording over 20 minutes. Only audio over 20
minutes makes a pass long, never its chunk count; a long pass takes its own pass slot, so it never holds
a short Finish's slot, and a short Finish waits up to 10 s for a slot instead of answering `busy`. Length,
canary and cap refusals are counted before any slot is taken. Each chunk asks the batch privacy fence
again when it actually starts, and so does the language probe right before it sends; one refusal or
error ends the pass (`privacy_blocked`), and every later check refuses without asking; a chunk is retried
once if time allows. One 45 s deadline from record admission (not the Finish tap) covers slot wait, the
Firestore reads before chunking, every retained-audio reference read (its storage timeouts capped to what
is left), both language probes, queueing and provider requests (their connect, pool, write and read
timeouts share what is left); past it the pass cancels queued chunks, waits at most 2 s more for running
ones and yields to batch as `deadline`. Language resolution (both probes) is abandoned at the deadline
as a whole, and skipped, keeping the row's language, with under 3 s left. Every Firestore call of a chunked pass (row refresh, funding,
privacy, the transcript write and the cut) is waited for only until the deadline, or 1.5 s past it after
the chunks, then abandoned as `deadline`; the write's own transaction refuses to run past that bound, and
no cut follows an abandoned write. A pass that stops early sends no further request or retry and
releases its slot when the requests in flight end. At a fixed cut the earlier chunk owns lines that start before the overlap's middle; every
later line that starts before the earlier chunk's last line ended is compared against it (words by time,
utterances by text, allowing a clipped word on either side) and keeps only what is new. Recordings over 20 minutes are a canary: `CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT`
(default 25, `long_canary` outside it) and `CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS` (default
7200 per UTC day across the fleet, of audio actually sent, retries, overlaps and the vendor probe
included, in the Redis key `v3_fast_finish:long_audio_seconds:<UTC day>`; `long_cap` past it, and also
whenever Redis errors or takes over 1 s). A long pass reserves the most it can send (every chunk twice
plus a 30 s probe clip), so retries cannot push the day past the cap, and settles in the background to
what it sent; while passes run the key reads high. Read today's total with `GET` on that key. Set `CONVERSATIONS_V3_FAST_FINISH_CHUNKED=off` on
`backend-integration` to restore one serial request per unit and the 20-minute bound. Read
`omi_conversations_v3_fast_finish_total{outcome}`, `omi_conversations_v3_fast_finish_seconds{stage}`,
`omi_conversations_v3_fast_finish_chunks`, `omi_conversations_v3_fast_finish_chunk_seconds`,
`omi_conversations_v3_fast_finish_chunk_queue_seconds`, `omi_conversations_v3_fast_finish_audio_seconds_total{path}`
(vendor probe clip included) and `omi_conversations_v3_fast_finish_wall_seconds` (written passes, from
record admission, not the Finish tap).
A manual finish that never starts the pass is counted in
`omi_conversations_v3_fast_finish_skipped_total{reason}`: `mode_off`, `already_started`, or the first
failing `fast_finish.candidate_rejection` predicate (`not_recording`, `no_manual_end`,
`status_in_progress`, `status_processing`, `status_other`, `no_private_cloud_sync`, `protection_level`,
`projection_revision`, `audio_partial`, `deleted`, `discarded`, `locked`, `custom_stt`).
Five minutes of placed-speech silence is a hard window boundary. An outline's
`resumes_previous` may undo a topic split within that interval, never rejoin
windows across the silence boundary, even with the same people. Short socket
captures and reconnects do not themselves split a continuous stretch. Listen
can seal a live v3 recording at the first 1.5 s speech pause once it is
`CONVERSATIONS_V3_ROTATION_MIN_SECONDS` old (180), or at
`CONVERSATIONS_V3_ROTATION_MAX_SECONDS` (300) without one.
`CONVERSATIONS_V3_RECORDING_ROTATION` is `off` by default; `cohort` rotates owners in
the `v3-recording-rotation` rollout cohort (`scripts/rollout_cohort.py --add`, no roll), `on`
rotates every v3 owner. Changing the env rolls backend-listen. The successor opens
first and the archive retargets late frames to it, so the sealed recording's custody
is final before it seals. A rotation-sealed recording carries
`v3_rotation_cap_seconds`; only then does a later recording still capturing (under
the cap) or sealed and untranscribed (up to 15 minutes) hold its stretch open. The
two-hour cap still bounds each resulting window. Missing transcript is not
proof of acoustic silence; qualify transcript completeness separately.

`CONVERSATIONS_V3_STRETCH_COHESION` defaults to `on`. The outline renders
stretch-local speaker labels, and short conversational topics fold within the
same silence, manual-end and two-hour cap boundaries. Home evaluates the
150-word threshold against that fresh stretch. Media, recognized background
and late fragments around published claims retain their own visibility rules.
Set the switch to `off` on v3 builder and backfill runners to restore the prior
prompt and per-topic Home minimum for subsequent passes. Existing published
windows and claims remain in place when the switch changes.

With stretch cohesion enabled, `CONVERSATIONS_V3_SILENCE_GAP_SECONDS`
controls recorded-speech grouping (120–1800 seconds), and `CONVERSATIONS_V3_LOCK_SECONDS`
controls when a card locks and owes notes (120–3600 seconds). Both default to
300. Invalid values use the defaults. When either value differs from its
default, the existing summary-open path and explicit End bypass the lock timer.
Setting both values back to 300 restores the default lock delay, still counted
from landing unless `CONVERSATIONS_V3_SETTLE_ON_LANDING=off`; disabling cohesion
restores the prior timing. Provisional rows remain reachable for the builder to finish.
A lock delay shorter than the silence threshold can finalize an initial card
while later speech still belongs to the same outline stretch. Later speech
gets its own continuation. Reconciliation can merge settled cards when the
outline and the loaded source claims cover the complete merge.

`CONVERSATIONS_V3_TRANSCRIPT_SIZE_CAP` defaults to on. A new derived window also splits
before its estimated encoded `transcript_segments` (enhanced encryption included) passes
900 KiB, below Firestore's 1,048,487-byte per-field limit. Splits use the duration cap's
continuation path; only unpublished windows split, and locked rows keep their boundaries.
Count `event=v3_transcript_size_cap_split` log lines to see splits. A commit Firestore still
rejects for size (whole document or one property) parks the owner as `document_too_large`
instead of retrying. To roll back, set `CONVERSATIONS_V3_TRANSCRIPT_SIZE_CAP=off` on builder
and backfill runners.

`CONVERSATIONS_V3_MAX_WINDOW_SECONDS` defaults to 10800 (three hours).
The first transcript line whose recorded start reaches the limit starts a new
stretch. The earlier live stretch locks and enters normal processing, and the
successor owns the live row. This boundary applies with either cohesion setting
and in historical planning. Values from 120 to 10800 set a shorter or equal
limit. Invalid values use 10800. To roll back, set
`CONVERSATIONS_V3_MAX_WINDOW_SECONDS=0` on builder and backfill runners
(`off` is also accepted). Stored windows and claims retain their existing
ownership. Track `omi_conversations_v3_window_cap_cuts_total` and verify that
live windows stay within three hours plus the configured lock delay.

A silence gap above 300 seconds also switches on sit-down cutting:
- The outline sees pauses of 2 minutes or more as `---- N min without speech ----`
  marker lines. A sit-down rule replaces the hard-boundary sentence.
- Neighbouring `conversation` entries of one stretch join into one card, with
  topics as sections. They stay apart when both name people and share none.
  Dictation under the Home word minimum between two of them joins as a section.
  Media, background, longer dictation and manual-end stretches keep their own
  cards.
- Each card meets the Home word minimum on its own words, not the stretch's.

Setting the gap back to 300 seconds turns sit-down cutting off for later passes.

At any timing, a stretch over two hours is cut at the last line that starts
within two hours of its start, then again from there. The cut ignores the
outline and does not move as live speech arrives, so a locked part never
strands lines between an old and a new cut. One ownership rule
(`planner.Ownership`) serves both the cap and the projection: a row that
published the exact segment from that recording owns it (open rows included);
only when no row does, containment in a row's window and audio claim decides,
locked rows first, so a revised turn stays with its row. When a locked row owns
the first line of a part, the part ends at the first line it does not own, so
rows cut by earlier code or an earlier pass keep their cut (even when a turn
straddles it or a held turn is revised) and the cap counts from there. A locked
row that owns none of the stretch's lines never cuts it.

With stretch cohesion on, live passes count the lock delay
from the later of the stretch's last speech and when that speech landed
(`v3_speech_landed_at`, written in the same transaction as the speech by the
live transcript write and sync assignment, and only when the speech changed). A
batch of old speech from
offline sync then waits the lock delay after landing instead of locking on
arrival. Custom timing (either setting differs from 300) always uses this clock.
At the default timing, `CONVERSATIONS_V3_SETTLE_ON_LANDING` (default on) selects it;
set it to `off` to count from the last speech again. Backfill and re-derive keep the
recorded clock.

The recording-speaker picker for a derived conversation reads and edits only
that copied window. Shared source scopes cannot expand it into other product
conversations. Legacy recording-wide naming keeps its existing behavior.
Search and agent reads retain short and hidden conversations. The exact reader
classification is `../conversations-v3-readers.json`; run
`python backend/scripts/check_conversation_readers.py --inventory` for every site.
Pipeline, sync, audio, custody, retention, export, deletion and builder readers
are explicit exceptions. Raw product by-id readers use a recording guard because
they do not all pass through the conversations router. Typesense's external
extension may still index recordings; first-party projection deletes them and
hydration rejects them. Admin raw-index counts may therefore be inflated.

Deterministic reconcile conflicts (`target_exists`, `target_deleted`, `multiple_open_conversations`,
the closure/derived budgets, `recording_decode_unavailable`, `account_deletion`, and
`document_too_large` when a written document exceeds Firestore's 1 MiB limit) answer the task with
outcome `blocked` instead of a 500 retry and park the owner on the builder lease doc
(`v3_backoff_until`, 5 min doubling to 1 h, token-fenced); `v3_pending` stays owed, on-open bypasses it,
backfill never parks the live builder, and the next successful commit clears it. `request_too_large`
is a commit request over Firestore's payload limit. Blocked and backoff live passes still drain notes for
windows earlier passes committed (not for `account_deletion`). The blocked log carries `owner=<sha256[:12]>`
and the redacted cause. A size failure also logs `v3 projection write too large
kind=<derived_row|recording|builder_lease> bytes=<estimate> claims=<n>` for the largest staged document.
Batches split at 2 MiB of derived rows or 8 MiB of all writes, counting each source claim rewrite. Source `claims` are deduplicated on every
commit: the 2026-11-18 incident was a fresh late-speech window time-matching a retained finished id, so
two planned rows re-added the same held claims and the array doubled each pass. A planned id that
already exists outside the loaded closure is adopted once as the prior (live derived rows only).
Watch `omi_conversations_v3_blocked_total{reason}` and `omi_conversations_v3_adopted_total`; an owner
blocked for hours needs investigation. With `CONVERSATIONS_V3_BOUNDED_PENDING` on, a legacy
closure-budget or document-size park gets an early background attempt. A closure-budget park
starts with eight seeds and can fall back to one. A document-size park starts with one seed.
The final commit remembers a successful smaller page on the builder lease. Before loading
the projection, the builder can clear discarded or deleted markers within the oldest 50
pending rows under that lease. A pass loads owner-wide unlocked windows one page at a time and,
while windows remain unvisited, wakes itself a minute later with a task named by its lease token.
A derived-budget park recorded before paging shipped, with indexed unlocked windows and no
`v3_unlocked_paging_attempted` yet, gets one more early attempt that sets it; a new park sets it
when it is recorded and waits out the usual backoff. See the [bounded pending](../listen_pusher_pipeline/changes/2026-11-26-v3-bounded-pending.md)
and [bounded unlocked](../listen_pusher_pipeline/changes/2026-11-26-v3-bounded-unlocked.md) change notes.
A one-seed closure still over the derived budget (one long recording owning hundreds of locked
one-line windows) parks with `v3_bounded_pending_attempted` already set. To admit it, take its
`owner=` tag from the `v3 reconcile blocked reason=v3_derived_budget` log line. Add the tag to
`CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS` on backend-sync, comma-separated; this is an env change and
rolls a revision. Then clear the park as below. The next pass loads the locked claimants within
the allowance and commits in at most `CONVERSATIONS_V3_LOCKED_MAX_BATCHES` batches. A pass costs about
6.5k to 30k reads, so admit owners one at a time first. Any step expected to exceed 10M reads a day
needs the Firestore cost owner (SCA-2173). An owner that still parks needs the fragment repair
(SCA-2918). Remove the tag to undo. See the
[locked-closure allowance change note](../listen_pusher_pipeline/changes/2026-11-26-v3-locked-closure-allowance.md).
A new failed bounded pass records `v3_bounded_pending_attempted` (and, with unlocked windows,
`v3_unlocked_paging_attempted`) on the builder lease and observes the usual backoff. An operator
clears the park by deleting `v3_blocked_count`, `v3_blocked_reason`, `v3_backoff_until`,
`v3_bounded_pending_attempted` and `v3_unlocked_paging_attempted` on
`users/{uid}/conversation_v3_leases/builder`.

Each source has a durable `v3_pending` obligation. Tasks use the dedicated `conversations-v3`
Cloud Tasks queue and the configured sync origin/OIDC identity unless
`CONVERSATIONS_V3_TASKS_QUEUE` / `CONVERSATIONS_V3_TASKS_URL` override them. A named
task coalesces each owner-minute. Explicit manual ends use a separate,
deterministic source-close task name so an already completed live task in the
same minute cannot swallow the close. They do not wait for the silence deadline.
Automatic end detection still waits five minutes of speech quiet; this is not
a measured 30-second end-to-notes guarantee. The scoped live recap can run before that background close wait for admitted testers.
Finished Standard notes use the existing summary stream.
The builder holds a Firestore token/expiry
lease, revision-checks sources and targets, and writes conversation copies and
recording claims together. A conflict retains pending work. The five-minute
sweeper cursor-pages capture, processing and purge obligations. Purge errors
retain pending state, attempts and a five-minute retry deadline per recording;
one failed erase does not block other owners. Declare indexes
with `generate_firestore_indexes.py --write`; schema readiness is an operator
gate before admission. Pending intake retains the oldest 32 obligations without a fixed 20-minute
anchor; capture-time continuation uses a bounded lookahead of at most 33 rows
(including equal timestamps). An undecodable/absent transcript cannot block the
rest of the owner: unreadable recording markers settle without a new window;
transient pointer-fetch/infrastructure errors retain their retry.
The builder and request summary share conversation leases. Renewal retries
transient faults three times and stops renewing after 15 minutes; token/expiry
fences still reject late writes. On-open's eight-second timeout shields the
tracked reconcile; a running outline retains its lease until the worker exits.
Reconcile errors log only exception class and stream the stored row. A supplied
summary token is released even on a fresh/ineligible stream exit.

Cached outlines are encrypted; transcript copies use the existing storage codec.
Finished-window copies retain user edits and stable titles. Recordings never
enter model processing, apps, memories or webhooks. Automatically ended short speech of at least 20
words uses the existing task extraction rules and memory processing without a
summary call. Media/background have no derived processing. Summaries reuse the
existing notes prompt; the v3 background lane and the on-open lane are both
Luna/low on the Standard tier (the background lane left the gateway's Flex-first
list on 2026-11-24; `LLM_GATEWAY_FLEX_FIRST_LANES` can name it again). Metering
stays in the gateway and usage tracker. The section stream uses the chat `data:` / base64 `done:` /
JSON `error:` protocol and stores only a complete revision-fenced result.
Terminal processing/outline retry exhaustion and affirmative transcription
failure show tile_state:failed, status:completed and summary_retryable when
copied speech can be retried. Locked presentation is retained. Partial/unproven
capture alone stays transcribing. Explicit reprocess owns the copied window,
resets the retry budget, bypasses short/covered-summary reuse and writes
writing -> done/failed; its notes use Standard. Home feed follows home_hidden
for v3, including failed rows, while retaining deleted/discarded/recording guards.

For recording-piece conversations, `/urls` and plugin backup return only the
conversation-level dense MP3 or pending, never covering per-file playback URLs.
The builder trims on each recording file's clock, subtracts deleted spans and
collapses gaps; spans use the copied transcript's conversation-relative clock.
Source metadata, pieces and effective deletions fingerprint the immutable blob.
Pending/unavailable /urls returns per-alias status entries without URLs so
released playback/export polls continue honestly; cached playback stays dense.
Permanent unavailable fingerprints stop re-enqueue until pieces/source change.
Temporary missing metadata/chunks/short PCM never export a partial artifact;
bounded task retries and the existing failed-merge recovery path retry them.
The v2 artifact format invalidates any older partial cache. Trim and wall spans
use normalized playback_start when present, retaining raw chunk keys for I/O.
Individual alias downloads redirect to that artifact or return 202. The manifest
retains file-local windows and skips missing/not-ready pieces. Public shares
expose only copied transcript windows. Claim release follows durable deletion
intent; settlement re-arms purge for unclaimed completed sources. Reclaim closes
the recording before physical deletion; failed erases remain owed.

Metrics: episode calls by route template, X-App-Build bucket (pre_v3/v3_capable/unknown), app channel and
v3; episode compose attempts by v3; daily active pendant owners with latest
legacy capture; builder outcomes, pending age, first speech to visible, end to
summary, first/rewrite writes and model calls. The builder's
omi_conversations_v3_uncertain_recognition_shown_total counts committed exposure
transitions caused by uncertain recognition (no owner labels). Gateway usage supplies actual cost
and per-owner accounting; aggregate Prometheus labels never contain owner IDs.
omi_conversations_v3_terminal_failures_total counts committed transitions with
static reason labels: outline/transcription/attempts_exhausted/processing.
Layer counts aggregate the unfiltered recording/Home-hidden layers without
optional-predicate composite indexes. Rare filtered layer counts select at most
10,001 metadata rows per layer, fail 503 above 10,000, and apply predicates locally; no
transcript decoding. The generated manifest has 304 composite indexes.
The daily gauge refuses a truncated scan rather than publishing a partial count.

## Sync redirect custody repair

Sync redirects transfer transcript-only claims and card source links in the same transaction
as the donor redirect. When playback backing, deletion spans, competing claims, or missing
speech evidence prevent a transfer, sync keeps the original source. The transfer checks every
line in the proposed claim against the published card and preserves the card's existing fields.

For an already-published chain, use the explicit custody repair in coordination with the live
re-derive owner. Keep overlapping repairs on the same owner paused during qualification.
Run the preview with the read-only operator profile and keep the resulting card IDs, claim
ranges and receipt in the approved QA channel.

```bash
PYTHONPATH=backend backend/.venv/bin/python -m scripts.conversations_v3_sync_custody preview \
  --uid "$QA_UID" --donor "$DONOR_ID"
```

A `ready` preview lists the original and proposed claims and card links. A `skipped` preview
reports the first reason the chain needs review. For example, playback references need proof
of equivalent backing, and competing claims need evidence beyond overlapping clocks.
The operation moves custody for supported cards. Existing Home visibility, titles, transcripts,
notes, and audio references are preserved.

After separate approval, use `apply --uid "$QA_UID" --donor "$DONOR_ID" --receipt "$RECEIPT"`
with the same module and scope. The receipt binds the exact project, owner, redirect path, edits,
and Firestore revisions. Apply updates all affected documents and creates the rollback journal in
one transaction. Repeating apply with the same receipt reports the recorded outcome.
Use `rollback` with the same arguments to restore the prior fields. Rollback refuses when a source
or card has advanced, acquired a tombstone, or changed lineage. Re-preview and escalate those cases.
Successful rollback consumes that receipt.

Each attempt reads at most nine source documents, 64 claimant cards, their tombstone documents,
the account deletion marker and the journal. At most 74 documents are written, including the
journal, and the journal is capped at 128 KiB. Preview uses a read-only transaction. Restrict
post-release readback to the approved internal TestFlight scope and record the exact TestFlight
build and serving revisions. Verify that fresh sync redirects retain custody, Home shows one
card for the same claimed speech, and separate speech remains present.

## Backfill and repair (per owner)

`CONVERSATIONS_V3_BACKFILL=off` by default. While it is off, nothing below runs. The switch is
not per owner: turning it on only lets runs that an operator planned start. A run is one owner and
one window, and it re-derives that owner's completed legacy `omi`/`phone` conversations
in `[since, until)` through the live builder and notes path. Code: `utils/conversations/v3/backfill.py`.
Operator: `backend/scripts/conversations_v3_backfill.py`, with the prod-operator tier (Firestore
only). Owners come from a file and print only as `owner[N]`. Output is counts and run ids only.

```bash
S=backend/scripts/conversations_v3_backfill.py; O=/path/to/owners.txt   # one uid per line, 0600
PYTHONPATH=backend backend/.venv/bin/python $S run --owners-file $O --days 2 --dry-run   # reads only
PYTHONPATH=backend backend/.venv/bin/python $S run --owners-file $O --days 2             # plans, waits
PYTHONPATH=backend backend/.venv/bin/python $S status --owners-file $O
PYTHONPATH=backend backend/.venv/bin/python $S resume --owners-file $O --run RUN_ID      # stalled/blocked
PYTHONPATH=backend backend/.venv/bin/python $S undo --owners-file $O --run RUN_ID [--dry-run]
PYTHONPATH=backend backend/.venv/bin/python $S run --owners-file $O --days 2 --mode rederive
PYTHONPATH=backend backend/.venv/bin/python $S run --owners-file $O --since 2026-11-19T00:00:00Z \
  --until 2026-11-20T00:00:00Z --mode rederive-live --dry-run                            # live windows
```

- **Plan.** The window is cut into partitions of at most 48 documents. Each cut is at a recorded gap
  of five minutes or more, the live hard boundary, so no live stretch spans two partitions. A gap-free
  run over the cap is cut at its largest gap, and the plan reports it as `forced_cuts`. Gaps come from
  row `started_at`/`finished_at`; a legacy row whose late text never moved `finished_at` can show a
  gap the live speech-level cut would not, so rarely one live stretch is split at a partition edge.
  `legacy_candidates` counts rows by metadata; the estimate's `sources` is the loaded count. The dry-run
  loads every partition as the builder will and prices it: one outline per stretch, plus notes or
  task-only calls by word count, at the gateway Luna card. The windows are known only after the
  outline, so treat the estimate as a planning number. Gateway usage has the actual spend.
- **Run.** The script writes `users/{uid}/conversations_v3_backfill_runs/{run_id}`: operator,
  window, planned and served code SHA, per-partition counts and outcome, and no content. It also
  writes a start marker in `users/{uid}/conversations_v3_backfill_starts` (account deletion purges
  it with the owner's data). The five-minute sweep starts the run
  when the switch is on. Each partition then runs as one task on the `conversations-v3-backfill`
  queue, one dispatch at a time: an outline pass under its own `backfill-builder` lease (never the
  live builder's), then notes through the live `_process` until a 20-minute step deadline. Notes for
  historical rows use their own `v3_backfill_process_pending` marker, so the live sweep and the live
  queue never pick them up. Owners run one after another. A new run is refused while the owner has a
  planned, running, blocked or undoing run: resume or undo it first.
- **Accuracy.** Derive uses the live stretches (five-minute silence, manual cuts, duplicate-capture
  removal), outline prompt and model, planner, visibility rules, the `CAPTURE_END` notes trigger
  (relevance, speaker resolution, meeting context, media/short-clip floors), the notes models,
  context and entitlement checks. Backfilled rows differ in one way: `process_conversation` takes no
  derived effects for them, the same as silent backfill. That means no memories, tasks, apps,
  folders, vectors, notifications, duplicate-capture links or created webhooks. A legacy manual stop
  is read from the row's `relevance_decision.trigger == client_finalize`. Rows without that record
  are treated as silence-ended.
- **Home.** Each legacy donor becomes a hidden source: `recording=True`, `backfill_superseded`, and
  `v3_backfill_run`. Its `structured` notes and summary are kept, and the original values of every
  field the conversion touches are kept in `v3_backfill_prior`. Derived rows carry `backfilled=True`
  and `v3_backfill_run`. Home shows the v3 rows and not the legacy ones, so there are no duplicate
  cards. Legacy rows that are private, discarded, imported, locked or unreadable stay as they are,
  and so does a row no window claims (no usable lines after duplicate-capture and deleted-span
  removal); the ledger counts those as `sources_unclaimed`.
  Deleting a backfilled row never arms the donor's audio purge.
- **Resume, re-derive and undo.** A redelivered or resumed partition loads its own run's donors and
  derived rows and plans over them (adoption, not delete and recreate). `--mode rederive` rebuilds
  rows that were already backfilled in the window after a pipeline fix. It reuses each row's id,
  re-runs outline (when its inputs changed) and notes, and retires copies that no rebuilt window
  claims. A window that would merge rows from two different runs blocks with `rederive_mixed_runs`,
  so undo stays scoped to one run. Edits made to backfilled copies are not kept. `undo --run` takes both the backfill and the live
  builder leases before it lists the run's documents, so no pass commits while it works. It refuses
  while either is held or a notes write for the owner is in flight, and records the refusal in the
  ledger (`undo.reason`); rerun it. `undo` and `resume` exit 1 when no listed owner has the run.
  Otherwise it works one connected group at a time (donors and the copies that claim them): in one
  transaction it restores every donor field exactly and deletes the group's copies, so nothing is
  hidden or doubled partway. It writes no tombstones and touches no audio. A group in which the owner
  deleted a copy (a deletion tombstone for a copy id, or a donor deleted span added after the run;
  both read inside the transaction, so a delete racing undo is seen) stays as backfilled v3, so undo
  never resurrects a deletion; its surviving copies' owed notes move to the live notes marker (the
  deleted copy's notes are never written). Totals and removed copy ids are written in each group's own
  transaction. If the owner deletes a copy in the instant undo removes it (before the delete path
  writes its tombstone), the legacy row is visible again: undo lists those copy ids as
  `deleted_during_undo_ids` (every attempt's removals are checked), so delete the matching legacy
  rows by hand. A run with kept groups or a raced delete ends `undone_partial`, never `undone`, and
  the operator exits 1. A group whose copy a live builder pass extended with recordings captured
  after the run (the copy then holds live capture as well as donor lines) also stays as v3, counted
  as `groups_kept_live`/`donors_kept_live`. A group containing a copy stamped with another run
  uses the same counters. Undo leaves the other run’s rows and notes obligations untouched. The ledger
  records `groups_kept_deleted` and `donors_kept_deleted`; `undo --dry-run` prints the group count
  and `donors_deleted_by_owner_min`, a lower bound (it counts deleted spans and deleted copies
  recorded on donors, and misses only a delete whose claim release has not run yet). Undoing a run
  already `undone` or `undone_partial` reports its recorded result and changes nothing. A group
  that is both live-extended and owner-deleted counts as kept-deleted. A group whose reads (two, plus one per donor and three per copy) would exceed 500 is
  refused (`undo_group_too_large`); partitions keep groups far below that. Undo a re-derive by undoing the original run;
  `undo` on a re-derive run id says so and exits 1. Not undone: outline cache entries, speaker-resolution and media-boundary
  evidence that the notes path wrote, and gateway spend.
- **Blocked.** A partition over the loader's 128-document limit, a planned id that is already a live
  row (`target_exists`), a tombstoned window, or a converted donor that no longer reads
  (`backfill_source_unreadable`; its copies are kept), a re-derive in which a converted donor no rebuilt window claims
  (`backfill_donor_unclaimed`; when the owner deleted that donor's copy, undo keeps it, so undo the
  run and plan a new one around that range instead of resuming), or account deletion starting mid-drain (`account_deletion`;
  no further transcript goes to the notes model) blocks the run. One owner's blocked plan prints
  its reason and the operator continues with the next owner (exit 1). The partition and its reason are
  recorded in the ledger. Fix the cause, then `resume`. Never describe a blocked or partial run as
  complete. `status` shows partitions committed, windows, Home-visible rows, outline calls and
  notes processed or failed.
- **Live re-derive (`--mode rederive-live`).** Replans one owner's finished live v3 windows in
  `[since, until)` from their source recordings with the current planner, after a planner fix (the
  live builder keeps finished windows as they are). `until` must be at least 15 minutes ago.
  Partitions hold up to 192 documents (the loader refuses more than 256). Same lease, queue, outline
  and notes path as a backfill; rebuilt rows are stamped `backfilled` and `v3_rederive_live_run`, so
  their notes take no derived effects and they never fan out again.
  - Never touched: open windows and every source they hold, rows that overlap `since` or `until`,
    sources that are pending, unsealed, still transcribing, failed, purge-pending, private, deleted,
    legacy backfill donors or within a claims update of Firestore's 1 MiB document limit
    (`size_limit`, reported by the dry-run; and every row on them), and rows that are edited (`user_title`,
    corrections, speaker assignments, star, folder, photos, kept), locked, shared, private,
    discarded, deleted, backfilled by a legacy run, unreadable or still owed notes. These are offered
    to the planner as published finished rows, so their speech, claims and audio stay theirs. The
    ledger counts each as `protected_<reason>` (deleted rows included: their claims still fence) or `sources_blocked_<reason>`,
    plus `sources_with_deleted_spans` (deleted spans are never replanned) and `sources_unclaimed`
    (sealed live speech no window ever claimed; the run makes new cards of it, so check it first).
  - Adoption: a rebuilt window keeps the id of the earliest row it absorbs. A rebuilt window equal to
    its row (speech, bounds, claims and Home decision) is not written and its notes do not re-run.
    Every other row it absorbs is retired as a sync bridge (`deleted`, `discarded`,
    `sync_merged_into` the survivor, `v3_derived=false`): reads by id follow it, and no v3 read
    treats it as a deletion. The survivor lists its bridges in `sync_merged_from`, so deleting it
    purges them, as with a sync merge. Its claims leave the sources in the same commit. No audio purge is
    armed or cancelled.
  - Dry-run: reads only and calls no model. Before counts are exact; `windows_after` and
    `visible_after` replan with one outline chapter per stretch, so the outline can only add windows
    and retire fewer rows than `rows_retired_est`. Spend: one outline per stretch plus notes per
    window after. The run's ledger records the exact `windows_after`, `visible_after`,
    `rows_rebuilt`, `rows_created`, `rows_unchanged`, `rows_retired` and `outline_calls`.
  - Use `--historical-sitdown` for the 900-second gap and 3,600-second landing lock. It takes
    one owner and explicit bounds, with the end at least an hour old. Partitioning refuses forced
    cuts, and the estimate and worker verify seams using decoded speech. Missing landing timestamps
    and unsettled stretches block the partition. The estimate still uses placeholder outlines.
    Before scheduling an approved repair, verify that every backfill task worker serves this
    code with cohesion enabled and both exact timing settings. The run records the timing pair
    and each derive attempt checks it against the worker configuration. Pause dispatch before
    routing an unfinished timed run to an older worker.
  - Blocked: `rederive_live_open` (speech within five minutes of now), `rederive_live_boundary` (a
    rebuilt window would cross `since` or `until`), `rederive_live_outline_failed` (the outline fell
    back; never committed as failed tiles), `rederive_live_coverage` (a row's speech would be lost),
    `rederive_live_donor_tasks` (a planned retirement would strand standalone tasks),
    `document_too_large` (a source's planned claims would cross the document limit; checked before
    any write), `backfill_partition_budget` (the final commit would exceed the write cap) and
    `rederive_live_range_overflow` (the partition's time range holds more documents than one pass
    loads; plan smaller partitions). A
    commit that fails after earlier batches landed leaves the partition blocked: `resume` replans it
    (rows this run already wrote are replanned, their first prior kept), and `undo` is exact from
    either state.
  - Undo: before each commit, the run writes every changed, created or retired row's stored document
    and claim positions to `conversations_v3_backfill_runs/{run_id}/conversations_v3_rederive_priors` (purged with the account
    and after a finished undo; never written for a conversation already deleted or once account
    deletion began). Conversation deletion checks for priors by the requested ID and known bridge
    IDs, including when the worker stopped before stamping a row. Re-protection empties old-level
    priors for the same scope, including unstamped rows and same-target retries. Emptied priors
    become `purged` stubs and undo refuses those runs.
  - App deletion and re-protection page only the owner's live re-derive runs, 200 IDs at a time.
    For `L` matching runs and `D` distinct conversation and bridge IDs, the lookup costs at most
    `L + 1` billed ledger reads and `L × D` prior point reads per attempt before transaction retries.
    Owners with no matching runs use one minimum query read and zero prior reads. The November 12
    phone cascade observation of about 1,400 deletes per day is a volume reference. The collection
    budgets allow 6,000 additional ledger reads and 12,000 prior reads per day, based on 2,000
    combined deletion and re-protection attempts at averages of three and six reads respectively.
    These are planning assumptions. Revisit the estimate with actual per-owner run history,
    duplicate attempts and migration batch sizes if observed traffic exceeds that scenario.
    [Firestore query billing](https://firebase.google.com/docs/firestore/pricing#minimum-charge-for-queries)
    A failed commit drops the copies of rows it did not write (a resume records them again).
    Each partition reads only its own copies, by id; `resume` and `undo` check every copy of the run
    once. A run whose undo refuses for good keeps its copies until the owner deletes the touched
    conversations or the account; delete the run's `conversations_v3_rederive_priors` only with the
    owner's approval, since it gives up the undo.
    A capture longer than one partition crosses both partitions' edges: the dry-run reports it as
    `windows_crossing_edge`; widen `since`/`until` around it or leave it.
    Restores are exact apart from the commit hook's `home_source_version` and
    `home_content_invalidated` stamps.
    `undo --run` keeps both builder leases renewed during preflight, refuses in-flight notes or
    lost leases, then restores each group of
    rows that share a source in one transaction: stored documents back exactly, created rows removed,
    each source's claim list back in its original order. It refuses (`undo.reason`) after the owner
    deleted a rebuilt row (`owner_deleted_rebuilt_row`), after the owner edited, shared, locked,
    merged or retitled a row the run wrote, created or retired (`owner_edited_rebuilt_row`; compared
    against the owner-surface digest each settled partition records), or while a newer live run
    restamped one (`undo_newer_run_first`: undo that one first). A standalone task linked to a card
    scheduled for removal also blocks undo (`undo_created_row_has_tasks`). The run checks all such
    cards before restoring any group and rechecks each group inside its transaction, including
    cards already hidden by an interrupted undo. Refinement absorption, repair retirement and undo
    each write a content-free, owner-scoped marker in the same transaction that hides the card.
    A linked task create reads that marker in its write
    transaction and checks the card itself only on a hit. The source-link switch leaves
    ordinary missing links alone when off. Account erasure removes the markers.
    An interrupted undo is rerun as is:
    rows it already restored, and created rows it already hid (`v3_rederive_live_undone`), are
    finished rather than refused. It also refuses once account deletion began (`account_deletion`),
    and before restoring anything when a group of rows sharing sources is too large for one
    transaction (`undo_group_too_large`). A later live speech append to a rebuilt row is
    replaced by the restored document. Before a partition settles, the run's own notes may discard a
    rebuilt card or add app results to it, so an owner discard or app run on that card in those few
    minutes is not told apart from the run's; undo the run only after it settles. Not undone: outline cache entries and gateway spend.

Rollout owner: lead2. Step 0: set CONVERSATIONS_V3_FIRST_APP_BUILD through the shared runtime source
from the first TestFlight build containing this PR. Then dev named accounts,
live/sync/late qualification and
current App Store/TestFlight fallback acceptance; prod named cohort only. Step 1:
beta in prod after that acceptance. Step 2: all within 12 hours if first-speech
visibility, end-to-summary latency, conversations/calls/cost per user-day,
share/delete/processing error rates, pending age and stuck counts remain clean,
and late rewrite cost share is at most 5%. Stage rollback or kill switch affects
new intake only; previously marked recordings continue draining.

Delete the old episode implementation in a follow-up only after stage all for
14 days, kill switch unused for seven days, episode calls below 1% of active
mobile sessions by app-build bucket, and completed/sample-verified 30-day backfill
for every active pendant owner (consecutive per-owner runs of at most 31 days each; the partitioned
runner above replaces V3-BACKFILL-30D-PARTITIONS and still has to qualify on named owners first). Episode routes continue returning disabled.
No source test, green CI, or generated client check is device acceptance or a
measured production outcome.
