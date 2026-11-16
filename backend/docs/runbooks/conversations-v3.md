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
before rollout. Do not assume deploying one role updates the others.

Only new `omi`/`phone` capture/sync creates become recordings. Existing documents
keep their layer through stage changes. A recording is not a product item;
`home_hidden` only removes a conversation from unfiltered Home and its count.
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
task coalesces each owner-minute. The builder holds a Firestore token/expiry
lease, revision-checks sources and targets, and writes conversation copies and
recording claims together. A conflict retains pending work. The five-minute
sweeper recovers dispatch failures and processing obligations. Declare indexes
with `generate_firestore_indexes.py --write`; schema readiness is an operator
gate before admission. The builder and request summary share conversation leases.

Cached outlines are encrypted; transcript copies use the existing storage codec.
Finished-window copies retain user edits and stable titles. Recordings never
enter model processing, apps, memories or webhooks. Short speech of at least 20
words uses the existing task extraction rules and memory processing without a
summary call. Media/background have no derived processing. Summaries reuse the
existing notes prompt; the v3 background lane is Luna/low, gateway Flex-first,
then Standard. The on-open lane is Standard. Metering stays in the gateway and
usage tracker. The section stream uses the chat `data:` / base64 `done:` /
JSON `error:` protocol and stores only a complete revision-fenced result.

Legacy audio files are owner-checked aliases to recording files. Released
clients can request `/v1/sync/audio/{conversation}/urls` and individual alias
file downloads. They play whole covering files, as the plan accepts. New clients
use the window manifest. File-local offsets subtract deleted spans. Public
shares expose only the conversation's copied transcript. Claim release follows
durable deletion intent. Reclaim first closes/tombstones an unclaimed completed
recording; pending/live sources are retained. Existing privacy/hold guards own
physical deletion. A failed storage erase retains a purge obligation.

Metrics: episode calls by route template, bounded version bucket, app channel and
v3; episode compose attempts by v3; daily active pendant owners with latest
legacy capture; builder outcomes, pending age, first speech to visible, end to
summary, first/rewrite writes and model calls. Gateway usage supplies actual cost
and per-owner accounting; aggregate Prometheus labels never contain owner IDs.
The daily gauge refuses a truncated scan rather than publishing a partial count.

Backfill is `CONVERSATIONS_V3_BACKFILL=off` by default. The OIDC-only backfill
route derives the preceding 30 days, marks new rows `backfilled`, and changes
source layers in the projection transaction. Historical processing uses the
existing silent-backfill policy. The initial implementation refuses a user
window over 128 documents; operator partitioning is required before enabling
for larger histories. Do not describe a blocked or partial backfill as complete.

Rollout owner: lead2. Step 0: dev named accounts, live/sync/late qualification and
current App Store/TestFlight fallback acceptance; prod named cohort only. Step 1:
beta in prod after that acceptance. Step 2: all within 12 hours if first-speech
visibility, end-to-summary latency, conversations/calls/cost per user-day,
share/delete/processing error rates, pending age and stuck counts remain clean,
and late rewrite cost share is at most 5%. Stage rollback or kill switch affects
new intake only; previously marked recordings continue draining.

Delete the old episode implementation in a follow-up only after stage all for
14 days, kill switch unused for seven days, episode calls below 1% of active
mobile sessions by app version, and completed/sample-verified 30-day backfill
for every active pendant owner. Episode routes continue returning disabled.
No source test, green CI, or generated client check is device acceptance or a
measured production outcome.
