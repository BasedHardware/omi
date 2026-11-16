# Recording-derived conversations v3

Admission defaults to `CONVERSATIONS_V3_STAGE=beta`. `CONVERSATIONS_V3=off`
stops marking new mobile pendant documents. Stages are `cohort`, `beta`, `all`;
`rollout_cohorts/conversations-v3` is for named qualification accounts. Beta uses
the shared, refreshed 14-day episode client-seen marker, so all devices of an
owner agree. No client version gate is introduced.

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
captures and reconnects do not themselves split a continuous stretch. The
two-hour cap still bounds each resulting window. Missing transcript is not
proof of acoustic silence; qualify transcript completeness separately.
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

Each source has a durable `v3_pending` obligation. Tasks use the dedicated `conversations-v3`
Cloud Tasks queue and the configured sync origin/OIDC identity unless
`CONVERSATIONS_V3_TASKS_QUEUE` / `CONVERSATIONS_V3_TASKS_URL` override them. A named
task coalesces each owner-minute. Explicit manual ends use a separate,
deterministic source-close task name so an already completed live task in the
same minute cannot swallow the close. They do not wait for the silence deadline.
Automatic end detection still waits five minutes of speech quiet; this is not
a measured 30-second end-to-notes guarantee. On-open Standard notes stream
through the existing summary endpoint without that background close wait.
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

Backfill is `CONVERSATIONS_V3_BACKFILL=off` by default. The OIDC-only backfill
route derives the preceding 30 days, marks new rows `backfilled`, and changes
source layers in the projection transaction. Historical processing uses the
existing silent-backfill policy. The initial implementation refuses a user
window over 128 documents; operator partitioning is required before enabling
for larger histories (follow-up V3-BACKFILL-30D-PARTITIONS). Do not describe a blocked or partial backfill as complete.

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
for every active pendant owner. V3-BACKFILL-30D-PARTITIONS must ship and qualify
before enabling backfill or claiming this deletion gate. Episode routes continue returning disabled.
No source test, green CI, or generated client check is device acceptance or a
measured production outcome.
