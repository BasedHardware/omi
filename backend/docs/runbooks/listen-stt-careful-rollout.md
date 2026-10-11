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

## Comparable recovery gates

Compare simultaneous, pinned-image canary and control **completed sockets** with
`omi_live_session_transcript_outcome_total`: report `no_transcript` over
`transcribed + no_transcript`, plus the `too_short` count. The attempt counter
`omi_live_stt_terminal_total` finishes at first delivered text; its success
cannot reveal later transcription loss. Teardown failures can also be runtime
errors or idle/lifetime completion. Before the canary regression fix, recovery
alone relabels abnormal client disconnects such as 1006 as attempt failures.
Do not interpret that ratio as STT loss.

For active sessions terminated by STT, count
`omi_live_stt_terminal_failures_total` **plus**
`omi_listen_stt_unavailable_total`: the former covers ordinary terminal failures
(including after text), the latter covers the disjoint provider-unavailable or
reconnect-budget close path. Show their counts beside completed sockets,
including short/quiet sockets. Pre-admit reconnect-budget backoff exits before
accepted-STT counting and session-end outcomes; in-runtime unavailable backoff
does emit a session outcome. This sum is not a completed-socket loss fraction.
Neither counter measures how much audio was lost. Failure/backoff label series
are created lazily: first increments can be missed by `increase()`, especially
on short-lived pods. Check series presence and scrape continuity; an absent
series is not a measured zero.
`omi_live_session_terminal_after_text_total` is emitted only with recovery on;
its absent control series is not zero loss. Keep it as a canary zero-loss gate,
not a canary/control rate comparison. No flag-off metrics change is required.

Window first-text seconds start at the window socket's **first** VAD speech.
A fully answered short fragment can cancel its 12s deadline, then later speech
starts a fresh deadline while the histogram retains the earlier clock. A >30s
sample can therefore contain long quiet gaps; it does not establish delayed
recovery. Paid-successor text is not an observation in this histogram. Keep the
window tail as an investigate/HOLD signal with its observation count, and
cross-check window deadline/empty outcomes, POST latency, actual recovery dials,
replay wall time, skipped audio and session outcomes before attributing harm.

Fallback `capacity_full` on `stt_live_session` describes the **source leg**.
Soniox/Modulate sources mean a local paid-adapter or replay delivery bound
(including the wrapper's tail admission cap);
Parakeet admission refusal is `stt_selection` with subtype `admission`.
Provider cooling is a circuit/backoff decision, not that source capacity cause.
This label does not establish why the successor path exhausted: cooling or
admission may still prevent a successor. Cross-check selection and actual dial
counters separately.
`exhausted` can settle an unproven hop at close and is not a session-loss count.

## Monitoring prerequisite (coordinator only)

Before any canary exists, **reconcile production adapter values with live and
review the local render before any Helm upgrade**. The shared adapter covers
listen, Parakeet, pusher, VAD, diarizer, Deepgram and NLLB prod chart metrics.
Incomplete values replace its rule lists and can break another service's HPA.
Production values preserve all 18 live rules and retain
`nllb_active_requests_total`: the 2026-10-04 live NLLB HPA is CPU-only (1 current,
maximum 2 replicas), while checked-in prod NLLB values set `requestsPerPod: 4`
and render an External metric on the next deploy. This is **known repo-versus-live
HPA drift**; do not change the NLLB chart in this adapter PR. A rule with no
matching series is harmless and protects that future deploy. The only allowed
rule differences are the two listen canary selectors and the exact added NLLB
rule. Reconcile any further drift in a reviewed PR first.

The scrape must copy `track` to `listen_track`, and the adapter must exclude
`listen_track="canary"` in **both** listen queries. A listen Helm upgrade does
not install these changes. The existing monitoring workflow installs the scrape
config, also deploys the Cloud Run exporter and provisions alerts; review that
scope separately. It does not deploy the adapter. Before the adapter sequence
below, capture the stack's deployed revision and dispatch the reviewed scrape
change (or follow the monitoring README's pinned stack Helm procedure):

```bash
# David: authorized context, reviewed merged main; record the deployed stack revision.
export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
export MON_NS=prod-omi-monitoring
helm --kube-context "$PROD_CTX" -n "$MON_NS" history prod-omi-kube-prometheus-stack
export STACK_BEFORE=REPLACE_WITH_DEPLOYED_KNOWN_GOOD_STACK_REVISION
gh workflow run gcp_cloud_run_metrics_egress.yml --ref main -f environment=prod
# Identify that exact run and wait: gh run watch RUN_ID --exit-status
```

Use a checkout at the reviewed merged monitoring revision. `helm template` is
local; never substitute a cluster dry-run/apply for it. The comparator normalizes
YAML and rule ordering and allows only the two reviewed differences above.
Deployment arguments and **both** APIService specs must match (omitted service
port defaults to 443). Upgrade comparison also requires Helm ownership; rollback
comparison (`--require-live-config`) requires exact live rules and both specs,
without requiring adoption of live metadata first.

The 2026-10-04 read-only capture found matching Deployment arguments/image and
APIService specs. The render changes the config checksum; live has a historical
restart annotation and Kubernetes defaults. Service differences are assigned
IPs/defaults. ClusterRole `prometheus-adapter-server-resources` and
ClusterRoleBinding `prometheus-adapter-hpa-controller` were **absent live**, so
would be created. All other rendered RBAC content and the ServiceAccount matched.
Recheck both RBAC objects immediately before upgrade: if now present, inspect
ownership and adopt only if unowned. The live custom APIService was manually
created and lacks Helm ownership. **HOLD until David adopts it after inspection**;
`--atomic` cannot adopt it. The same inspection/adoption applies to every other
pre-existing rendered object. Never overwrite a conflicting Helm owner or use a
blanket takeover flag. A passing comparator does not replace review of the full
Deployment, Service and RBAC content in the captures.

David runs the following block in order: **history → capture → baseline and
ownership inspection → adopt → atomic upgrade → post-checks**. `prod-operator`
currently has no GKE writes; use David's authorized human context for adoption,
upgrade and rollback. Agents must not request/use that login for reads. Helm
history reads release secrets unavailable to `ro-prod`. Select the **deployed,
known-good** revision, not simply the latest history row; confirm chart 4.14.2.
Every live object rendered by the chart is captured before mutation into the
local, gitignored directory, including the kube-system RoleBinding and both
APIService objects. Preserve this directory until acceptance and rollback are
complete; it contains the pre-adoption ownership metadata as well as specs.

**The rollback gate blocks unless the selected revision's stored manifest contains
BOTH APIService specs and preserves all live rules and Deployment arguments.**
If either APIService is missing or other live-only edits are absent, do not adopt
or upgrade: establish a reviewed complete baseline first. For emergency recovery
from an incomplete historical/atomic rollback, the alternative below re-applies
the captured live APIService YAML and ConfigMap, then restarts the adapter. That
recovery path does not waive the pre-upgrade gate; `--atomic` alone would restore
an incomplete revision.

```bash
# David only: run from the reviewed merged repository root with authorized GKE writes.
# Execute in bash; stop at every HOLD/review gate. Set ADAPTER_BEFORE after reading history.
set -euo pipefail
export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
export MON_NS=prod-omi-monitoring
source ~/.local/bin/gcp-agent-env.sh human
kprod() { rm -f ~/.kube/gke_gcloud_auth_plugin_cache; kubectl --context "$PROD_CTX" "$@"; }

# 1. History: choose the deployed, known-good adapter revision; verify chart 4.14.2.
helm --kube-context "$PROD_CTX" -n "$MON_NS" history prod-omi-prometheus-adapter
: "${ADAPTER_BEFORE:?Set ADAPTER_BEFORE to the deployed known-good revision shown above}"
umask 077
mkdir -p .local
export ADAPTER_REVIEW_DIR=$(mktemp -d "$PWD/.local/adapter-review.XXXXXX")
git check-ignore "$ADAPTER_REVIEW_DIR/rollback.yaml"
# Persist rollback state so the rollback block works from a fresh shell.
printf 'export ADAPTER_REVIEW_DIR=%q ADAPTER_BEFORE=%q STACK_BEFORE=%q\n' \
  "$ADAPTER_REVIEW_DIR" "$ADAPTER_BEFORE" "${STACK_BEFORE:-}" > .local/adapter-review.env
git check-ignore .local/adapter-review.env
helm --kube-context "$PROD_CTX" -n "$MON_NS" get manifest prod-omi-prometheus-adapter \
  --revision "$ADAPTER_BEFORE" > "$ADAPTER_REVIEW_DIR/rollback.yaml"

# 2. Local render and capture EVERY pre-existing rendered object, before adoption.
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community
helm template prod-omi-prometheus-adapter prometheus-community/prometheus-adapter \
  --version 4.14.2 --namespace "$MON_NS" --api-versions apiregistration.k8s.io/v1 \
  --values backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  > "$ADAPTER_REVIEW_DIR/rendered.yaml"
kprod get -f "$ADAPTER_REVIEW_DIR/rendered.yaml" --ignore-not-found -o yaml > "$ADAPTER_REVIEW_DIR/live-all.yaml"
kprod -n "$MON_NS" get configmap prod-omi-prometheus-adapter -o yaml > "$ADAPTER_REVIEW_DIR/configmap.yaml"
kprod -n "$MON_NS" get deployment prod-omi-prometheus-adapter -o yaml > "$ADAPTER_REVIEW_DIR/deployment.yaml"
kprod get apiservices v1beta1.external.metrics.k8s.io v1beta1.custom.metrics.k8s.io -o yaml > "$ADAPTER_REVIEW_DIR/apiservices.yaml"
# Inspect custom APIService: service must be the adapter in prod-omi-monitoring.
kprod get apiservice v1beta1.custom.metrics.k8s.io -o yaml
# Empty items mean new objects; otherwise inspect for unowned/conflicting owners.
kprod get clusterrole prometheus-adapter-server-resources --ignore-not-found -o yaml
kprod get clusterrolebinding prometheus-adapter-hpa-controller --ignore-not-found -o yaml

# Prepare clean recovery YAML BEFORE checking the stored rollback baseline.
backend/.venv/bin/python - <<'PY'
import copy, os
from pathlib import Path
import yaml
root = Path(os.environ['ADAPTER_REVIEW_DIR'])
objects = yaml.safe_load((root / 'apiservices.yaml').read_text())['items']
objects.append(yaml.safe_load((root / 'configmap.yaml').read_text()))
clean = copy.deepcopy(objects)
for obj in clean:
    obj.pop('status', None)
    for key in ('uid', 'resourceVersion', 'generation', 'creationTimestamp', 'managedFields'):
        obj['metadata'].pop(key, None)
(root / 'restore-apiservices-configmap.yaml').write_text(yaml.safe_dump_all(clean))
PY
# HOLD on failure, including a missing custom OR external APIService in rollback.yaml.
backend/.venv/bin/python backend/scripts/diff_prod_adapter.py --require-live-config \
  --rendered "$ADAPTER_REVIEW_DIR/rollback.yaml" --configmap "$ADAPTER_REVIEW_DIR/configmap.yaml" \
  --deployment "$ADAPTER_REVIEW_DIR/deployment.yaml" --apiservices "$ADAPTER_REVIEW_DIR/apiservices.yaml"
backend/.venv/bin/python -m pytest -q backend/tests/unit/test_monitoring_adapter_hpa_contract.py

# 3. Reject conflicting owners for ALL captured objects; prepare only needed adoptions.
backend/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import yaml
root = Path(os.environ['ADAPTER_REVIEW_DIR'])
objects = yaml.safe_load((root / 'live-all.yaml').read_text())['items']
expected = {'meta.helm.sh/release-name': 'prod-omi-prometheus-adapter',
            'meta.helm.sh/release-namespace': 'prod-omi-monitoring'}
adopt = []
for obj in objects:
    meta = obj['metadata']
    labels, annotations = meta.get('labels', {}), meta.get('annotations', {})
    manager = labels.get('app.kubernetes.io/managed-by')
    if manager not in (None, 'Helm') or any(annotations.get(k) not in (None, v) for k, v in expected.items()):
        raise SystemExit('HOLD: conflicting owner for ' + obj['kind'] + '/' + meta['name'])
    if obj['kind'] == 'APIService':
        service = obj['spec']['service']
        if service['name'] != 'prod-omi-prometheus-adapter' or service['namespace'] != 'prod-omi-monitoring':
            raise SystemExit('HOLD: APIService points at another service')
    if manager != 'Helm' or any(annotations.get(k) != v for k, v in expected.items()):
        ref = {'apiVersion': obj['apiVersion'], 'kind': obj['kind'],
               'metadata': {k: meta[k] for k in ('name', 'namespace') if k in meta}}
        adopt.append(ref)
        print('ADOPT after review:', obj['kind'], ref['metadata'])
(root / 'adopt.yaml').write_text(yaml.safe_dump_all(adopt))
PY
# David: inspect live-all.yaml against rendered.yaml; HOLD on any unexplained drift.
# After approving that object diff, set ADAPTER_OBJECT_DIFF_APPROVED=yes.
# Includes the custom APIService; includes either RBAC object if it now exists unowned.
: "${ADAPTER_OBJECT_DIFF_APPROVED:?HOLD: inspect and approve the complete rendered/live object diff first}"
[ "$ADAPTER_OBJECT_DIFF_APPROVED" = yes ] || { echo "HOLD: object diff not approved"; exit 1; }
if [ -s "$ADAPTER_REVIEW_DIR/adopt.yaml" ]; then
  kprod label -f "$ADAPTER_REVIEW_DIR/adopt.yaml" app.kubernetes.io/managed-by=Helm --overwrite
  kprod annotate -f "$ADAPTER_REVIEW_DIR/adopt.yaml" \
    meta.helm.sh/release-name=prod-omi-prometheus-adapter \
    meta.helm.sh/release-namespace=prod-omi-monitoring --overwrite
fi
# Preserve original captures; re-read ownership into a separate file for the upgrade gate.
kprod get apiservices v1beta1.external.metrics.k8s.io v1beta1.custom.metrics.k8s.io -o yaml > "$ADAPTER_REVIEW_DIR/apiservices-adopted.yaml"
backend/.venv/bin/python backend/scripts/diff_prod_adapter.py \
  --rendered "$ADAPTER_REVIEW_DIR/rendered.yaml" --configmap "$ADAPTER_REVIEW_DIR/configmap.yaml" \
  --deployment "$ADAPTER_REVIEW_DIR/deployment.yaml" --apiservices "$ADAPTER_REVIEW_DIR/apiservices-adopted.yaml"

# 4. Upgrade only after all gates pass. If atomic rollback fails, use recovery below.
helm upgrade prod-omi-prometheus-adapter prometheus-community/prometheus-adapter \
  --version 4.14.2 --namespace "$MON_NS" --kube-context "$PROD_CTX" \
  --values backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  --atomic --wait --timeout 10m

# 5. Post-checks: allow the one-minute relist interval, then require fresh nonempty items.
kprod -n "$MON_NS" get secret prod-omi-kube-prometheus-s-prometheus-scrape-confg \
  -o jsonpath='{.data.additional-scrape-configs\.yaml}' | base64 --decode
kprod -n "$MON_NS" get configmap prod-omi-prometheus-adapter -o yaml
kprod -n "$MON_NS" rollout status deployment/prod-omi-prometheus-adapter --timeout=5m
kprod get apiservices v1beta1.external.metrics.k8s.io v1beta1.custom.metrics.k8s.io
kprod get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/backend_listen_requests_per_pod
kprod get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/backend_listen_active_ws_connections_per_pod
kprod get --raw /apis/external.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/parakeet_gpu_utilization
# Parakeet requests use the custom (Pods) API.
kprod get --raw '/apis/custom.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/pods/*/parakeet_active_requests_total?labelSelector=app.kubernetes.io%2Fname%3Dparakeet%2Capp.kubernetes.io%2Finstance%3Dprod-omi-parakeet'
kprod -n prod-omi-backend describe hpa prod-omi-backend-listen prod-omi-parakeet
```

Require both APIService objects `Available=True`, fresh nonempty metric items,
and `ScalingActive=True` with no `FailedGetExternalMetric` / `FailedGetPodsMetric`
errors on either HPA. Persistent missing metrics mean HOLD and rollback before
canary creation. Verify the scrape relabel and main-only adapter averages; after
canary creation verify zero canary gauge samples match the adapter selector,
including after pod replacement/expansion. No upgrade or post-upgrade acceptance
was performed by this PR's author; production access was read-only.

**Rollback path (run separately, only on failed acceptance).** First remove any
canary and wait for its pods to terminate; never restore the inclusive selector
while canary pods serve. Roll back the adapter to the verified revision. If the
historical rollback omits either APIService or live rules, or atomic/explicit
rollback fails, use the captured live APIService/ConfigMap recovery alternative
below. Re-run the post-checks against the restored baseline. Roll back the stack
only if its scrape change also needs reversal; exporter/alert effects need their
own reviewed recovery and are not covered by these Helm rollbacks.

```bash
# David: run from the same repository root; self-contained for a fresh shell.
set -uo pipefail
export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
export MON_NS=prod-omi-monitoring
source ~/.local/bin/gcp-agent-env.sh human || { echo "HOLD: GCP auth setup failed"; exit 1; }
kprod() { rm -f ~/.kube/gke_gcloud_auth_plugin_cache; kubectl --context "$PROD_CTX" "$@"; }
# No errexit here (a failed helm rollback must fall through to restore), so every
# precondition exits explicitly before any cluster operation.
source .local/adapter-review.env || { echo "HOLD: .local/adapter-review.env missing"; exit 1; }
[ -n "${ADAPTER_BEFORE:-}" ] && [ -n "${ADAPTER_REVIEW_DIR:-}" ] || { echo "HOLD: rollback state incomplete"; exit 1; }
test -s "$ADAPTER_REVIEW_DIR/restore-apiservices-configmap.yaml" || { echo "HOLD: restore YAML missing"; exit 1; }
if [ "${ROLLBACK_STACK:-no}" = yes ] && [ -z "${STACK_BEFORE:-}" ]; then echo "HOLD: set STACK_BEFORE before a stack rollback"; exit 1; fi
# Drain the canary first; every step fails closed so the inclusive selector is
# never restored while canary pods might still serve.
kprod -n prod-omi-backend delete deployment prod-omi-backend-listen-canary \
  --ignore-not-found --wait=true --timeout=5m || { echo "HOLD: canary delete failed"; exit 1; }
CANARY_PODS=$(kprod -n prod-omi-backend get pod -l app.kubernetes.io/name=backend-listen,track=canary -o name) \
  || { echo "HOLD: canary pod query failed"; exit 1; }
if [ -n "$CANARY_PODS" ]; then
  kprod -n prod-omi-backend wait --for=delete pod \
    -l app.kubernetes.io/name=backend-listen,track=canary --timeout=5m \
    || { echo "HOLD: canary pods still present"; exit 1; }
fi
LEFT=$(kprod -n prod-omi-backend get pod -l app.kubernetes.io/name=backend-listen,track=canary -o name) \
  || { echo "HOLD: canary pod re-check failed"; exit 1; }
[ -z "$LEFT" ] || { echo "HOLD: canary pods remain: $LEFT"; exit 1; }
if ! helm rollback prod-omi-prometheus-adapter "$ADAPTER_BEFORE" \
  --namespace "$MON_NS" --kube-context "$PROD_CTX" --wait --timeout 10m; then
  export RESTORE_CAPTURED_LIVE=yes
fi
# Also set RESTORE_CAPTURED_LIVE=yes for a confirmed incomplete historical rollback.
if [ "${RESTORE_CAPTURED_LIVE:-no}" = yes ]; then
  kprod apply -f "$ADAPTER_REVIEW_DIR/restore-apiservices-configmap.yaml" \
    || { echo "FAIL: restore apply failed; adapter state unknown, escalate"; exit 1; }
  kprod -n "$MON_NS" rollout restart deployment/prod-omi-prometheus-adapter \
    || { echo "FAIL: adapter restart failed; escalate"; exit 1; }
  kprod -n "$MON_NS" rollout status deployment/prod-omi-prometheus-adapter --timeout=5m \
    || { echo "FAIL: adapter rollout did not complete; escalate"; exit 1; }
fi
# Re-run both APIService, listen/Parakeet metric API and HPA post-checks above.
# Set ROLLBACK_STACK=yes only if the stack also needs rollback.
if [ "${ROLLBACK_STACK:-no}" = yes ]; then
  helm rollback prod-omi-kube-prometheus-stack "$STACK_BEFORE" \
    --namespace "$MON_NS" --kube-context "$PROD_CTX" --wait --timeout 15m \
    || { echo "FAIL: stack rollback failed; escalate"; exit 1; }
fi
```
