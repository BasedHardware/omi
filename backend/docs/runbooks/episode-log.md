# Episode log: shadow drain and read ramp

Owner: planscost. One backend train; no production backfill, config write,
alert install, merge or deployment is performed by this change.

## Storage and authority

Everything is inside `users/{uid}`: `episode_facts`,
`episode_log_state/owner`, `episode_log_checkpoint`, `episode_views`, and
`episode_view_links`. Existing recursive account deletion covers these namespaces.
No new deletion implementation is included. Conversations/audio remain owned by
conversation processing; episode workers never edit them.

Legacy writers continue serving throughout this dual-write stage. Each episode
transaction reads the per-user append sequencer before its first write, then
atomically appends its committed input/decision envelope. A transaction rollback
stores neither the mutation nor its fact. Input-hook facts use the shared
`utils/conversations/episode_attach_key.py:content_key` digest, including revision,
recorded evidence, ancestry and member flags. IDs are included so distinct
captures with identical evidence cannot collide in a per-user log. Unknown
recorded/transcript proof gets an explicitly separate uncertainty key, never a
memo hit. Other lifecycle facts use their sequence and decision digest: a close
and compose have no conversation attach revision to reuse.

The new sync hook only appends a member dirty fact and schedules a wake. It does
not repartition or compose. The existing serving hook is retained during shadow;
its committed decisions supply the log's boundary/content/identity facts. This is
intentional dual-write, not an assertion that eager legacy costs have disappeared.
No-op domain decisions ignore lease/version/timestamp churn.

The projector ports the prototype's five rules: occupied/displaced IDs,
fence-adjacent growth, permanent wedge fences, retained bounds on discard, and
donor repoints retaining dead activity keys. The fold uses
`episode_recorded_components.partition()`. Arrival order is the log sequence;
recorded time still owns placement. Replaying a given sequence is deterministic.
A shuffle is compared with legacy in that same order; IDs legitimately differ
between different arrival orders.

Boundary and content decisions are facts, not a second mutable status authority.
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
including disabled users and failed task dispatches. This prevents a permanently
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

Member policy edits fence view reads before the change and append refresh debt
when it finishes. A killed writer's barrier has a 25-minute deadline; the sweep
refreshes current member policy and unblocks only after that fact drains.
This applies to every existing log, including shadow users at zero read percent.
While any barrier/debt exists, reads use legacy policy. These barriers live in
the same queued phase and carry the same queued deadline and alert.

`OmiEpisodeLogSweepStale` detects missing sweep observations; silence in deadline
counters is insufficient evidence of a healthy scheduler. The PrometheusRule in
`charts/monitoring/episode-log/alerts.yaml` is a reviewable artifact for the train
owner to install with the existing metrics scrape.

## Switches and read admission

- `EPISODES_LOG_ENABLED`: on unless explicitly off; off disables capture, drain,
  wake/sweep work, sampling and the read flip. Legacy remains the serving path.
- `EPISODES_HOME_ROWS_ENABLED`: on unless off. Rows are sealed, server-filtered
  wire projections (member IDs, titles, emoji, starts, visibility and floor).
  Off returns Home to legacy. Missing or policy-outdated Home rows also fall back.
- `EPISODES_LOG_READ_PERCENT`: default 0. An Omi flag-store rule with this key is
  authoritative; its `rollout_percentage` admits UID cohorts. Change it using the
  existing flag-store operator procedure, without creating a Cloud Run revision.
  An absent rule uses the numeric env percentage, still default 0. An inactive
  remote rule rolls reads back within the flag refresh window (up to 60 seconds).

A selected user also needs `backfill_complete`, a caught-up cursor, Home rows,
and no policy barrier. No incomplete user can flip. Direct reads follow view
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

Cached Home policy expires at the earliest live idle-close or temporary settling
deadline. An expired owner cannot answer 304: it appends one deduplicated, urgent
member-refresh fact and serves the existing legacy policy while the worker drains.
Quiet closes still occur through the legacy read lifecycle, never in the shadow
worker. Settling clocks are bounded to 128 per user; overflow uses the existing
capacity retry/alert and legacy fallback. Permanent below-floor verdicts never expire.

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
`composed_fingerprint`, `composed_notes`, version and consumed-ID sets are copied.
The backfill watermark follows the facts; serving waits until it drains.
Restarting deduplicates input records. A stale backfill never replaces a newer
observed episode or link decision. Historical spans are coarser envelopes; this
does not invent delivery-level history or change client-held IDs.

## Train order, ramp and verification

At implementation start #24577, #24579, #24582 and #24544 were open. Land batch
close #24544 and the compatible batch-1 attach/gate #24582, composer #24579, and
read/write trims #24577 before this PR, or co-rebase them onto one train. Reconcile
the shared gate helper and transaction seams without duplicating append hooks.
The phase shadow already on main remains active.

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

Cost forecast from the supplied 2026-11-04 aggregate study: the conservative dual-write here budgets roughly
$5–12/day in extra fact/dirty writes at the current trigger rate, plus the bounded wake/sweep overhead (study allowance $0–2/day).
Allow another $1–2/day for control-document reads and scan rotation: roughly
$6–16/day total shadow overhead, to be verified against billed operations.
Home rows and conditional requests target $6–10/day of read savings after the
cohort/app ramp. The design's broader **$30–40/day incremental batch-2 saving**
includes retiring eager legacy consolidation, which this dual-write PR does not
claim to have realized. Full redesign target $95–130/day is a forecast for the
study's cohort, with composer uncertainty and rollout growth. Re-measure reads,
writes and tasks normalized by admitted sync volume; include vendor composer
usage in the total. No new paid work is introduced by the drain.

## Documented follow-up only

After seven clean days at 100%, planscost must present replay checks and obtain
specific approval before legacy receipt/link/fence/episode removal. Keep all old
namespaces through this PR. No delete code, production backfill, writer-freeze
switch, Postgres move or data cleanup is shipped here.
