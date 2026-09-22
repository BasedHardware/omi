# Firestore reads by request-owner tier

`omi_firestore_document_reads_total{collection,outcome,tier}` and
`omi_firestore_query_operations_total{collection,tier}` extend the existing SDK
probe. Collection patterns and counting semantics are unchanged. The separate
call-site histogram `omi_firestore_documents_per_operation` is unchanged.

## Read the answer after deployment

Basic's percentage of **all observed reads**, per collection, over the last day:

```promql
100 * (
  sum by (collection) (
    increase(omi_firestore_document_reads_total{tier="basic"}[24h])
  )
  or on (collection)
  0 * sum by (collection) (
    increase(omi_firestore_document_reads_total{tier!=""}[24h])
  )
)
/
sum by (collection) (
  increase(omi_firestore_document_reads_total{tier!=""}[24h])
)
```

Use identical production scrape selectors on every operand if the Prometheus
data source also contains other environments. The `tier!=""` matcher excludes
pre-deployment series during rollout; wait a full day after all observed replicas
have upgraded. Zero-read collections produce NaN rather than a fabricated share.
Read the unknown share alongside basic's share:

```promql
100 * sum by (collection) (
  increase(omi_firestore_document_reads_total{tier=~"unattributed|other"}[24h])
)
/
sum by (collection) (
  increase(omi_firestore_document_reads_total{tier!=""}[24h])
)
```

Absolute per-tier volume, and the reconciled collection totals:

```promql
sum by (collection, tier) (
  increase(omi_firestore_document_reads_total{tier!=""}[24h])
)

sum by (collection, outcome) (
  increase(omi_firestore_document_reads_total{tier!=""}[24h])
)

sum by (collection, tier) (
  increase(omi_firestore_query_operations_total{tier!=""}[24h])
)
```

Summing tiers recovers the existing counter's collection totals; no shadow
counter or duplicate reads are introduced. Do **not** add RunQuery operations to
document reads: nonempty query results are already counted. Existing limitations
remain: document counts omit empty-query floors, query index-entry billing,
retries and unwrapped SDKs; aggregation accounting is the existing approximation.
This is reconcilable measurement, not an exact billing export. Reconcile the
observed fleet to the **Cloud Firestore Read Ops** SKU under **App Engine**.
Unscraped services and jobs are invisible even though their reads have a bounded
label in-process. Verify scrape coverage before making a company-wide claim.

## Attribution and cost contract

- Closed labels come from the generated plan catalog and its wire aliases:
  `basic`, `plus`, `operator`, `architect`, `unlimited`, `unlimited_v2`, `pro`,
  plus `unattributed` and `other`. Noncatalog values collapse to `other`.
  UIDs stay internal and never enter metric labels or telemetry logs.
- Pure ASGI middleware creates a fresh ContextVar holder for each HTTP request
  and WebSocket. The authenticated access boundary binds its owner. The holder
  survives FastAPI's sync-dependency context copy and the existing
  `run_blocking` / `submit_with_context` copies into `db_executor` workers.
  Closing the response or request revokes all copies; `finally` resets the token
  on success, error and cancellation. Streaming/WS work retains attribution
  while active, subject to projection expiry.
- **Added Firestore reads per request: 0. Added Redis/Stripe calls: 0.** Existing
  `get_user_subscription` / `get_existing_user_subscription` business reads
  opportunistically publish their parsed subscription to a process-local,
  4,096-entry, 60-second projection. Auth only peeks; misses never load. No whole
  user documents, credentials or entitlements are cached by this probe. Cache
  locks use nonblocking acquisition; the per-read path has no lock or I/O.
- This improves on a Redis read-through projection by making the extra read
  cost exactly zero, including outages and cold starts. Existing subscription
  resolution (`utils/subscription.py` and `get_user_valid_subscription`) still
  owns product decisions. Even `provision=False` reads Firestore and can return
  synthetic basic on a miss, so the probe never invokes it to resolve a tier.
- Only stored active basic or paid through its period end is attributed.
  Expired/missing state is `unattributed`, including a nonprovisioning resolver's
  synthesized basic. Successfully provisioned basic can be observed after the
  existing business write. Subscription updates invalidate the projection;
  other processes and out-of-band changes can remain stale for at most 60
  seconds after observation (and never beyond a known paid period end).
- Unauthenticated, cold-process, expired-cache and auth paths without a bound
  owner remain `unattributed`. Cron/sweep/Cloud Tasks start without a request
  owner; observing a user's subscription does not turn a job into that user.
  Post-response background work is also `unattributed`. Work awaited within an
  authenticated request retains the request owner's tier.
- Attribution can be selectively missing: requests that never encounter normal
  subscription resolution may remain unattributed indefinitely. Treat basic's
  measured share as a lower bound with an unknown bucket, not a paid/free split
  extrapolated from the attributed subset. This attributes reads by the tier of
  the request's owner; it does **not** establish that basic users generate
  avoidable load. Cross-user reads inside a request still belong to its owner.

Verification lives in `tests/unit/test_firestore_tier_context.py` (real FastAPI
auth, simultaneous requests, executor copies, cold/fault paths, close and
cancellation, 30 requests with zero additional subscription reads) and
`tests/unit/test_firestore_document_probe.py` (all four SDK paths under multiple
tiers, bounded labels, metrics failures, additive totals).
