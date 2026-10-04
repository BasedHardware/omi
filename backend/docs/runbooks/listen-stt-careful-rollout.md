# Listen recovery: coordinator rollout card (#20391)

**Coordinator runs every cluster/build action. HOLD until Luna has reviewed the
final #20391 diff and its default-off recovery flag. No production action was
performed when writing this card.** Commands run from the repository root.
Keep routing shadow/on0, provider order and allocations unchanged in prod.
The [design/image notes](listen-stt-canary-design.md), [soak instructions](../../../testing/live_stt_soak/README.md)
and [watch queries](listen-stt-canary-queries.promql) are part of this card.

1. **Merge inert code, locate image.** #20391's author must implement and test
   `STT_FAILOVER_RECOVERY_ENABLED=false` as the code/chart/runtime default;
   this is a proposed name, not an existing switch. It must cover controller,
   replay, adapter and rejection changes, not just routing. Approve that diff
   first. Merge through normal PRs, wait for successful main Release Eligibility,
   then use the existing dev build. It deploys dev surfaces; it is not build-only.

   ```bash
   export RELEASE_SHA=<full-merged-eligible-main-sha>
   gh workflow run gcp_backend.yml --ref main -f environment=development \
     -f mode=deploy -f release_sha="$RELEASE_SHA" -f deploy_targets=cloud-run-only
   # Locate this exact run with gh run list, then gh run watch RUN_ID --exit-status.
   export TAG=$(git rev-parse --short=7 "$RELEASE_SHA")
   source ~/.local/bin/gcp-agent-env.sh ro-dev
   export DIGEST=$(gcloud container images describe "gcr.io/based-hardware-dev/backend:$TAG" \
     --project based-hardware-dev --format='value(image_summary.digest)')
   export IMAGE="gcr.io/based-hardware-dev/backend@$DIGEST"
   test -n "$DIGEST"
   ```

   Coordinator must confirm prod node pull permission for this dev image digest
   without granting IAM, and inspect exact image source/flag. If unavailable,
   use an **already built** prod image for the same merged SHA. The prod build
   also promotes Cloud Run, so obtain that separately scoped release approval;
   do not use it as an unapproved image factory. Rollback: stop here; no listen
   mutation. Never bypass eligibility to build a PR head.

2. **Dev soak and rollback drill.** Follow the linked soak README: 16 public-audio
   sessions for 10 minutes in each window→Soniox and window→Modulate arm, fake
   first then paid if credentials/capacity permit. Review terminal failures,
   positive replay coverage, wall time/skips/recovered/exhausted, RSS, paid usage
   and backfill headroom. Missing exposure means HOLD. Delete the isolated dev
   namespace to stop the soak. Record fake versus vendor evidence separately.

3. **Two-pod prod canary.** Set explicit coordinator context from the approved
   cluster inventory; never rely on the default. First complete the
   [monitoring prerequisite](#monitoring-prerequisite-coordinator-only), then
   capture controls, render, review, diff, apply and check ready Service
   endpoints/NEG health and scrapes.

   ```bash
   export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
   export NS=prod-omi-backend
   source ~/.local/bin/gcp-agent-env.sh prod-operator
   kubectl --context "$PROD_CTX" -n "$NS" get deploy prod-omi-backend-listen -o yaml > /tmp/listen-control.yaml
   kubectl --context "$PROD_CTX" -n "$NS" get pods -l app.kubernetes.io/name=backend-listen -o json > /tmp/listen-controls.json
   backend/.venv/bin/python backend/scripts/render_listen_canary.py --environment prod \
     --image "$IMAGE" --replicas 2 --control-deployment /tmp/listen-control.yaml \
     --env STT_FAILOVER_RECOVERY_ENABLED=true > /tmp/listen-canary.yaml
   kubectl --context "$PROD_CTX" -n "$NS" diff -f /tmp/listen-canary.yaml
   # diff exit 1 means differences; any other nonzero status is an error.
   kubectl --context "$PROD_CTX" -n "$NS" apply -f /tmp/listen-canary.yaml
   kubectl --context "$PROD_CTX" -n "$NS" rollout status deployment/prod-omi-backend-listen-canary --timeout=10m
   kubectl --context "$PROD_CTX" -n "$NS" get pods -l track=canary -o wide
   kubectl --context "$PROD_CTX" -n "$NS" get endpointslice -l kubernetes.io/service-name=prod-omi-backend-listen -o yaml
   ```

   Two of 30–60 main pods gives approximately 3–6% of endpoints. LB connections
   are not guaranteed to follow that share: measure accepted sockets by exact
   canary pod names. Save the control digest; verify the reported `a2ab2c5`
   controls actually exist, otherwise HOLD/review the comparable-load baseline.
   Start the clock only after **both** canary pods are ready, NEG-attached and
   scraped **with `listen_track="canary"`**, and the isolation checks in the
   query file pass (no canary sample eligible for the HPA). Otherwise remove
   canary immediately. Compare the external metric with the main-only PromQL
   average; confirm HPA has no metric errors. Refresh exact pod regex after
   replacements; reset the exposure
   window. Rollback at every canary stage is the same draining removal:

   ```bash
   kubectl --context "$PROD_CTX" -n "$NS" delete deployment prod-omi-backend-listen-canary --wait=true --timeout=5m
   ```

4. **15-minute gate.** From #20391 report §8: ≥10 positive-duration replays
   covering both paid families; all new pods scraped; zero paid capacity deaths
   or replay-induced 1011; replay p95 ≤20s with ≥10 observations; no unexplained
   fresh-audio skips; no lifecycle residual sustained 2min. Any-text success
   ≥95% with ≥50 sockets, decline ≤2 percentage points against simultaneous
   controls. Terminal-after-text zero, or individually review every non-replay
   cause. Recovered successor death = investigate/HOLD; replay-induced terminal
   death = ABORT/remove. Missing metrics or exposure = HOLD, never elapsed-time GO.

5. **60-minute gate.** ≥30 positive replays, ≥5 per paid family, ≥100 canary
   sockets; same zero-overflow/replay-terminal/lifecycle gates; fleet
   `omi_live_stt_terminal_failures_total{phase=~"connection|send"}` ≤3/25min
   at comparable load; first-text p95 <30s; window POST p95 <2s; combined
   pressure/overflow ≤1%/10min with ≥20 admissions. Review RSS slope/limit
   headroom, vendor usage, GPU and backfill queues. Fallback `exhausted` is a
   diagnostic, **not the authoritative user-harm count**. For each of the two
   proposed fleet watches in the query file, evaluate every 15s: five consecutive
   true evaluations spanning at least 60s trigger investigate/HOLD (`for: 1m`
   semantics). A false evaluation resets that watch's timer; missing/stale
   telemetry means HOLD. The 5m/25m lookbacks do not establish dwell. This PR
   installs no alert rules; replay-induced terminal death still aborts immediately.

6. **Expand only after attended hour and coordinator approval.** For 25% then
   50% of endpoints (each ≥1h; 50% through peak), use `ceil(p*main_ready/(1-p))`
   fixed canary replicas, capacity-check first, regenerate the manifest with
   `--replicas COUNT`, then apply and repeat gates. Record actual socket share;
   HPA movement changes endpoint share. At 60 main pods, 50% needs 60 extra
   pods: insufficient headroom means HOLD. Rollback: draining removal above.

7. **Full rollout, then removal.** Enable the approved flag through a normal
   config PR in prod chart **and** runtime overlay and regenerate the runtime
   manifest; routine hourly main deploys otherwise overwrite a manual main
   env patch. Coordinator dispatches existing listen workflow with the admitted
   image's short SHA (prod registry image required), observes ≥1h and repeats
   gates, then removes canary with the command above. Keep canary until main
   is ready/scraped. For full-rollout containment, coordinate all release writers,
   revert the flag in those owning config sources and redeploy; if an immediate
   image rollback is needed, use the approved `0ba6edb` containment SHA below
   and remove active canary. It retains the old overflow defect. Pause/resume
   competing release writers by coordinator agreement; no workflow edits here.

   ```bash
   gh workflow run gcp_backend_listen_helm.yml --ref main -f environment=prod \
     -f branch=main -f mode=deploy -f image_tag="$TAG"
   # Emergency containment only after verifying this known tag exists in prod:
   gh workflow run gcp_backend_listen_helm.yml --ref main -f environment=prod \
     -f branch=main -f mode=deploy -f image_tag=0ba6edb
   ```

Deletion retains chart preStop (15s) and termination grace (120s). Existing
sockets remain process-owned; there is no cross-image session transfer. Grace
is bounded, not a promise that every long WebSocket ends naturally. Record
disconnects in the rollback drill; abrupt process death can lose in-memory tail.

## Monitoring prerequisite (coordinator only)

Before any canary exists, **reconcile the production adapter values with live
and review the local render before any Helm upgrade**. The adapter is shared
by listen, Parakeet, pusher, VAD, diarizer and Deepgram HPAs. An incomplete
values file replaces its rule lists and can remove metrics used by another
service. Production values preserve all 18 live rules; NLLB's unused external
rule is excluded (the live NLLB HPA scales on CPU). If live changes again,
reconcile it in a reviewed PR first. Do not add an unreviewed metric or drop a
live rule as part of canary preparation.

The scrape must copy `track` to `listen_track`, and the adapter must exclude
`listen_track="canary"` in **both** listen queries. A listen Helm upgrade does
not install these changes. The existing monitoring workflow can install the
scrape config (a main push deploys development only; prod requires coordinator
dispatch); it also deploys the Cloud Run exporter and provisions live alerts,
so review that scope. It does not deploy the adapter. Alternatively the
coordinator can use the monitoring README's pinned stack Helm procedure.

Use a checkout at the reviewed merged monitoring revision. Run this read-only
preflight from the repository root; keep captures outside Git. Clear the GKE
auth plugin cache before every kubectl call and always use an explicit context.
`helm template` is local; do not substitute a cluster dry-run or apply for it.

```bash
export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
export MON_NS=prod-omi-monitoring
export ADAPTER_VERSION=4.14.2
export ADAPTER_REVIEW_DIR=$(mktemp -d /tmp/omi-adapter-review.XXXXXX)
source ~/.local/bin/gcp-agent-env.sh ro-prod
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n "$MON_NS" get configmap prod-omi-prometheus-adapter -o yaml > "$ADAPTER_REVIEW_DIR/configmap.yaml"
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n "$MON_NS" get deployment prod-omi-prometheus-adapter -o yaml > "$ADAPTER_REVIEW_DIR/deployment.yaml"
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" get apiservices v1beta1.external.metrics.k8s.io v1beta1.custom.metrics.k8s.io -o yaml > "$ADAPTER_REVIEW_DIR/apiservices.yaml"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community
helm template prod-omi-prometheus-adapter prometheus-community/prometheus-adapter \
  --version 4.14.2 --namespace "$MON_NS" \
  --values backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  > "$ADAPTER_REVIEW_DIR/rendered.yaml"
backend/.venv/bin/python backend/scripts/diff_prod_adapter.py \
  --rendered "$ADAPTER_REVIEW_DIR/rendered.yaml" \
  --configmap "$ADAPTER_REVIEW_DIR/configmap.yaml" \
  --deployment "$ADAPTER_REVIEW_DIR/deployment.yaml" \
  --apiservices "$ADAPTER_REVIEW_DIR/apiservices.yaml"
backend/.venv/bin/python -m pytest -q backend/tests/unit/test_monitoring_adapter_hpa_contract.py
```

The comparator normalizes YAML and rule ordering, prints the rule diff, and
fails on any difference beyond the two reviewed listen canary selectors.
Deployment arguments and both APIService specs must also match (the API server
defaults an omitted service port to 443). It also checks the live APIService
Helm ownership metadata and fails closed when adoption would be rejected. A PASS does not review every object:
inspect the remaining rendered resources against read-only live captures,
including RBAC and the full Deployment. HOLD on unexplained drift. The
2026-10-04 reconciliation found matching Deployment arguments/image and
APIService specs; the config checksum changes, live has a historical
`kubectl.kubernetes.io/restartedAt` annotation, and Kubernetes fills default
fields absent from the render. Two rendered custom-metrics RBAC objects were absent live:
ClusterRole `prometheus-adapter-server-resources` (get/list/watch on custom
metrics) and ClusterRoleBinding `prometheus-adapter-hpa-controller` (binds that
role to the HPA controller). The upgrade will create them. All other rendered
RBAC content and the ServiceAccount matched; Service differences were assigned
cluster IPs and Kubernetes defaults. Review these additions before approving
the upgrade and recheck live state immediately beforehand. The live custom
APIService `v1beta1.custom.metrics.k8s.io` was manually created and lacks
`app.kubernetes.io/managed-by: Helm`, `meta.helm.sh/release-name` and
`meta.helm.sh/release-namespace`; its spec matches, but Helm will reject
adoption by this release. **HOLD: the live comparator currently fails on this
ownership drift.** The coordinator must reconcile ownership as a separately
reviewed production action, establish the complete rollback baseline below,
and repeat the capture/comparison before any upgrade. Do not bypass ownership
checks with a blanket takeover flag.

Only after reconciliation is merged, the preflight passes, and the coordinator
approves the reviewed object diff, use an identity authorized for GKE writes.
The `prod-operator` agent tier currently has no GKE write permission. Helm
history reads release secrets, which `ro-prod` cannot list; the authorized
coordinator must inspect history and capture the **deployed**, known-good
revision immediately before the upgrade (do not assume the latest row is
healthy). Fetch that revision's stored manifest and compare it with the live
captures using `--require-live-config`. Live-only edits may be absent from
Helm history: the rollback manifest must preserve all 18 rules, Deployment
arguments and both APIService specs. **If this fails, HOLD the upgrade** until
the coordinator establishes a reviewed rollback baseline; `--atomic` would
otherwise restore an incomplete Helm revision on failure. Confirm the adapter
chart is still 4.14.2; if it changed, repeat the pinned render review.

```bash
# Coordinator identity with Helm release-secret reads and approved GKE writes.
helm --kube-context "$PROD_CTX" -n "$MON_NS" history prod-omi-kube-prometheus-stack
helm --kube-context "$PROD_CTX" -n "$MON_NS" history prod-omi-prometheus-adapter
export STACK_BEFORE=<deployed-stack-revision>
export ADAPTER_BEFORE=<deployed-adapter-revision>
helm --kube-context "$PROD_CTX" -n "$MON_NS" get manifest prod-omi-prometheus-adapter \
  --revision "$ADAPTER_BEFORE" > "$ADAPTER_REVIEW_DIR/rollback.yaml"
backend/.venv/bin/python backend/scripts/diff_prod_adapter.py --require-live-config \
  --rendered "$ADAPTER_REVIEW_DIR/rollback.yaml" \
  --configmap "$ADAPTER_REVIEW_DIR/configmap.yaml" \
  --deployment "$ADAPTER_REVIEW_DIR/deployment.yaml" \
  --apiservices "$ADAPTER_REVIEW_DIR/apiservices.yaml"
# Proceed only if the rollback comparison passes and the object diff is approved.
gh workflow run gcp_cloud_run_metrics_egress.yml --ref main -f environment=prod
# Find the exact main run, then gh run watch RUN_ID --exit-status; proceed only on success.
helm upgrade prod-omi-prometheus-adapter prometheus-community/prometheus-adapter \
  --version 4.14.2 --namespace "$MON_NS" --kube-context "$PROD_CTX" \
  --values backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  --atomic --wait --timeout 10m
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n "$MON_NS" get secret prod-omi-kube-prometheus-s-prometheus-scrape-confg \
  -o jsonpath='{.data.additional-scrape-configs\.yaml}' | base64 --decode
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n "$MON_NS" get configmap prod-omi-prometheus-adapter -o yaml
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n "$MON_NS" rollout status deployment/prod-omi-prometheus-adapter --timeout=5m
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/backend_listen_requests_per_pod
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/backend_listen_active_ws_connections_per_pod
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/parakeet_gpu_utilization
# Parakeet's requests metric uses the custom (Pods) API, not the external API.
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" get --raw '/apis/custom.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/pods/*/parakeet_active_requests_total?labelSelector=app.kubernetes.io%2Fname%3Dparakeet%2Capp.kubernetes.io%2Finstance%3Dprod-omi-parakeet'
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n prod-omi-backend describe hpa prod-omi-backend-listen prod-omi-parakeet
```

Require nonempty metric items and fresh timestamps, plus `ScalingActive=True`
with no `FailedGetExternalMetric` / `FailedGetPodsMetric` errors on either HPA.
Allow the adapter's one-minute relist interval after rollout; persistent missing
metrics mean HOLD and rollback before canary creation.

Use a checkout at the reviewed merged monitoring revision for the adapter values.
Verify the live scrape relabel and adapter rules match this PR; after Prometheus
reload, confirm main scrapes and the external metric remain healthy. Once canary
starts, verify each ready canary's `up` and connection gauge has the canary
label, verify **zero** canary gauge samples match the adapter selector, and
compare its main-only average with the external API value. Recheck on pod
replacement/expansion and after any monitoring change. HOLD/abort on mismatch.
The reconciliation used read-only production config/HPA captures; no upgrade or
post-upgrade metric verification was performed by its author.

Rollback: remove canary and wait for its pods to terminate first, then roll back
the adapter and, if needed, the stack to the captured deployed revisions. Never
restore the inclusive adapter while canary pods still serve. Review exporter and
alert changes from the workflow separately; these Helm rollbacks cover only the
two releases named here.

```bash
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n prod-omi-backend delete deployment prod-omi-backend-listen-canary --wait=true --timeout=5m
rm -f ~/.kube/gke_gcloud_auth_plugin_cache
kubectl --context "$PROD_CTX" -n prod-omi-backend wait --for=delete pod \
  -l app.kubernetes.io/name=backend-listen,track=canary --timeout=5m
helm rollback prod-omi-prometheus-adapter "$ADAPTER_BEFORE" \
  --namespace "$MON_NS" --kube-context "$PROD_CTX" --wait --timeout 10m
helm rollback prod-omi-kube-prometheus-stack "$STACK_BEFORE" \
  --namespace "$MON_NS" --kube-context "$PROD_CTX" --wait --timeout 15m
```
