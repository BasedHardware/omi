# Pinecone query accounting

`database.pinecone_partition_index.OwnerIndex.query` meters each provider query
attempt, including provider errors. It consumes the explicit `caller` argument
locally; that argument never reaches Pinecone. Every `vector_db.py` query site
passes its containing function's fixed name, including metadata pagination.

The four process-local counters use the default Prometheus registry:

| Counter | Meaning |
| --- | --- |
| `omi_pinecone_queries_total` | Provider query attempts after owner validation and route resolution |
| `omi_pinecone_read_units_total` | Sum of valid, nonnegative `response.usage.read_units` on successful responses |
| `omi_pinecone_query_missing_usage_total` | Successful responses missing usage or read units; units are never estimated |
| `omi_pinecone_query_metering_errors_total` | Swallowed accounting errors; unlabelled |

The first three counters have only `family`, `route_mode`, and `caller` labels.
`family` is the original shared namespace (`ns1`, `ns2`, `ns3`, `ns4`, `ns_x`,
`ns_tchunks`, `workstream-association-v1`); unknown families map to `other`.
`route_mode` is `legacy` when the actual target equals that original family,
otherwise `partitioned`. A route in `copying` that still reads the shared family
therefore counts as `legacy`. Caller values are closed in
`database/pinecone_query_metrics.py`; unknown callers map to `other`.
No owner, bucket, routed namespace, vector id, or request text is exported.
Children are created only when used, never as a label cross product.

The pinned `pinecone==7.3.0` client was verified against
`memories-backend-dev` on 2026-11-02 using a synthetic-owner-only query with
values and metadata disabled, no matches and no writes. The actual response
was `pinecone.core.openapi.db_data.model.query_response.QueryResponse`, its
`usage` was `pinecone.core.openapi.db_data.model.usage.Usage`, and
`usage.read_units` was the integer `1`. The meter supports both SDK attributes
and mapping responses without converting or traversing matches.

Accounting adds only local counter updates. It performs no network, logging,
retry, background dispatch, or stack inspection. Failure preserves the provider
result or exception. Provider failures count attempts but do not count missing
usage. Invalid usage counts an accounting error and contributes no units. The
pinned SDK declares integer read units, so fractional/float values and booleans
are rejected rather than added to billing totals.

## Query-path audit

All 11 `vector_db.py` query callsites use `OwnerIndex.query`. Serving account
deletion also issues `_query` directly in `verify_empty_all_copies` to inspect
freshness headers; those calls are separately metered with
`caller="account_purge_verify"`, including each retry and each namespace copy.
Mutation admission, routing, freshness checks and provider arguments are unchanged.
The migration transport's queries are operator-only and excluded from this
serving meter. Fetch, list, mutations and their usage are outside this query meter.

## Scrape coverage and release acceptance

Read-only Managed Prometheus aggregates on 2026-11-02 verified existing
application metrics from Cloud Run `backend`, `desktop-backend`, `backend-sync`,
`backend-sync-backfill`, `backend-integration`, and `notifications-job`.
All use the default application registry. The general sidecar admits `omi_.*`;
the sync profile explicitly admits `omi_pinecone_.*` with this change.
The new metric was absent before deployment, as expected.

GKE listen and pusher expose the default registry at authenticated `/metrics`
and have local Prometheus jobs `backend-listen-metrics` and `pusher-metrics`.
They were absent from the GMP scrape aggregate; this PR does not add GMP
collection for them. The GPU batch worker does have a GMP scrape job, but uses
its own registry and does not perform Pinecone queries (no vector DB imports
in the worker implementation). CPU finalization queries run on backend services.

The local Prometheus Cloud Run sync bridge also has a separate explicit
Stackdriver-exporter allowlist which does not import Pinecone counters. Query
GMP directly for Cloud Run workers; changing that bridge is unnecessary for
the query below. GMP results alone are not a complete fleet cost attribution
until the listen/pusher collection gap is resolved or those local series are
analyzed separately.

The rollout lead deploys the backend image and revision-local sync scrape
profile together, plus listen/pusher images when those services need the meter.
After deployment, verify the running release identity, generate or observe a
query, then confirm the new counters appear in GMP for the receiving services.
Watch missing usage and accounting errors before trusting unit totals. This PR
establishes instrumentation, not production ingestion, a cause, or savings.

## Dashboard-free queries (Managed Prometheus)

Largest reported read-unit consumers over the last day, Cloud Run scope:

```promql
topk(10, sum by (caller) (
  increase(omi_pinecone_read_units_total{project_id="based-hardware",cluster="__run__"}[24h])
))
```

To compare query cost before and after partition routing:

```promql
sum by (family, route_mode, caller) (
  rate(omi_pinecone_read_units_total{project_id="based-hardware",cluster="__run__"}[1h])
)
/
sum by (family, route_mode, caller) (
  rate(omi_pinecone_queries_total{project_id="based-hardware",cluster="__run__"}[1h])
)
```

This ratio includes failed queries in the denominator. Inspect
`omi_pinecone_query_missing_usage_total` and
`omi_pinecone_query_metering_errors_total` alongside it; an absent counter is
not proof of zero consumption or complete collection. Units reflect Pinecone's
response usage, rather than a billed-dollar estimate.
