# Firestore read attribution

`database/firestore_document_probe.py` counts billed-equivalent Firestore reads
for every process that imports `database/_client.py`. The patch is on the SDK
classes, so a later `firestore.Client()` in that process is covered. Recording
does no network I/O, adds no Firestore reads, and never raises into the caller.

The coverage numerator is `omi_firestore_billed_reads_total`. Do not add
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

## Coverage PromQL

The stackdriver exporter publishes
`firestore.googleapis.com/document/read_count` as the gauge
`stackdriver_firestore_instance_firestore_googleapis_com_document_read_count`.
The gauge value is the count for a 60-second window. Use `avg()` across
exporter replicas and `avg_over_time(...) / 60` for reads per second. `rate()`
on that gauge is not a read rate.

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

After deploy, each of the three type ratios and the overall ratio should be
**≥ 95%**. A short window while old replicas are still serving will sit below
that. A ratio that stays below 95% after the fleet is on this commit is a
reader this probe does not see, or the index-entry residual below.

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
| llm_gateway | `backend/llm_gateway/main.py` | `openai_compatible` imports `llm_gateway/gateway/jit_budget.py`, which imports `database._client` |
| desktop-backend | `backend/desktop_backend.py` | imports `routers` |
| pusher | `backend/pusher/main.py` | imports `routers.pusher`, which imports `database.users` |
| memory-maintenance-job | `backend/modal/memory_maintenance_job.py` | maintenance cron imports `database._client` |
| daily-memory-sweep-job | `backend/modal/daily_memory_sweep_job.py` | imports `database._client` |
| knowledge-ledger-drain-job | `backend/modal/knowledge_ledger_drain_job.py` | drain module imports `database._client` |
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

Measure these as the residual: billed reads minus `omi_firestore_billed_reads_total`,
after the Python fleet is on this commit. Server SDK traffic is
`module="__unknown__"` in Firestore audit logs, so a module filter does not
name them. Do not turn DATA_READ audit back on for this.

| Reader | Path | What it reads | How to measure |
|---|---|---|---|
| `getOrgConversations`, `searchOrgConversations`, `getOrgActionItems`, `modifyActionItem` | not in this repo | org conversation and action-item documents | residual after the Python probe; function instance count in Cloud Monitoring if the function runtime exports one |
| `acceptInvitation`, `inviteUser`, `declineInvitation`, `manageUser`, `cleanupExpiredInvitations` | not in this repo. `web/admin/lib/services/invitation.ts` calls `inviteUser` | invitation and membership documents | same residual. `inviteUser` is a callable, so its reads are not in the admin page's browser SDK |
| `ext-firestore-typesense-conversations-indexonwrite`, `ext-firestore-typesense-conversations-backfill` | Firebase Typesense extension, not in this repo. Still installed; see `backend/utils/conversations/typesense_index.py` | conversation documents on write and backfill | residual. Uninstall is a separate change |
| admin web client | `web/admin/components/auth-provider.tsx` `getDoc` on `adminData/{uid}` | one admin document per signed-in session | Firebase client SDK, not this process. Count it inside the residual, or with a client-side counter that is not in Prometheus today |
| personas web client | `web/personas-open-source/src/lib/firebase.ts` and the `getDocs` / `getDoc` calls under `web/personas-open-source/src/app/` | `plugins_data` and `users` | same. This tree has no `.onSnapshot(` / `.on_snapshot(` call |

Mobile clients in this repo do not use `cloud_firestore`.
