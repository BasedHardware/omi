# Episode log: shadow drain and read ramp

Owner: planscost. One backend train; no production backfill, config write,
alert install, merge or deployment is performed by this change.

## Storage and authority

All new data is inside `users/{uid}`: `episode_facts`,
`episode_log_state/owner`, `episode_log_checkpoint`, `episode_views`, and
`episode_view_links`. Existing recursive account deletion covers these namespaces.
The existing durable account-deletion marker also fences new independent fact/
policy writers and leased publication, including deletion accepted mid-drain.
The marker is read on the same Firestore plane and inside the publication
transaction, so an erased view cannot be recreated by an old worker.
No new deletion implementation is included. Conversations/audio remain owned by
conversation processing; episode workers never edit them.

Legacy writers continue serving throughout this dual-write stage. Serving
transactions register only content-free capture intent, with no log reads,
writes or owner locks. After a successful SDK commit, an instance-local observer
appends in a **separate transaction**, with at most two SDK commit attempts and
no outer retries. An aborted serving attempt emits no fact. Capture failures,
including encryption and oversize payloads, are caught, counted through shared
`omi_fallback_total{component="sync_dispatch",from="episode_capture",to="legacy"}`
and dropped; they cannot retry or replace a committed writer's response. The
post-commit append and policy refresh use a shared, lazy executor with four
workers and 64 queued items. Submission never waits for capacity. Overflow and
cancellation are counted drops. Only the small pre-write policy fence remains
synchronous; geometry compaction is allowlisted copying, without IO/encryption.
Every detected capture/entry/refresh drop writes a durable `capture_dirty` token,
clears Home readiness and advances the owner epoch, fencing older publishers.
Home automatically uses legacy for that owner, including at read percent 100.
Ordinary publication cannot clear the marker. The next drain performs a full
bounded reconciliation from current legacy episodes, links and receipt archives,
removes stale views/links and reprojects current member policy. Only atomic
publication under the unchanged epoch, gap token and append watermark clears it.
The full reconciliation scans at most 128 documents (including old projections
and archives); overflow fails closed on legacy rather than clearing the marker.
A completely unavailable data plane may also prevent persistence of the marker;
`invalidation_failed` is an error requiring repair before read readmission.
There is no durable outbox guarantee for process death between commit and append.
A caught-up watermark alone cannot prove a process-death gap did not occur.

Input-hook facts use the shared `utils/conversations/episode_attach_key.py:content_key`
digest, including revision, recorded evidence, ancestry and member flags. Unknown
proof gets a distinct uncertainty key. Lifecycle captures have unique decision
keys and carry structural geometry deltas plus episode/member references, never
full speech snapshots. Speech fields and current composer metadata are loaded
from the existing episode authority by the drain. Member facts contain only a
refresh reference. All fact writers, including backfill, strip speech using an
allowlist and cap the **encrypted payload at 64 KiB**. A larger fact is dropped on
the serving capture path and fails explicitly in the operator backfill path.

The new sync hook only appends a member dirty fact and schedules a wake. It does
not repartition or compose. The existing serving hook is retained during shadow;
its committed decisions supply the log's boundary/identity facts. This is
intentional dual-write, not an assertion that eager legacy costs have disappeared.
No-op domain decisions ignore lease/version/timestamp churn.

The projector ports the prototype's five rules: occupied/displaced IDs,
fence-adjacent growth, permanent wedge fences, retained bounds on discard, and
donor repoints retaining dead activity keys. The fold uses
`episode_recorded_components.partition()`. Arrival order is the log sequence;
recorded time still owns placement. Replaying a given sequence is deterministic.
A shuffle is compared with legacy in that same order; IDs legitimately differ
between different arrival orders.

Boundary decisions and content references are facts, not a second mutable status authority.
The fold feeds those facts through `derive_episode_phase`; the owner phase is
`derive_phase(log_watermarks_and_lease, now)`. Neither stores an extra status.
Fingerprints, composer metadata and consumed receipt IDs survive baseline/replay.
The drain only sets `compose_dirty`; it never calls a model or uses its lease as
paid-once proof. Batch 1's composer fingerprint/lease remains the paid authority.

## Durable scheduling and bounded recovery

The existing sync Cloud Tasks queue targets OIDC-only `/v2/episode-drain/run` on
backend-sync, using its existing sync audience/invoker binding. Wakes round to a
stable future 30-second bucket per UID; concurrent producers deduplicate. There
is no sleeping executor or new queue. The existing two-minute sync sequencer
Scheduler endpoint also sweeps at most 32 due owners and redrives wakes. Thus
an append whose producer dies before enqueue remains discoverable.
Each observed owner rotates its scan time by two minutes using a guarded update,
including disabled users and failed task dispatches. Caught-up owners without
barriers remove `scan_at` and `drain_at`, so idle owners leave the due query. The
sweep also removes old idle scan debt without waking it. This prevents a permanently
failing first page from starving later users; phase and drain deadlines do not move.

Each drain handles at most 64 facts and publishes at most 128 changed view/link
documents. It checkpoints the pure fold with compressed, independently sealed
200 KB parts (at most 24) and caps the complete transaction estimate at 8 MB.
Every read precedes every write in storage transactions. Cursor, checkpoint,
views, Home version and lease release publish atomically under owner + epoch +
unexpired lease. A stale worker cannot publish, even if its executor survived
request cancellation. A process killed before commit leaves the cursor intact.
Capacity overflow leaves facts intact, retries and alerts; it never partially
publishes or silently truncates history. Large-user partitioned checkpoints are
a follow-up capacity extension if measured accounts reach this guard.

| Derived automatic phase | Entry deadline | Exit/recovery | Dwell and alert |
| --- | --- | --- | --- |
| queued | durable quiet deadline = last activity + 3 min; hard deadline = first pending + 25 min; size 64 flushes now | lease claim, or bounded sweep after lost wake | `omi_episode_drain_dwell_seconds{phase="queued"}`, `OmiEpisodeLogQueuedOverdue` |
| running | ten-minute lease stamped on claim | atomic publication, retry, or epoch takeover after expiry | same histogram with `running`, `OmiEpisodeLogRunningOverdue` |
| retrying | 30-second retry deadline stamped on failure | next claim or sweep redrive | same histogram with `retrying`, `OmiEpisodeLogRetryingOverdue` |

Member policy edits attempt a separate best-effort read barrier before the
change and enqueue background refresh debt when it finishes. Entry/client/read/release
failures are caught and counted; the original writer runs exactly once and
retains its own result or exception. Sync/smart-merge transactions register
post-commit refresh intent, with no log IO in their serving transactions. A killed writer's barrier has a 25-minute deadline; the sweep
refreshes current member policy and unblocks only after that fact drains.
This applies to every existing log, including shadow users at zero read percent.
While any barrier/debt exists, reads use legacy policy. These barriers live in
the same queued phase and carry the same queued deadline and alert.

The backend-sync collector retains both drain and view metric families.
`OmiEpisodeLogSweepStale` detects stale or entirely absent sweep observations; silence in deadline
counters is insufficient evidence of a healthy scheduler. The PrometheusRule in
`charts/monitoring/episode-log/alerts.yaml` is a reviewable artifact for the train
owner to install with the existing metrics scrape.

## Switches and read admission

- `EPISODES_LOG_ENABLED`: remote Omi flag-store rule is authoritative; when absent,
  the env value defaults **false**. Remote inactive stops capture, drain, wakes,
  sampling and read admission after the cached rule refresh, normally up to about
  **60 seconds**. Refresh failures retain the last snapshot, so this is not a hard
  maximum. Already committing work completes; the drain cheaply rechecks the
  cached rule before publication and defers if it now sees the kill. The TTL
  safety guard still runs while capture is off. Queued intent rechecks admission
  after commit. The
  existing flag CLI supports this Firestore key; no deploy is needed to stop it.
- `EPISODES_HOME_ROWS_ENABLED`: on unless off. Rows are sealed, server-filtered
  wire projections (member IDs, titles, emoji, starts, visibility and floor).
  Off returns Home to legacy. Missing or policy-outdated Home rows also fall back.
- `EPISODES_LOG_READ_PERCENT`: default 0. An Omi flag-store rule with this key is
  authoritative; its `rollout_percentage` admits UID cohorts. Change it using the
  existing flag-store operator procedure, without creating a Cloud Run revision.
  An absent rule uses the numeric env percentage, still default 0. An inactive
  remote rule rolls reads back within the flag refresh window (up to 60 seconds).
  At zero, Home performs no episode-log reads, fact appends or wake dispatches;
  the 1% sampler and expired-clock/row refresh hooks use the same read admission.
  Post-drain comparisons continue independently in shadow.

Rollback order: set reads to zero (or the remote rule inactive) before disabling
`EPISODES_LOG_ENABLED`. After any capture gap, keep reads inactive until an
approved fresh baseline has drained and been compared. A previous backfill
marker does not cover writes made while capture was off.

A selected user also needs `backfill_complete`, a caught-up cursor, Home rows,
no policy barrier and no `capture_dirty` marker. No incomplete user can flip. Direct reads follow view
redirects and view navigation/membership links; live polling preserves the
legacy idle-close/conflict handling before choosing a ready view.

`GET /v1/episodes` returns an opaque `home_version`, ETag, and numeric
`X-Omi-Home-Version`. Send that ETag as `If-None-Match`, or the opaque value as
`home_version`. Matching a ready user's exact window/page/policy returns 304
before the page query and member reads. It still reads one small authoritative
owner document; this PR does **not** claim zero Firestore reads. Tokens include
UID, window, limit, cursor and server policy. Responses are private/no-cache;
there is no cross-user/CDN cache. New clients can adopt this in the next app train.
Existing clients continue receiving compatible full responses.

Cached Home policy expires at the earliest live idle-close, temporary settling,
batch transcription deadline or batch-1 pending-compose maximum-settle deadline. A cached 200 preserves the
existing bounded foreground composition repair for dirty rows; an old pending
compose cannot stay behind 304 forever after a process restart. The composer
retains its fingerprint/lease authority; the drain only writes dirty intent. An expired owner cannot answer 304: it appends one deduplicated, urgent
member-refresh fact and serves the existing legacy policy while the worker drains.
Quiet closes still occur through the legacy read lifecycle, never in the shadow
worker. Settling clocks are bounded to 128 per user; overflow uses the existing
capacity retry/alert and legacy fallback for the entire user, including other
view updates. Do not truncate clocks: that could admit stale visibility policy.
Partitioned checkpoints/clocks require a separately qualified capacity extension. Permanent below-floor verdicts never expire.

All visibility, below-floor suppression, neutral titles and member filtering stay
server-side. #24541's client layout contract is unchanged: pin after two seconds,
release on pull-to-refresh, resume or re-entry. No mobile layout code changes here.

## Backfill (dev/emulator only in this change)

The script defaults to a pure dry run with an input record list encoded by the
log JSON codec (`namespace`, `id`, `data`, and archive index where applicable).
It can also scan one explicit dev/emulator UID in bounded document pages.
Production project `based-hardware` is refused, including `--apply`.

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/backfill_episode_log.py \
  --uid synthetic-user --input /path/to/synthetic-records.json
# With the authorized dev tier, a separate operator may use:
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/backfill_episode_log.py \
  --uid dev-user --project based-hardware-dev --apply
```

It converts episode snapshots, fixed/discard/wedge fences, redirects, current/
last-closed/member links, base receipts and all `s/{index}` archives. Stored
`composed_fingerprint`, version and consumed-ID sets are copied as structural
metadata. Speech and current notes hashes are fetched by reference when projecting.
The backfill watermark follows the facts; serving waits until it drains.
Restarting deduplicates input records. A stale backfill never replaces a newer
observed episode or link decision. Historical spans are coarser envelopes; this
does not invent delivery-level history or change client-held IDs.

## Train order, ramp and verification

This branch includes merged read/write trims #24577 and attach/gate #24582.
The shared digest normalizes the capture ID at memo verification as well as fact
append, including raw documents without a stored ID. Cached fence reads, completed
memo hits, conditional membership writes and invalidation remain intact.
Composer #24579 and batch close #24544 are also included. Metadata-only batch
close stamps enqueue post-commit member-refresh facts, including a proof-hit whose
episode shape does not change. Home caches expire at the transcription deadline
and late projection receipts restore the normal cached metadata.
The phase shadow already on main remains active.

Rollout order is **TTL apply (ops) -> capture on -> drift soak -> read ramp**.
The separately authorized operator first applies the reviewed retention policy
with `batch_pipeline_ttl.py --apply` and verifies ACTIVE. This task does not apply it.
Then enable the remote capture rule using `scripts/omi_flags.py set
EPISODES_LOG_ENABLED --active --rollout 100 --episode-data-project based-hardware`
with the normal reason/approval options. The CLI checks ACTIVE TTL in that explicit
customer-data project before writing the flag; the flag-store project is separate.
Every runtime fact writer also refuses capture unless a read-only TTL check is
ACTIVE (cached at most 60 seconds; errors fail closed). The existing scheduler
runs a periodic guard even with capture off, logging
`event=episode_log_ttl outcome=facts_without_active_ttl` and publishing
`omi_episode_facts_without_active_ttl`; the reviewed alert and sync collector
include that metric. Runtime needs read-only field-policy inspection permission.
After capture admission, soak drift before starting the 5/25/50/100 read ramp.

After the authorized backend train, inspect each traffic-serving revision's
`OMI_BACKEND_RELEASE_SHA` and percentage, then a new drain metric/log from that
artifact. Do not infer deployment from the service spec or a green local test.
Confirm queue OIDC binding, the existing Scheduler tick, due-owner index readiness
and installed alerts. Run synthetic dev backfill/replay before any separately
approved production migration. This change does not authorize that migration.

Planscost owns expansion **5 -> 25 -> 50 -> 100**, one full clean day per step,
review by 2026-11-18. Gate each step on:

```promql
sum(increase(omi_episode_view_drift_total{outcome!="match"}[24h])) == 0
sum(increase(omi_episode_drain_deadline_total[24h])) == 0
histogram_quantile(0.99, sum by (le) (rate(omi_episode_drain_seconds_bucket[1h])))
sum by (outcome) (increase(omi_episode_compose_total[24h]))
```

Require nonzero comparison volume and fresh sweep observations, not just a zero
error rate. `omi_episode_view_drift_total{field,outcome}` has a fixed field set
and no UID labels: post-drain canonical digest compare plus 1% list-read sampling (at most three rows per sampled request).
A mismatch is re-read once before counting to reduce in-flight false positives.
Comparisons bracket source reads with a caught-up log watermark. Pending batches,
concurrent mutations, and sampled users awaiting backfill are deferred through
`omi_episode_view_compare_skipped_total{reason}` rather than counted as drift.
Require nonzero aligned comparison volume before treating zero drift as evidence.
Never compare randomized ciphertext bytes. Watch composer and moment receipts
for a recomposition/double-consumption wave, task dispatch failures, and Home 200/
304 wire canaries in admitted and legacy cohorts. Roll reads back before repair.

The dated [cost assumptions and validation record](../evidence/2026-11-04-episode-log.md)
owns the forecast and its limitations. In particular, each tracked member edit
adds two fenced transactions (four writes and three owner reads), and independent
drift comparison reads authoritative members again in one batch. Include these
operations, retained log/index storage and vendor usage when measuring the ramp.
The drain itself introduces no paid model call. Legacy consolidation remains
active, so the wider architecture savings are not realized by shadow migration.

## Fact retention and conversation privacy

Facts contain no conversation content, even after a conversation delete or
tombstone; only IDs, geometry, state flags, fingerprints and receipt IDs remain.
No historical transcript, title, bullets, notes, names, structured member data,
or encrypted content blob is copied into a fact. This covers mutation, member
and backfill producers. Account deletion retains recursive `users/{uid}` erasure
and the durable publication fence.

Each fact has `expires_at = recorded_at + 24 hours`, the shortest retained window
that supports the ramp's one-full-day drift comparison. The reviewed TTL policy
is [`deploy/episode-log/retention.json`](../../deploy/episode-log/retention.json).
It uses the existing TTL-only operator (which never changes indexes):

```sh
# Read-only local plan; no credentials or cloud clients:
backend/.venv/bin/python backend/scripts/batch_pipeline_ttl.py \
  --project based-hardware --policy backend/deploy/episode-log/retention.json
```

The separately authorized train owner must apply that policy and verify ACTIVE
before enabling capture in production; **this PR does not activate a live TTL**.
The index reconciler intentionally rejects TTL changes, so this declaration is
separate from `firestore.indexes.json`. Storage is a rolling one-day target plus
TTL deletion lag and index/document overhead, not a strict physical 24-hour
ceiling. Measure expiry lag and retained bytes; disable capture if TTL stalls.
Checkpoints preserve the fold beyond fact expiry. A worker behind the retained
window fails closed on a sequence gap and remains off the read path until an
approved fresh baseline is installed; do not extend retention silently. Replay
from facts alone is supported only within the retained window.

## Documented follow-up only

After seven clean days at 100%, planscost must present replay checks and obtain
specific approval before legacy receipt/link/fence/episode removal. Keep all old
namespaces through this PR. No legacy delete code, production backfill, writer-freeze
switch, Postgres move or data cleanup is shipped here.
