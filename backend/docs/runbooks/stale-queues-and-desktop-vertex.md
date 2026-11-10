# Stale queues and desktop Vertex: read-only investigation, 2026-10-12

## Authorization and reproducible dry-run

No production writes, deployments, user API calls or customer-content reads were
performed. Run from the repository root with the worktree's Python environment:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python backend/scripts/retire_dead_queue_backlog.py --project based-hardware
```

The script uses the read-only gcloud token explicitly, never interactive ADC.
It defaults to dry-run. Counts use Firestore aggregation; bounded scans project
creation time only. The historical table below came from stale_queue_audit.py.
It emits no document paths or user IDs.

Dry-run at 2026-10-12 11:51 UTC (`writes: 0`):

| Queue/state | Total count | Sample count | Sample oldest days | Sample attempts |
|---|---:|---:|---:|---|
| projection repairs / queued | 1,177,555 | 200 | 90.761 | missing: 200 |
| projection repairs / failed, dead_letter | 0 each | 0 | 0 | none |
| candidate integration / pending | 0 | 0 | 0 | none |
| candidate integration / failed | 3,284 | 200 | 57.551 | 1: 198; 2: 2 |
| candidate integration / processing | 1 | 1 | 58.685 | 1: 1 |
| candidate integration / dead_letter | 0 | 0 | 0 | none |
| Chat-first / ready | 375,079 | 200 | 41.342 | attempts stored separately |
| Chat-first / pending_kernel_receipt | 512 | 200 | 58.766 | attempts stored separately |
| Chat-first / dead_letter | 0 | 0 | 0 | none |

All 200 sampled ready Chat-first rows have source `capture_arrival`. Pending
kernel samples are `cold_start_rich` (128) and `cold_start_sparse` (72).
Absence of attempt fields on intent documents does **not** prove zero attempts:
`chat_first_delivery_attempts` owns those fields.

## Consumer evidence and operational repair boundaries

### Projection repairs: retired

The fact-bearing legacy callers were removed by #11447 and #12084; remaining
Dream commits have no fact IDs. The ledger no longer enqueues repairs. Inline
legacy vector writes and current canonical repair are independent of this queue.
Delete the historical backlog with `scripts/retire_dead_queue_backlog.py` after
reviewing its default dry-run. Keep `memories`, `memory_commits`, `memory_items`
and `memory_outbox` untouched. Do not replay the unused repair adapter.

### Candidate integrations: first delivery exists, retries have no scheduler

Acceptance dispatches once. `candidate_service.drain_candidate_integrations`
has only the `/v1/candidates/integrations/drain` route as a production caller;
generated client methods exist but there are no application call sites.
`candidate_integration_outbox` bounds completed failures to five attempts, but
most sampled failures never get the second call. The stale processing row is an
abandoned lease, not an actively executing task.

Human-owned repair plan: schedule a backend-internal dispatcher over metadata
from the collection-group query for `pending`, `failed` and expired `processing`.
For each owning account, resolve its **current** task-workflow generation, then
call `candidate_service.drain_candidate_integrations(uid,
account_generation=current_generation, limit=100)` from the service runtime.
The existing claim/complete transactions enforce the generation and lease.
Do not impersonate a user or call the public drain endpoint with an operator
credential. Wait for submitted integration futures before the job exits; a
fire-and-forget Cloud Run job would recreate abandoned leases. Repeat until
success/suppression/dead-letter, without raising the five-attempt policy.

The script above gives the exact dry-run roster counts (3,285 nonterminal rows),
with no dispatches. A deployment needs the normal reviewed job-image, workload
identity and secret configuration; no `gcloud run jobs execute` or scheduler
creation was performed here.

### Chat-first: retired automatic materialization

#20665 removed the production producers and client polling. Released-client
materialization routes return empty 200 responses without touching the store;
meeting-treatment receipts remain. Delete historical intents only after reviewing
the cleanup dry-run. Leave `messages` and Chat-first sibling collections alone.
The age sampler, stalled alert and scheduled materialization review are retired.
The unused store and historical audit CLI remain for a separate removal change.

### Deployment/scheduling inventory

Read-only Cloud Run inventory in `based-hardware/us-central1` contains nine jobs:
`agent-vm-reconciler`, `boot-probe`, `day3-reengagement-email-job`,
`finops-unit-cost-job`, `llm-gateway-vpc-probe-30033797890-1`, `notifications-job`,
`summary-vector-backfill`, `untitled-repair`, `x-connector-sync-job`.
There is no named queue worker. Cloud Run services include backend,
backend-integration, backend-sync/backfill and desktop-backend. Helm source and
live `prod-omi-backend` deployments have no queue CronJob. Scheduler listing was
**PERMISSION_DENIED** for the read-only SA; absence of an independent scheduler
cannot be asserted. These conclusions rely on the missing application consumers
as well as the deployment inventory, not names alone.

## Prometheus evidence and alert acceptance

Use this read-only proxy, URL-encoding the query:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
kubectl --context gke_based-hardware_us-central1_prod-omi-gke get --raw \
  '/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/query?query=max%20by%28queue%29%28omi_queue_oldest_ready_age_seconds%29'
```

`max by(queue)(omi_queue_oldest_ready_age_seconds)` at 11:41 UTC:
projection repairs 7,841,149 seconds; candidate integrations 5,069,850;
Chat-first 5,076,774; **finalization jobs 234,351 seconds**. The last queue is
another independent blocker for the unchanged six-hour alert.

The sampler now ignores future `available_at` retries and candidate leases less
than 300 seconds old, but keeps expired or missing leases visible. It projects
metadata fields only. This fixes readiness semantics, not the missing consumers.
The bounded identity-ordered sampler remains a lower-bound age sample; it does
not guarantee the globally oldest row beyond its 200-row page.

**Queue alert: do not deploy expecting it to be quiet after this PR.** It can
remain unmodified, but backlog convergence, dormant-client policy and the
finalization backlog need resolution and then the exact committed expression
must be evaluated before enabling it.

## Desktop Vertex: historical rejection, current recovery

Query:

```promql
sum by(outcome,error_class,fallback_reason,provider_rejection) (
  increase(llm_gateway_requests_total{lane_id="omi:auto:desktop-vertex-pro"}[14d])
)
```

At 11:41 UTC, approximate extrapolated counts:

| Outcome / failure | Count |
|---|---:|
| success | 51,410.07 |
| error / provider_invalid_request / other_4xx | 5,839.28 |
| error / provider_429_omi_paid | 15.04 |
| error / provider_5xx_omi_paid | 19.06 |
| error / timeout_before_output | 6.00 |

All observed lane series are non-streaming. The counter previously had no HTTP
status label; grouping it by `status_code` does not produce a status breakdown.
This PR adds `upstream_http_status` to the request counter, using a fixed status
vocabulary; it leaves latency-histogram labels and the alert expression unchanged.
No provider body, request value or error message becomes a label.

Historical terminal logs (859 matching entries in a bounded 1,000-entry
September 28–October 5 query) corroborate `provider_request_rejected/other_4xx`.
They do not retain exact status or Vertex reason. The 141 provider-attempt entries
in that mixed sample are 429/unknown and cannot be correlated to this lane;
do not use them to claim that the 5,839 lane rejections were quota failures.
Recent Vertex rejection diagnostics report other lanes, not Pro.

The exact historical causal parameter is **unproven**. Main already contains
#20424 (October 3: preserve tool-call thought signatures), #20960 (October 8:
reserved Gemini with Luna fallback), #21071 and #21087 (October 9: structured
schema normalization/grammar bounds). Those are plausible contributing fixes;
aggregate historical telemetry cannot apportion their causal effect.

The deployed gateway is `gcr.io/based-hardware/llm-gateway:e9c7915` with Pro route
digest `sha256:924e24988ecf9e89f121b8d778f9a28304131b304156fc3787cda3b10044d5e6`.
The lane model label is its requested anchor; it does not prove Pro was served:
current policy selects the active Flash reservation. Forcing a Pro thinking-budget
change from the anchor label would be an unsupported fix. Google documents Pro's
128-token minimum, but that does not identify this incident's actual served model.

Current windows at 11:47 UTC: seven days = 21,073.05 successes and 6.00 timeouts,
zero invalid-request errors; 24 hours = 44.03 successes, zero errors.
Hourly subqueries using the committed >=20 requests and >0.25 predicates give
39 bad hours / 141 eligible hours (27.7%) over the retained 14-day query window,
not the older 61%. Prometheus retention is configured at ten days, so a `[14d]`
query is not evidence of fourteen complete days.

**Gateway alert: the unchanged expression is compatible with this PR and recent
traffic supports enabling it after a maintainer rechecks all lanes and terminal
config rollout.** No new routing repair is justified by current evidence. Deploy
the diagnostics through the normal gateway GitHub Actions release, then query
`sum by(lane_id,upstream_http_status,provider_rejection,fallback_reason)(increase(llm_gateway_requests_total{outcome!="success"}[1h]))`.
If the historical rejection returns, use correlated allowlisted Vertex attempt
status/field/reason to establish the precise mechanism before modifying routing.
