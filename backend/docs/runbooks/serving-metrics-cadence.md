# Listen/pusher managed metrics cadence

Production GMP exports each application metric through exactly one of two
PodMonitoring resources. The existing job retains 15s collection for privacy,
audio custody/compression guards, record-token guards, freshness timestamps,
WebSocket HPA gauges, and application metrics read by GMP paging rules. Its
`-bulk` companion exports the complement at 120s. Development retains its single
15s scrape. Neither application pods nor the local Prometheus configuration
change. No family, histogram bucket, or application label is removed.

Bulk metrics acquire `job="prod-omi-backend-listen-bulk"` or
`job="prod-omi-pusher-bulk"`. All other labels, including `pod`, `worker_process`,
Firestore `caller`, `collection`, `kind`, `service_name`, and `origin`, survive.
The audited job-pinned managed queries stay on the original job. Ad-hoc GMP
queries for other families must include the `-bulk` job. During cutover,
prefer `max without(job)` when deduplicating a counter across old/new jobs;
wait for an entire query window after old series become stale before comparing
rates. Do not sum both identities across the cutover and call the result traffic.

## 120s bulk follow-up

The November 19 read-only audit reviewed 37 Cloud Monitoring policies, one
Cloud Monitoring dashboard, 269 Grafana rules, 50 Grafana dashboards, and the
source alert and dashboard definitions. Fallback and STT routing rules and
panels use local Prometheus. The four live GMP Firestore rules that query
caller-attributed reads keep their 15s GKE inputs. The backend Cloud Run
sidecars use 60s scrapes. For ad-hoc rate queries on the two GMP bulk jobs, use a window of at
least 8m to include multiple scrapes with room for jitter.

### Release-owner rollout

Confirm both existing bulk endpoints use 60s. Record their live specs and
target counts. From the release owner’s authorized GKE context, change just
the interval on the two bulk resources. The JSON Patch test protects against
overwriting a different live interval.

```bash
set -euo pipefail
CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
for name in prod-omi-backend-listen-bulk prod-omi-pusher-bulk; do
  kubectl --context "$CONTEXT" -n prod-omi-backend patch podmonitoring "$name" \
    --type=json -p='[
      {"op":"test","path":"/spec/endpoints/0/interval","value":"60s"},
      {"op":"replace","path":"/spec/endpoints/0/interval","value":"120s"}
    ]'
done
```

This change requires no pod roll. If only one patch succeeds, read both live
intervals before resuming or rolling back. To restore 60s on a changed endpoint,
swap `60s` and `120s` in the patch. Render subsequent releases with
`--set-string podMonitoring.bulkInterval=60s` for both charts while rollback is
in force. Keep the bulk resources and their job names.

Verify `up == 1` for each target and compare
`count_over_time(up{job=~"prod-omi-(backend-listen|pusher)(-bulk)?"}[30m])` over a
full new-state window. Expected counts per stable target are about 15 for bulk
and 120 for primary. Confirm the local STT alerts and dashboards have data and
the GMP Firestore caller queries still return data at 15s. Compare caller,
origin and other label coverage at comparable traffic.

### Billing readback

On the November 18 transition day, production billing showed 1.324B samples
at $71.48, down from 2.277B and $122.93 on November 16. The export totals across
production and development were $75.08 and $124.96. Pusher had split by the
start of November 18 UTC. Listen joined by 08:00 UTC. Compare complete days on
each cadence after export settles.

Run the per-metric attribution query at the UTC midnight ending each day. Run
it with `attribution_id="__run__"` for the Cloud Run comparison. Use the
cluster dimension once so namespace attribution does not double the count.

```promql
sum by (metric_type) (
  increase(monitoring_googleapis_com:collection_attribution_write_sample_count{
    attribution_dimension="cluster",
    attribution_id="prod-omi-gke",
    metric_type=~"prometheus.googleapis.com/(omi_(fallback_total|stt_cost_routing_(ignored_deaths|settlements)_total|firestore_billed_reads(_by_caller|_by_origin)?_total)/counter|omi_episode_compose_seconds/histogram)"
  }[24h])
)
```

Billed SKU totals come from the billing export. Set `@before_day` and
`@after_day` to the two complete UTC days being compared.

```sql
SELECT DATE(usage_start_time) AS day, usage.pricing_unit AS unit,
  SUM(usage.amount_in_pricing_units) AS billed_samples,
  ROUND(SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)), 2) AS net_usd
FROM `based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256`
WHERE DATE(usage_start_time) IN (@before_day, @after_day)
  AND project.id = 'based-hardware'
  AND service.description = 'Cloud Monitoring'
  AND sku.description = 'Prometheus Samples Ingested'
GROUP BY 1, 2 ORDER BY 1, 2
```

Over the full 60s window ending November 19 at 10:26 UTC, cluster attribution
reported 1.172B samples across GKE and Cloud Run. Of these, 330.65M came from
44 high-volume scalar families seen only on bulk targets in the GKE census.
Halving their cadence projects about 165M fewer samples and $8.93/day in
additional savings at the observed $0.054 per million billed samples. The
model gives about 1.007B samples/day and $54.36/day overall, around $68.57
below November 16 in production. This uses collection attribution as a billing proxy and
excludes histogram and shared families from the projected reduction. Compare
the gathered samples and billing export before claiming savings.

## Initial 60s split

The remaining sections record the original release from one 15s job to two jobs.
Use the 120s follow-up above when the split already serves.

### Consumer audit, 2026-11-17

Audited source: public Omi main `c94d892461bf` plus this change. Literal metric
searches covered `backend/charts`, `backend/deploy`, `backend/docs`,
`backend/scripts`, root `scripts`, `infra` if present, and
`web/admin/grafana`. The workspace's `infra/rollout` and `avo` were also checked.
The [per-metric inventory](../monitoring/2026-11-17-serving-metrics-consumers.csv)
records all literal source references for the 509 observed exposition names on
listen/pusher, including histogram buckets, sums and counts. Export keep-lists
and generated inventory references are recorded as such; their presence alone
is not proof of a query consumer. Blank matches do not authorize dropping a
family: unknown/future families are retained by the complementary filters.

| Consumer | Input and cadence | Disposition |
| --- | --- | --- |
| Live listen HPA | CPU; `backend_listen_requests_per_pod` from LB request counters / deployment replicas over 5m; `backend_listen_active_ws_connections_per_pod` from local `backend-listen-metrics`, 15s | Unchanged. The live adapter points at in-cluster Prometheus, not GMP; relists at 1m, max age 5m. |
| Live pusher HPA | `pusher_active_ws_connections_per_pod` from local `pusher-metrics`, 15s | Unchanged. Both WS gauges additionally remain 15s in GMP. |
| Local alerts, recording rules and dashboards | `alert-rules.json`, split `alerts/*.json`, dashboard JSONs, `core-features/recording-rules.yaml`, all PrometheusRules, adapter configs | Local jobs remain 15s. Fallback, STT routing settlements/decisions/snapshot health, live demand and provider circuit pages keep their original local inputs. |
| GMP paging | Firestore caller folding (`by_caller_total`, caller overflow); read parity; batch reads per audio hour (`completed_audio_seconds_total`) | Application inputs stay on original GMP job at 15s. Native Firestore metrics and Cloud Run-only GMP rules are outside these two resources. |
| Audio compression rollback and acceptance | `docs/runbooks/audio-durable-outbox.md`, job-pinned `omi_audio_*` integrity/custody/codec counters and histograms, 5m/30m windows | Entire `omi_audio_*` prefix remains 15s on existing jobs, including future members. |
| In-cluster guards / shape watcher | `charts/incluster-guards/files/guard.py`, `scripts/parakeet_shape_watch.py`; local `backend-listen-metrics` window admissions, first/post latency, coverage/freshness | Unchanged, including the short freshness checks. |
| STT routing runbook | `live-stt-routing.md`, canary PromQL, resilience dashboards: `omi_fallback_total`, `omi_stt_cost_routing_*` | Named local jobs remain 15s. Additional GMP diagnostic copy is 60s; no label or series combination is removed. |
| Privacy shadow | `privacy-check-shadow.md`: all `privacy_*` counters, cycle histogram and cache-disabled gauge | Entire prefix stays 15s, including all buckets. |
| Firestore cost attribution | Firestore read/spend runbooks and GMP cost queries: caller/collection/kind/service_name, origin, tier, document reads | All labels retained. Caller paging input remains 15s; origin, tier and other diagnostic/cost copies become 60s. No label coalescing. |
| Episode and batch histograms | Episode composer docs, batch-worker runbook, batch HPA chain busy `_sum` and other batch rules | Listen/pusher copies become 60s; every bucket retained. Batch worker PodMonitoring and its short HPA freshness contract are untouched. |
| FinOps and parity tools | `scripts/finops/pull_prometheus.py` uses local daily increases plus Cloud Run-only GMP; `scripts/parity/soak_check.py` uses long-window legacy-sync increases | No collector used by FinOps changes. Long-window managed diagnostic reads retain every family. |

Read-only live inspection used **ro-prod**, no customer/account documents.
The live HPAs, adapter ConfigMap/deployment arguments, Prometheus resource and
Grafana datasource ConfigMap confirm the local source. No managed Rules,
ClusterRules or GlobalRules existed in any namespace. Live Grafana API readback returned 226 rules, with no unknown live UIDs; all
application inputs from its 11 GMP rules are covered at 15s. Two query definitions
differ from main (`omi-pipeline-held-row-age`, `omi-pipeline-projection-drain-stall`);
they do not add a listen/pusher GMP input. Full source/live rule parity is not claimed.
No external/ad-hoc consumer census is possible from Git alone.

Do not make eager counters lazy in this change: fallback initialization explicitly
allows `increase()` to see the first burst. An emitter change would also require
an image rollout on the live audio path and separate review/qualification.

### Sizing and price basis

Measurements: 2026-11-17 04:08Z exposition census, with separate histogram-count
queries at 04:12Z (GMP aliases can collapse `_count` with the `+Inf` bucket in an
`or` union). All queries name metrics explicitly. The original input was
re-measured: GKE attribution was 1.839B samples/day over the latest hour,
2.356B/day six hours earlier; Cloud Run was 0.281B/day. Attribution dimensions
were not added together. Latest 24h GKE ingestion was 1.977B. These are observations,
not a stable post-change baseline.

[Per-family/workload sizing](../monitoring/2026-11-17-serving-metrics-sizing.csv)
uses `count by (__name__, top_level_controller_name)(METRIC{cluster="prod-omi-gke",namespace="prod-omi-backend"})`.
Counters/gauges save `series * (86400/15 - 86400/60) = series * 4320` points/day.
Histograms keep all buckets. Their raw point reduction is an upper bound on billed
samples, because GMP does not bill unchanged cumulative buckets. For the billed
estimate, each histogram family's live collection attribution is allocated by
its current logical `_count` series across workloads, then multiplied by 75%.
This assumes comparable nonempty bucket density across workloads. The separate
hour-attribution model applies that allocation to scalar families too, retaining
recent pod churn rather than projecting only the current count.

| Workload | Observed raw exposition series | Keep at 15s | Move to 60s | Raw points/day before → after | Estimated billed samples/day removed |
| --- | ---: | ---: | ---: | ---: | ---: |
| listen | 244,164 | 21,579 | 222,585 | 1,406.38M → 444.82M | 703.59M |
| pusher | 143,916 | 12,547 | 131,369 | 828.96M → 261.44M | 404.33M |
| total | 388,080 | 34,126 | 353,954 | 2,235.34M → 706.26M | **1,107.92M** |

Series **removed**: zero. Series moved off the 15s GMP scrape: 353,954. Raw points
removed: 1,529.08M/day; do not price that as the billed reduction. The broader
`scrape_samples_post_metric_relabeling` read was 287,195 listen and 160,620 pusher;
that includes exposition/created/scrape details outside this explicit family
census. No savings are credited for that unpriced remainder. The extra bulk
scrape adds about 0.36M generated scrape-health points/day at 50 targets, subtracted from both dollar estimates below and to be verified after apply.

Examples across both workloads: fallback 44,000 series / 190.08M samples/day
removed; ignored deaths 21,600 / 93.31M; settlements 16,200 / 69.98M. Episode
compose has 44,600 raw exposition series: 192.67M fewer raw points but only about
28.37M fewer billed samples/day in the attribution model. Caller attribution and
all privacy series save zero because their cadence stays 15s.

KB billing records in `gcp-cost-efficiency/candidates/journal/2026-11-14-prometheus-settle-check-no-fire-queue-at-cap.md` record $123.15 / 2,281M and
$118.95 / 2,203M settled pairs: `(123.15+118.95)/(2281+2203)` = **$0.053991/M**,
rounded to $0.054/M. This replaces triage's baseline-delta $0.058/M estimate.
The KB search found no list-price entry. Google's
[pricing table](https://cloud.google.com/products/observability/pricing) verifies
**$0.060/M for the first 0–50B/month**, with account-wide tiers thereafter.
The observed net rate is 90% of that first-tier list rate; the exact discount and
marginal monthly tier were not independently established. Google's
[billing explanation](https://docs.cloud.google.com/stackdriver/docs/observability/pricing-optimize-and-monitor)
explains why empty histogram buckets must not be priced as full samples.

The conservative current-count estimate is **$59.8/day**; the latest-hour
attribution model is **$61.2/day**. This targets about $60/day and roughly half
the prior sample bill, but does not prove a hard $60 floor under changing pod
counts. A lower monthly marginal tier would lower the dollars further.
**No saving is claimed until a settled billing day.**

### Release-owner apply and rollback

No deploy/apply/merge was performed by the implementer. The release owner applies
only PodMonitoring. Do **not** run a full listen/pusher Helm upgrade to apply this
change: that can roll pods using unrelated image/private-values drift.

First fetch/review the exact merged source and create a fresh release evidence
directory in the owning record repository. From that public Omi checkout, set
`RECORD` to that absolute directory. The following preparation is read-only on GKE:

```bash
set -euo pipefail
source ~/.local/bin/gcp-agent-env.sh prod-operator
CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
: "${RECORD:?Set an absolute durable release evidence directory}"
kubectl --context "$CONTEXT" -n prod-omi-backend get podmonitoring \
  prod-omi-backend-listen prod-omi-pusher -o json > "$RECORD/before.json"
helm template prod-omi-backend-listen backend/charts/backend-listen \
  -n prod-omi-backend -f backend/charts/backend-listen/prod_omi_backend_listen_values.yaml \
  --set-string image.tag=render-only --set-string podMonitoring.bulkInterval=60s \
  --show-only templates/podmonitoring.yaml > "$RECORD/listen.yaml"
helm template prod-omi-pusher backend/charts/pusher \
  -n prod-omi-backend -f backend/charts/pusher/prod_omi_pusher_values.yaml \
  --set-string image.tag=render-only --set-string podMonitoring.bulkInterval=60s \
  --show-only templates/podmonitoring.yaml > "$RECORD/pusher.yaml"
backend/.venv/bin/python - "$RECORD" <<'PY'
import copy, json, sys
from pathlib import Path
import yaml
p = Path(sys.argv[1])
before = json.loads((p / 'before.json').read_text())['items']
assert {o['metadata']['name'] for o in before} == {'prod-omi-backend-listen', 'prod-omi-pusher'}
rendered = {o['metadata']['name']: o for f in ('listen.yaml', 'pusher.yaml')
            for o in yaml.safe_load_all((p / f).read_text()) if o}
assert len(rendered) == 4 and all(o['kind'] == 'PodMonitoring' for o in rendered.values())
restore, primary, bulk = [], [], []
for live in before:
    name = live['metadata']['name']
    assert live['spec']['endpoints'][0]['interval'] == '15s'
    assert len(live['spec']['endpoints']) == 1
    assert 'metricRelabeling' not in live['spec']['endpoints'][0]
    base = {k: copy.deepcopy(live[k]) for k in ('apiVersion', 'kind', 'spec')}
    # Preserve live selectors, target labels, auth and namespace. In particular,
    # live pusher lacks the fromPod service_name addition already present in main.
    base['metadata'] = {k: copy.deepcopy(v) for k, v in live['metadata'].items()
                        if k in ('name', 'namespace', 'labels', 'annotations')}
    base['metadata'].get('annotations', {}).pop('kubectl.kubernetes.io/last-applied-configuration', None)
    restore.append(copy.deepcopy(base))
    for suffix, dest in (('', primary), ('-bulk', bulk)):
        obj = copy.deepcopy(base)
        desired = rendered[name + suffix]
        assert desired['spec']['selector'] == live['spec']['selector']
        endpoint = copy.deepcopy(desired['spec']['endpoints'][0])
        for key in ('port', 'path', 'authorization'):
            assert endpoint[key] == live['spec']['endpoints'][0][key]
        obj['metadata']['name'] = name + suffix
        obj['spec']['endpoints'] = [endpoint]
        dest.append(obj)
for name, objects in (('rollback', restore), ('bulk', bulk), ('primary', primary)):
    (p / (name + '.json')).write_text(json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': objects}, indent=2) + '\n')
PY
```

Review `primary.json` and `bulk.json`: four PodMonitoring objects only, original
selectors/target labels/auth preserved. Compare application Deployment pod-template
hashes before/after. Confirm local HPA and page inputs are healthy at 15s before
applying. The exact authorized write step is:

```bash
kubectl --context "$CONTEXT" -n prod-omi-backend apply -f "$RECORD/bulk.json" && \
kubectl --context "$CONTEXT" -n prod-omi-backend apply -f "$RECORD/primary.json"
```

Bulk first avoids an ingestion gap; a brief overlap during collector reload can
produce duplicate logical counters under the two job names. Wait through reload
and staleness before acceptance. Collector reload is automatic; no image build,
Deployment update or pod roll is needed. Both `/metrics` endpoints still render
the complete registry before filtering, so the extra 60s scrape raises HTTP
scrape work by 25%. Pre-change p95 scrape elapsed time was 0.362s listen and
1.758s pusher; elapsed time is not CPU usage. Release must watch live-audio CPU,
queue/stall/latency signals as well as successful scrapes before accepting the
tradeoff. No compute saving is included in the estimate.

Acceptance: fresh `up==1` for both original and bulk jobs on every selected pod;
15s sample cadence for privacy/caller/guards and local HPA inputs; 60s cadence for
fallback/routing on bulk; unchanged label sets and no doubled steady-state
application family; no deployment generation/pod-template change. After a full
one-hour new-state window, compare collection attribution by cluster only, then
check a complete settled billing day against sample volume and rate. Refresh live Grafana rule definitions and check any out-of-repo guard before
rollout; the audit is dated evidence, not a standing guarantee.

Rollback restores the exact original two resources, then removes only this
change's two bulk resources:

```bash
kubectl --context "$CONTEXT" -n prod-omi-backend apply -f "$RECORD/rollback.json" && \
kubectl --context "$CONTEXT" -n prod-omi-backend delete podmonitoring \
  prod-omi-backend-listen-bulk prod-omi-pusher-bulk
```

Also revert this PR before the next full Helm deployment, or render production
with `--set-string podMonitoring.bulkInterval=` and remove the companion resources
as above. That restores the single full 15s scrape; it does not roll application
pods. Do not leave a chart override as an unrecorded permanent deployment input.
