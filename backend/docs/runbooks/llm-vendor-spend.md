# LLM vendor spend: estimate, reconcile, then count savings

Gateway Prometheus counters describe reported usage and configured rate-card
estimates. They are not vendor invoices. Never sum estimated savings across
model/routing changes without checking that cost did not move to another vendor.
Dream's prepaid Vertex PT is outside this optimization scope.

## Per-lane daily table

`llm_gateway_accounted_attempts_total`, `llm_gateway_accounted_tokens_total`
and `llm_gateway_estimated_cost_micro_usd_total` observe **newly persisted**
accounting events. These counters run after responses, alongside existing
accounting delivery telemetry. They include short/non-cache-eligible requests,
retries, and failed provider attempts when usage was reported. Duplicate writes
never count again. Missing/unpriced usage is a coverage gap, not free work. For token events, raw
provider completeness must also be true: permissive legacy normalization may
mark partial usage confirmed while filling absent fields with zero. Those
events are indeterminate in these counters and publish neither token classes
nor estimated dollars. This stricter observation does not change stored ledger
pricing or the provider response.
`payer` separates Omi from BYOK; the dollar counter includes only estimated Omi
cost. Returned `traffic_type` distinguishes Flex from Standard/unknown. A lane's
name or a requested service tier does not prove the vendor served that tier.

Use the in-cluster Prometheus proxy (the subscription run's `ops/pq.sh`). That
helper displays only its first 20 result rows: split queries or retain the full
proxy JSON for an all-lane report. Anchor each 24h increase at the next UTC
midnight for a calendar day. Do not sum counters across the in-cluster and GMP
surfaces unless their populations are proven disjoint.

```promql
sum by (lane_id,api_surface,provider,model,traffic_type,token_type) (
  increase(llm_gateway_accounted_tokens_total{payer="omi"}[24h])
)
sum by (lane_id,api_surface,provider,model,traffic_type,rate_card_id) (
  increase(llm_gateway_estimated_cost_micro_usd_total{payer="omi"}[24h])
) / 1e6
sum by (lane_id,api_surface,provider,model,usage_status,cost_status) (
  increase(llm_gateway_accounted_attempts_total{payer="omi"}[24h])
)
sum by (provider,payer,delivery,usage_status,cost_status) (
  increase(llm_gateway_accounting_events_total[24h])
)
```

`token_type=output` is **billable** output: OpenAI completion tokens already
include reasoning; providers reporting reasoning separately add it once.
`reasoning` is an overlapping diagnostic subset, so never add it to `output`.
Likewise `prompt`, `cached_input`, `uncached_input`, `cache_write` and
`tool_use_prompt` are the accounting event's reported classes, not an additive
list. Use `cached_input / prompt` only where that provider reports compatible
fields. A known output count may include tool arguments and hidden reasoning;
response character buckets cannot substitute for tokens.

The existing `llm_gateway_cache_*` token counters cover cache-eligible attempts
only. They cannot establish full lane cost, and their eligible cached share
cannot be presented as the whole lane's cache hit rate.

The new counters require `LLM_GATEWAY_ACCOUNTING_ENABLED` (existing switch);
disabling it stops new observations and ledger persistence. Delivery failed or
dropped events are outside these totals, as is accounting-disabled traffic.
Measure those gaps with the delivery counter and compare attempt volumes with
cache-attempt/request counters. Missing usage on a delivered event remains
visible by usage/cost status. Counters begin only after the gateway release:
there is no historical backfill, and a new series needs a prior scrape before
`increase` can measure its first event. Wait a full day after rollout before
using a daily delta. Backend-only deployment does not update the gateway.

No new response work, model, prompt, route, account document, or production
configuration is introduced. Roll back the gateway image to remove this
telemetry; the existing accounting switch is a broader emergency stop. Series
are lazy, with gateway-configured lane/model identities or rate-card models
(unknown values collapse to `unknown`), finite API-surface/provider/payer/tier/
token classes and rate-card IDs; there are no user, request, transcript, or response
labels. No provider content is logged by this change. Legacy image generation does not
have a routed lane; its dollars retain `lane_id="unknown"` and are separately
attributable by `api_surface="openai_images_generations"`. Unrecognized image
model request strings collapse to the same `model="unknown"` value. This keeps
image spend visible without inventing a gateway lane or leaking request values.

## Batch eligibility and discount accounting

OpenAI's [Batch guide](https://developers.openai.com/api/docs/guides/batch)
documents a 50% discount and up to 24h completion. Its
[Flex guide](https://developers.openai.com/api/docs/guides/flex-processing)
prices Flex at Batch rates. Batch is not an additional 50% reduction on Flex.
Hold model, full request body, response schema and output validation constant
when evaluating a transport-only move. Cache mix/write charges and expiration,
retry/fallback work can change net economics; verify the actual bill.

Existing scheduled memory/X extraction has a durable Flex path in
`utils/memory/promotion_flex.py`; `utils/memory/required_intake.py` also binds
Flex. Capability code does not prove live control state. Inspect aggregate
served tiers and cost before treating the Standard population as addressable.
Do not touch the shared control document as a measurement step.

A synchronous worker is not automatically Batch-eligible. Notes, L1 capture
finalization, interactive chat, retrieval, and embedding-dependent operations
must retain their required freshness and live p95. Before implementing a new
Batch adapter, identify a truly offline producer and prove its existing durable
receipt/lease can survive 24h. Preserve owner isolation, immutable effective
input identity, source revisions, schema validation, cancellation, expiry and
partial-failure replay. Never retry unresolved Batch items on Standard while
the first submission can still complete. Revalidate revisions before committing
results. Do not upload production content or launch jobs during investigation.

For work already on Flex, incremental Batch discount is $0. For new Standard
work, estimate the net discount only from the measured eligible population; do
not apply 50% to the entire OpenAI bill. Dream remains excluded, and model
substitutions or semantic prompt changes require a per-lane parity eval first.

## Billing readback

Read aggregates with the `ro-prod` tier. OpenAI organization Costs/Usage require
appropriate vendor admin access; do not use an inference key or production
Secret Manager payload to bypass that requirement. The FinOps reconciliation
table records `invoice_source=openai_admin_api`, while `llm_openai_measured`
contains only allocated measured spend. Add the reconciled OpenAI residual
before comparing with vendor totals. Never add cohort and plan partitions of
`unit_cost_daily`: they are alternate allocations of the same cost.

Compare 10-24/25 baseline with a complete D+1 vendor day and the GCP export
`based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256`.
External OpenAI cash does not appear in that export; retain vendor costs as its
billing proof and check GCP for offsetting costs. For Vertex embeddings compare
net cost of `Large Text Embedding Model - Predictions`. Verify export freshness;
partial dates and lagging vendor tables cannot confirm realized savings.
