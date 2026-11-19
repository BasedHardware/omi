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
A manually ended window with any speech is Home-visible regardless of length,
unless media or positively recognized background; no speech creates no window.
The persisted manual_end follows late rewrites, merges and backfill and requires
full notes even below 20 words. Background hides only with positive wearer
recognition somewhere in the contributing recordings: is_user:true or a
segment-bound wearer label from the authoritative speaker-evidence projection.
Without it, background becomes conversation and uses the normal 300-word rule
(or the manual-end override). Media stays hidden. home_hidden_reason records
this decision and outline_kind retains the original classification.
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
300-word threshold against that fresh stretch. Media, recognized background
and late fragments around published claims retain their own visibility rules.
Set the switch to `off` on v3 builder and backfill runners to restore the prior
prompt and per-topic Home minimum for subsequent passes. Existing published
windows and claims remain in place when the switch changes.

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
blocked for hours needs investigation, and an operator clears the park by deleting the three
`v3_blocked_*`/`v3_backoff_until` fields on `users/{uid}/conversation_v3_leases/builder`.

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
existing notes prompt; the v3 background lane is Luna/low, gateway Flex-first,
then Standard. The on-open lane is Standard. Metering stays in the gateway and
usage tracker. The section stream uses the chat `data:` / base64 `done:` /
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
  Otherwise it restores every donor field exactly, then deletes the run's derived rows. It writes no
  tombstones and touches no audio. A donor whose backfilled copy the owner deleted is not restored
  (that would resurrect the deletion): it stays a hidden source, together with every copy it shares
  and those copies' donors. The ledger and `undo --dry-run` count them (`donors_kept_deleted`,
  `rows_kept_deleted`, `donors_deleted_by_owner`). Undo a re-derive by undoing the original run;
  `undo` on a re-derive run id says so and exits 1. Not undone: outline cache entries, speaker-resolution and media-boundary
  evidence that the notes path wrote, and gateway spend.
- **Blocked.** A partition over the loader's 128-document limit, a planned id that is already a live
  row (`target_exists`), a tombstoned window, or a converted donor that no longer reads
  (`backfill_source_unreadable`; its copies are kept) blocks the run. The partition and its reason are
  recorded in the ledger. Fix the cause, then `resume`. Never describe a blocked or partial run as
  complete. `status` shows partitions committed, windows, Home-visible rows, outline calls and
  notes processed or failed.

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
