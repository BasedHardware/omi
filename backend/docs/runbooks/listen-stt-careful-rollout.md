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

Before any canary exists, deploy the reviewed main monitoring configuration.
The scrape must copy `track` to `listen_track`, and the adapter must exclude
`listen_track="canary"` in **both** listen queries. A listen Helm upgrade does
not install these changes. The existing monitoring workflow can install the
scrape config (a main push deploys development only; prod requires coordinator
dispatch); it also deploys the Cloud Run exporter and provisions live alerts,
so review that scope. It does not deploy the adapter. Alternatively the
coordinator can use the monitoring README's pinned stack Helm procedure.

```bash
export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
export MON_NS=prod-omi-monitoring
source ~/.local/bin/gcp-agent-env.sh prod-operator
# Save the DEPLOYED revision of each release for rollback; inspect history.
helm --kube-context "$PROD_CTX" -n "$MON_NS" history prod-omi-kube-prometheus-stack
helm --kube-context "$PROD_CTX" -n "$MON_NS" history prod-omi-prometheus-adapter
export STACK_BEFORE=<deployed-stack-revision>
export ADAPTER_BEFORE=<deployed-adapter-revision>
export ADAPTER_VERSION=<currently-deployed-prometheus-adapter-chart-version>
gh workflow run gcp_cloud_run_metrics_egress.yml --ref main -f environment=prod
# Find the exact main run, then gh run watch RUN_ID --exit-status; proceed only on success.
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community
helm upgrade prod-omi-prometheus-adapter prometheus-community/prometheus-adapter \
  --version "$ADAPTER_VERSION" --namespace "$MON_NS" --kube-context "$PROD_CTX" \
  --values backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  --atomic --wait --timeout 10m
kubectl --context "$PROD_CTX" -n "$MON_NS" get secret prod-omi-kube-prometheus-s-prometheus-scrape-confg \
  -o jsonpath='{.data.additional-scrape-configs\.yaml}' | base64 --decode
kubectl --context "$PROD_CTX" -n "$MON_NS" get configmap prod-omi-prometheus-adapter -o yaml
kubectl --context "$PROD_CTX" -n "$MON_NS" rollout status deployment/prod-omi-prometheus-adapter --timeout=5m
kubectl --context "$PROD_CTX" get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/backend_listen_active_ws_connections_per_pod
```

Use a checkout at the reviewed merged monitoring revision for the adapter values.
Verify the live scrape relabel and adapter rules match this PR; after Prometheus
reload, confirm main scrapes and the external metric remain healthy. Once canary
starts, verify each ready canary's `up` and connection gauge has the canary
label, verify **zero** canary gauge samples match the adapter selector, and
compare its main-only average with the external API value. Recheck on pod
replacement/expansion and after any monitoring change. HOLD/abort on mismatch.
No production config/metric verification was performed by this PR's author.

Rollback: remove canary and wait for its pods to terminate first, then roll back
the adapter and, if needed, the stack to the captured deployed revisions. Never
restore the inclusive adapter while canary pods still serve. Review exporter and
alert changes from the workflow separately; these Helm rollbacks cover only the
two releases named here.

```bash
kubectl --context "$PROD_CTX" -n prod-omi-backend delete deployment prod-omi-backend-listen-canary --wait=true --timeout=5m
kubectl --context "$PROD_CTX" -n prod-omi-backend wait --for=delete pod \
  -l app.kubernetes.io/name=backend-listen,track=canary --timeout=5m
helm rollback prod-omi-prometheus-adapter "$ADAPTER_BEFORE" \
  --namespace "$MON_NS" --kube-context "$PROD_CTX" --wait --timeout 10m
helm rollback prod-omi-kube-prometheus-stack "$STACK_BEFORE" \
  --namespace "$MON_NS" --kube-context "$PROD_CTX" --wait --timeout 15m
```
