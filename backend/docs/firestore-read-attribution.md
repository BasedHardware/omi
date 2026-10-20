# Firestore read attribution

`database/firestore_document_probe.py` counts billed-equivalent Firestore reads
for every process that imports `database/_client.py`. The patch is on the SDK
classes, so a later `firestore.Client()` in that process is covered. Recording
does no network I/O, adds no Firestore reads, and never raises into the caller.

The daily bill-reconcile coverage numerator is the cumulative JSON read ledger
emitted when `FIRESTORE_READ_LEDGER=1`. The service label is
`FIRESTORE_READ_LEDGER_SERVICE` when that is set, otherwise Cloud Run
`K_SERVICE` or `CLOUD_RUN_JOB`, otherwise `DD_SERVICE`. GKE listen and pusher
use `DD_SERVICE` (`backend-listen` and `pusher`). `memory-maintenance-job`
uses `CLOUD_RUN_JOB` so runtime env does not add another copy of that job name. The ledger reuses the probe's billed
`amount` and `kind`, scoped to clients in `based-hardware`; unknown client
projects are counted and mark the day incomplete. It is sampled at p=1, so
sampling error is zero. `backend` and `backend-listen` must show a snapshot
in the last 15 minutes of the UTC day; other required services must appear
at least once. `pusher` stays in the shipped set and its rows still count,
but prod pusher is still the pre-ledger image, so a missing pusher snapshot
is a recorded exclusion and does not make the day incomplete. Clear
`COMPLETENESS_EXCLUDED` in `backend/scripts/firestore_read_reconcile.py`
once a normal promotion is serving pusher on a ledger SHA. That puts the
loud missing-snapshot exit back. A cron job that exits earlier does not fail the
day. Crash loss after the last snapshot stays unquantified. Index-entry and other
billing-model bias is not quantified. The ±2% band is an operational allowance,
not proof that bias is under 2%.

Daily outcomes are `healthy`, `audit_required`, `accounting_failure`, and
`incomplete`. The reconcile workflow only reads billing and ledger logs; it
does not turn on Firestore `DATA_READ` audit logging.

The separate Prometheus counter is `omi_firestore_billed_reads_total`. Do not add
`omi_firestore_document_reads_total`, `omi_firestore_query_operations_total`,
`omi_firestore_documents_per_operation`, or
`omi_firestore_document_reads_by_site_total` to it. Those answer different
questions and would double-count.

## Kind and Cloud Monitoring type

| `kind` | Cloud Monitoring `type` | What is counted |
|---|---|---|
| `lookup` | `LOOKUP` | `DocumentReference.get` / `get_all` that returns a document |
| `not_found` | `NOT_FOUND` | the same lookups when the document does not exist |
| `query` | `QUERY` | documents yielded by a query, the one-read empty minimum, configured `offset` skips, aggregation batches, `list_documents`, `get_partitions`, and one read per `collections()` RPC |

`omi_firestore_billed_reads_by_caller_total` is the same reads with a
`module:function` caller and no tier label. The frame is the first product
function on the stack. `database._client`, `database.helpers`,
`database.read_boundary`, `utils.other.list_budget`, `utils.executors`, this
probe, and `google` / `asyncio` / `threading` / `contextlib` / `concurrent`
frames are skipped.

An AST scan of `backend/database` and `backend/utils` on 2026-09-23 found 921
functions that call a Firestore read. The cap is 1536, that count plus headroom
for routers, services, and new call sites. The set is not pre-created. A
well-formed caller that arrives after the cap is full is labeled `other` and
`omi_firestore_caller_label_overflow_total` increments. A non-zero rate means
new call sites are no longer named. Collection patterns are the allowlist in
the probe (`users/*/memory_items` becomes `users/memory_items`).

```promql
sum(rate(omi_firestore_caller_label_overflow_total[30m]))
```

## PromQL dashboard guidance (not the bill reconcile)

The stackdriver exporter publishes
`firestore.googleapis.com/document/read_count` as the gauge
`stackdriver_firestore_instance_firestore_googleapis_com_document_read_count`.
The gauge value is the count for a 60-second window. Use `avg()` across
exporter replicas and `avg_over_time(...) / 60` for reads per second. `rate()`
on that gauge is not a read rate. This dashboard comparison is not a 60-second
read-count error bar and is not the daily bill reconciliation.

Use a window of at least 30 minutes, and only after every replica of every
instrumented service is running this probe.

```promql
# QUERY coverage
sum(rate(omi_firestore_billed_reads_total{kind="query"}[30m]))
/
(
  avg_over_time(avg(stackdriver_firestore_instance_firestore_googleapis_com_document_read_count{type="QUERY"})[30m:1m]) / 60
)

# LOOKUP coverage
sum(rate(omi_firestore_billed_reads_total{kind="lookup"}[30m]))
/
(
  avg_over_time(avg(stackdriver_firestore_instance_firestore_googleapis_com_document_read_count{type="LOOKUP"})[30m:1m]) / 60
)

# NOT_FOUND coverage
sum(rate(omi_firestore_billed_reads_total{kind="not_found"}[30m]))
/
(
  avg_over_time(avg(stackdriver_firestore_instance_firestore_googleapis_com_document_read_count{type="NOT_FOUND"})[30m:1m]) / 60
)

# Overall coverage
sum(rate(omi_firestore_billed_reads_total[30m]))
/
(
  avg_over_time(sum(avg by (type) (stackdriver_firestore_instance_firestore_googleapis_com_document_read_count))[30m:1m]) / 60
)
```

Which code produced the QUERY reads:

```promql
topk(20, sum by (caller, collection) (rate(omi_firestore_billed_reads_by_caller_total{kind="query"}[30m])))
```

## Acceptance

For dashboard investigation only, after deploy each of the three type ratios
and the overall ratio should be **≥ 95%**. A short window while old replicas
are still serving will sit below that. A ratio that stays below 95% after the
fleet is on this commit is a reader this probe does not see, or the
index-entry residual below. These ratios do not determine the daily bill
reconcile outcome.

## What stays outside the numerator

- Queries with two or more range fields, and kNN `find_nearest`, also bill
  index-entry batches the stream does not report. The document reads are
  counted; those extra index reads are not.
- `sum()` / `avg()` aggregations bill one read per 1000 index entries. The SDK
  does not expose that count, so the probe bills the one-read minimum.
  `count()` uses `ceil(value / 1000)` with a floor of 1.
- Cloud Functions and browser SDKs, listed below. Their reads remain in the
  billed denominator.
- A process that never imports `database/_client.py`.

## Processes

Importing `database/_client.py` installs the probe. These production
entrypoints do that before they read:

| Process | Entrypoint | Covered because |
|---|---|---|
| backend, backend-listen, backend-sync, backend-sync-backfill | `backend/main.py` | imports `routers`, which import `database` |
| backend-integration | `backend/main.py` | imports the same database-backed router process and is included in the required ledger service set |
| llm_gateway | `backend/llm_gateway/main.py` | Gateway still records provider accounting through its retained accounting boundary |
| desktop-backend | `backend/desktop_backend.py` | imports `routers` |
| pusher | `backend/pusher/main.py` | imports `routers.pusher`, which imports `database.users` |
| memory-maintenance-job | `backend/modal/memory_maintenance_job.py` | maintenance cron imports `database._client` |
| day3-reengagement-email-job | `backend/modal/day3_reengagement_email_job.py` | imports `database._client` |
| frame-request-retention-job | `backend/modal/frame_request_retention_job.py` | retention service imports `database._client` |
| notifications-job | `backend/modal/job.py` | `utils/other/jobs.py` imports `utils/x_connector.py`, which imports `database._client` |

`diarizer`, `parakeet`, `nllb-translation`, and `plugins` do not construct a
Firestore client.

Production `firestore.Client(` construction is in `backend/database/_client.py`.
There is no `firebase_admin.firestore.client(` and no product `AsyncClient(`.
Operator and emulator scripts that call `firestore.Client(` without importing
`database._client` are not covered. They are not the always-on fleet. Scripts
that import a module which imports `_client` (for example
`backend/scripts/enrich_historical_memory_graph.py`) are covered by the class
patch. Scripts that do not, including
`backend/scripts/support/find_stripe_entitlement_mismatches.py` and
`backend/scripts/scan_wake_word_variants.py`, are not.

## Readers this Python probe cannot see

Measure these as the residual: billed reads minus the ledger sum, after the
Python fleet is on this commit. Server SDK traffic is `module="__unknown__"`
in Firestore audit logs, so a module filter does not name them. The daily
workflow does not enable DATA_READ. Turning that audit log on requires
`resourcemanager.projects.setIamPolicy`, which this measurement job does not hold.

| Reader | Path | What it reads | How to measure |
|---|---|---|---|
| `getOrgConversations`, `searchOrgConversations`, `getOrgActionItems`, `modifyActionItem` | not in this repo | org conversation and action-item documents | residual after the Python probe; function instance count in Cloud Monitoring if the function runtime exports one |
| `acceptInvitation`, `inviteUser`, `declineInvitation`, `manageUser`, `cleanupExpiredInvitations` | not in this repo. `web/admin/lib/services/invitation.ts` calls `inviteUser` | invitation and membership documents | same residual. `inviteUser` is a callable, so its reads are not in the admin page's browser SDK |
| `ext-firestore-typesense-conversations-indexonwrite`, `ext-firestore-typesense-conversations-backfill` | Firebase Typesense extension, not in this repo. Still installed; see `backend/utils/conversations/typesense_index.py` | conversation documents on write and backfill | residual. Uninstall is a separate change |
| admin web client | `web/admin/components/auth-provider.tsx` `getDoc` on `adminData/{uid}` | one admin document per signed-in session | Firebase client SDK, not this process. Count it inside the residual, or with a client-side counter that is not in Prometheus today |
| personas web client | `web/personas-open-source/src/lib/firebase.ts` and the `getDocs` / `getDoc` calls under `web/personas-open-source/src/app/` | `plugins_data` and `users` | same. This tree has no `.onSnapshot(` / `.on_snapshot(` call |

Mobile clients in this repo do not use `cloud_firestore`.

## Origin attribution (always on)

`omi_firestore_billed_reads_by_origin_total{origin,collection,kind}` records the
same amount at the same `_record` boundary as `omi_firestore_billed_reads_total`.
Do not add the two counters. No lever controls origin accounting. It performs no
additional Firestore/Redis calls and cannot change a read's result or exception.
The new work per read is bounded dictionary/set lookups and one counter increment;
collection-group aliases are precomputed rather than scanning the allowlist.

`FirestoreTierMiddleware` binds the live ASGI scope for HTTP and WebSocket
requests. Recording lazily reads `scope['route'].path` after Starlette has routed
it: `http:/v1/users/{uid}` or `ws:/v4/listen`. It never labels `scope['path']`.
Before a route is known, the label is `http:unmatched` or `ws:unmatched`. A context
without a request or named task/job is `unset`. Auth/executor copies preserve the
ContextVar through the existing `run_blocking`/`submit_with_context` helpers.
Bare new threads and raw executor submissions require explicit context copying.

```python
from database.firestore_read_origin import read_origin

with read_origin('job:daily_summary'):
    run_daily_summary()

@read_origin('job:memory_maintenance')
async def maintain():
    await run_maintenance()
```

Use source-code constants, never uid/job/session IDs, payload fields or raw URLs.
The context manager also decorates synchronous functions; async decorators cover
the entire awaited invocation. `start_background_task(coro, name='worker')`
automatically sets `task:worker` in the created task's context, leaving its actual
name, coroutine, cancellation and completion callback unchanged. Existing dynamic
task names are normalized to registered families (for example
`sync_pipeline:<job_id>` → `task:sync_pipeline`,
`fair_use_classifier:<uid>:<session_id>` → `task:fair_use_classifier`,
`x_initial_sync_<uid>` → `task:x_initial_sync`). Extend the fixed family registry
when introducing another dynamic task-name format.

Names register only on observation. At most 400 distinct route/job/task origins
are retained per process, plus `unset`, unmatched and `overflow` buckets.
`omi_firestore_origin_label_overflow_total` increments for observations rejected
by the cap. There is no origin × collection × kind pre-initialization. The first
read creates its series. The collection allowlist includes account cutover,
client devices, prompt/usage state, durable queues, daily summaries, dreams,
finalization, sync backfill/content/dead-letter collections and fixed batch
pipeline namespaces; document IDs are removed before matching.

With the existing `FIRESTORE_READ_LEDGER=1`, schema-2 cumulative snapshots also
carry `reads_by_origin`. It uses the same accumulator boundary and project scope
as the old kind/tier fields and resets with them at UTC day rollover. All old
fields and reconciliation semantics remain intact; the existing reducer ignores
this additional field.

After every relevant replica has upgraded, check both counter parity and the
named fraction in the same production scrape scope:

```promql
# Must remain 1 (no double counting or lost origin observations).
sum(increase(omi_firestore_billed_reads_by_origin_total[1h]))
/ sum(increase(omi_firestore_billed_reads_total[1h]))

# Conditional attribution among probe-observed backend reads; target >= .90.
sum(increase(omi_firestore_billed_reads_by_origin_total{origin!~"unset|overflow|http:unmatched|ws:unmatched"}[1h]))
/ sum(increase(omi_firestore_billed_reads_by_origin_total[1h]))

# Rank origins and collections; compare identical windows before/after a lever.
topk(30, sum by (origin, collection) (increase(omi_firestore_billed_reads_by_origin_total[1h])))

sum(increase(omi_firestore_origin_label_overflow_total[1h]))
```

At least two scrapes of a newly created series are needed for `increase()`; its
first observation is not a precreated zero. These checks alone do not establish
that 90% of **billed fleet reads** are named: reconcile coverage against Cloud
Monitoring/billing as above, add the separately logged admin reads, and account
for uninstrumented services and index-entry residuals. No production coverage
claim is justified by unit tests.

## Admin server reads

`web/admin/lib/firebase/admin.ts:getDb()` returns a cached Firestore facade.
It counts document/query/collection-group `get`, `getAll`, transaction reads,
query streams, empty-query floors, offsets and `count()` batches (ceil(count/1000),
minimum 1). Writes use the original SDK objects. SDK internal funnels are not
wrapped, preventing duplicate counting. Snapshot accessors remain synchronous;
returned snapshot refs and query builders retain instrumentation. Arbitrary
sum/avg aggregates retain the one-read minimum estimate. Reads through the default
`admin` export or other SDK instances bypass this facade; callers should use
`getDb()`.

The installed Next 16 runtime's work and request AsyncLocalStorage stores supply
the router-owned template and request identity. One `after()` callback per request
emits one structured `firestore_read_ledger` JSON line, including the precompute
request at `http:/api/internal/precompute`. No route edits are necessary. These
Next internal store imports must be checked when upgrading Next. Non-Next scripts
can use the explicit sync/async boundary:

```typescript
import { withFirestoreReadLedger } from '@/lib/firebase/read-counter';
await withFirestoreReadLedger('job:stats_precompute', () => runPrecompute());
```

Each admin request/run has its own epoch and `seq=1`, with schema 2,
`service=web-admin`, UTC `day`, `lookup`, `not_found`, `query`, `origin`,
`reads_by_origin` and `reads_by_collection`. Final rows may be summed after
deduplicating `(service,epoch,day,seq)`; they are not backend process-cumulative
snapshots. The ledger excludes known non-`based-hardware` projects and marks
unknown SDK project identity with `unscoped=1`, matching Python's conservative
scope rule. The bounded in-process counter snapshot is exported by
`firestoreReadCounts()` (origin × reviewed collection name × kind, plus origin
overflow). Admin collection labels use the final collection name, so collection
group and nested reads can be compared without document IDs.

The Python reconcile tool's shipped-service allowlist currently excludes
`web-admin`; an integrator must explicitly add it before counting these rows in
that tool. Keep Cloud Run logs enabled. A request killed before its `after()`
callback loses that request's ledger; in-process counters are still updated.
Standalone code outside Next must provide an explicit run boundary to emit a row.
Neither implementation adds a fallback database read to recover missing context.

### Integrator entrypoint wiring

Import `read_origin` from `database.firestore_read_origin`. Put each decorator
immediately above the function and below any router decorator. Already launched
named tasks receive `task:` labels automatically; these optional `job:` overrides
make the durable origin independent of the launcher. Do not apply a decorator
and an overlapping context for the same entrypoint.

| Entrypoint | Exact line |
|---|---|
| `main.py:_periodic_deletion_wipe_reconcile` | `@read_origin('job:periodic_deletion_wipe_reconcile')` |
| `main.py:_periodic_listen_finalization_reconcile` | `@read_origin('job:periodic_listen_finalization_reconcile')` |
| `main.py:_drain_pending_deletion_wipes` | `@read_origin('job:startup_deletion_wipe_reconcile')` |
| `main.py:_drain_listen_finalization_jobs` | `@read_origin('job:startup_listen_finalization_reconcile')` |
| `main.py:_drain_stale_processing_conversations` | `@read_origin('job:startup_stale_processing_reconcile')` |
| `main.py:_drain_stale_in_progress_conversations` | `@read_origin('job:startup_stale_in_progress_reconcile')` |
| `main.py:_drain_abandoned_byok_finalization_jobs` | `@read_origin('job:startup_byok_abandonment_reconcile')` |
| S2's `main.py:_run_fsr_loop` (alternative fine-grained override around its existing body; loop names are S2's fixed registry) | `with read_origin(f'job:{loop_name}'):` |
| `modal/job.py:main` (notifications + daily summaries) | `@read_origin('job:notifications')` |
| `modal/x_connector_sync_job.py:main` | `@read_origin('job:x_connector_sync')` |
| `modal/memory_maintenance_job.py:main` | `@read_origin('job:memory_maintenance')` |
| `modal/frame_request_retention_job.py:main` | `@read_origin('job:frame_request_retention')` |
| `modal/day3_reengagement_email_job.py:main` | `@read_origin('job:day3_reengagement_email')` |
| `modal/conversation_selfheal_job.py:main` | `@read_origin('job:conversation_selfheal')` |
| `routers/sync.py:sweep_sync_backfill_sequencer` (`/v2/sync-backfill-sequencer/sweep`) | `@read_origin('job:sync_backfill_sequencer')` |
| `routers/dream_sweep.py:canary_dream_agent` (`/v2/dream-agent/canary`) | `@read_origin('job:dream_agent_canary')` |
| `routers/dream_sweep.py:sweep_dream_agent` (`/v2/dream-agent/sweep`) | `@read_origin('job:dream_agent_sweep')` |
| `routers/candidate_integration_sweep.py:sweep_candidate_integrations` (`/v2/candidate-integrations/sweep`) | `@read_origin('job:candidate_integration_sweep')` |
| `routers/feedback_admin.py:generate_yesterdays_feedback_report` (nightly target) | `@read_origin('job:feedback_report_yesterday')` |
| `routers/feedback_admin.py:generate_feedback_report` (scheduled/manual dated backfill) | `@read_origin('job:feedback_report_generate')` |

Cron HTTP routes already receive their route-template origins without these
optional job decorators. `main.py` also launches live-STT refresh,
executor health and proactive dispatch with constant names; those receive
`task:live_stt_fleet_health`, `task:executor_health` and
`task:proactive_message_dispatcher` automatically. S2's new startup queue publisher
receives `task:startup_durable_queue_age_publish` automatically.

The other ASGI entrypoints need the same middleware: add
`from database.firestore_tier_context import FirestoreTierMiddleware`, then
`app.add_middleware(FirestoreTierMiddleware)` in `pusher/main.py` after app
construction, in `desktop_backend.py:_build_app`, and in `llm_gateway/main.py`
after app construction. Without those additions their unscoped reads remain
`unset`; `main.py` already installs the middleware. The Scheduler inventory also
contains `/v1/webhooks/sentry/poll`, whose handler is absent from this checkout;
no verified function exists here to decorate. Finops' scheduled job uses BigQuery,
GCS and provider APIs in a standalone image, so importing the backend origin
module into it is unnecessary. `modal/main.py` is the VAD service, not a Firestore
job.
