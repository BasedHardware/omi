# Shared internal model Gateway

One `gke-l7-rilb` Gateway per environment exposes HTTP port 80 at a reserved
internal `NamedAddress`. Each service chart owns its HTTPRoute, HealthCheckPolicy,
GCPBackendPolicy and additional `<fullname>-gw` ClusterIP Service. The latter
selects the existing pods and has no Ingress NEG or BackendConfig annotations.
GKE manages its standalone NEGs. Existing Services, Ingresses and BackendConfigs
remain unchanged. This separation is required by [GKE's coexistence limitation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/deploying-gateways).

Routes are off in chart defaults and enabled in environment values. Installing
these values does **not** switch a caller. Route prefixes have no trailing slash;
`PathPrefix` matches path elements, so `/diarizer` cannot capture
`/diarizer-batch`. `URLRewrite/ReplacePrefixMatch: /` preserves native paths.
No hostnames are set, allowing IP-literal HTTP and WebSocket requests.

| Route | Native health | Backend timeout | Draining |
| --- | --- | --- | --- |
| `/diarizer-batch` | `/health` | 900s | default 0s |
| `/nllb` | `/health` | 30s | default 0s |
| `/vad` | `/health` | 30s | default 0s |
| `/diarizer` | `/health` | 30s | default 0s |
| `/parakeet` | `/health` | 120s | 130s |

Health checks go directly to pod port 8080, without a route prefix; interval 10s,
timeout 5s. Session affinity remains unset, matching current BackendConfigs.
[Internal ALB WebSockets](https://docs.cloud.google.com/load-balancing/docs/l7-internal)
are supported: active sockets ignore backend timeout, idle sockets obey it.
Parakeet uses `/v3/stream`, `/v1/transcribe` (windows) and `/v2/transcribe`.

LLM gateway is excluded: its verified endpoint is coupled to its own Ingress.
Its chart, callers and deployment gate remain untouched; migration needs a
separate route-aware serving-verification change. Pusher's own listen Ingress,
Deepgram and Grafana are also excluded.

## Lead rollout runbook

These are lead-operated commands, **not** an instruction to run deployments from
a review agent. Run from the reviewed repository commit in bash. Dev first;
repeat in prod only after dev qualification. Do not let a normal service deploy
consume the newly enabled environment values before step 0 finishes. Coordinate
chart upgrades with each service's deployment workflow; do not overlap them.
Every kubectl/Helm invocation below explicitly pins its cluster context.

### 0. Choose environment, enable Gateway API, reserve address, install

Select exactly one environment block. The read-only identities are suitable for
inspection only; the lead uses its approved deployment identity for mutations.

```bash
# Development
ML_ENV=dev
ML_PROJECT=based-hardware-dev
ML_CONTEXT=gke_based-hardware-dev_us-central1_dev-omi-gke
ML_CLUSTER=dev-omi-gke
ML_SUBNET=omi-deepgram-gke-us-central1-dev-vpc-1-subnet-1
ML_NETWORK=omi-dev-vpc-1
ML_RUN_SUBNET=omi-us-central1-dev-vpc-1-subnet-1
# Or production, after development qualification:
# ML_ENV=prod
# ML_PROJECT=based-hardware
# ML_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
# ML_CLUSTER=prod-omi-gke
# ML_SUBNET=omi-deepgram-gke-us-central1-prod-vpc-1-subnet-1
# ML_NETWORK=omi-prod-vpc-1
# ML_RUN_SUBNET=omi-us-central1-prod-vpc-1-subnet-1
ML_REGION=us-central1
ML_NAMESPACE="${ML_ENV}-omi-backend"
ML_GATEWAY="${ML_ENV}-omi-internal-gateway"
ML_ADDRESS="${ML_ENV}-ml-gateway-ilb-ip"
ML_STATE="$(mktemp -d)"
chmod 700 "$ML_STATE"

# Read-only prerequisite inspection (use ro-dev/ro-prod in an inspection shell).
gcloud container clusters describe "$ML_CLUSTER" --project="$ML_PROJECT" \
  --region="$ML_REGION" --format='json(currentMasterVersion,network,subnetwork,gatewayApiConfig)'
gcloud compute networks subnets list --project="$ML_PROJECT" \
  --filter="network:$ML_NETWORK AND region:$ML_REGION" \
  --format='table(name,ipCidrRange,purpose,role)'

# Lead applies these with an approved mutating identity.
gcloud container clusters update "$ML_CLUSTER" --project="$ML_PROJECT" \
  --region="$ML_REGION" --gateway-api=standard
kubectl --context="$ML_CONTEXT" wait --for=create \
  crd/gateways.gateway.networking.k8s.io crd/httproutes.gateway.networking.k8s.io \
  crd/healthcheckpolicies.networking.gke.io crd/gcpbackendpolicies.networking.gke.io --timeout=10m
kubectl --context="$ML_CONTEXT" wait --for=condition=Established \
  crd/gateways.gateway.networking.k8s.io crd/httproutes.gateway.networking.k8s.io \
  crd/healthcheckpolicies.networking.gke.io crd/gcpbackendpolicies.networking.gke.io --timeout=10m
kubectl --context="$ML_CONTEXT" get gatewayclass gke-l7-rilb
# If the named address already exists, describe and verify it instead of recreating it.
gcloud compute addresses create "$ML_ADDRESS" --project="$ML_PROJECT" \
  --region="$ML_REGION" --subnet="$ML_SUBNET" --purpose=SHARED_LOADBALANCER_VIP
helm upgrade --install "$ML_GATEWAY" backend/charts/internal-gateway \
  --kube-context="$ML_CONTEXT" --namespace="$ML_NAMESPACE" \
  -f "backend/charts/internal-gateway/${ML_ENV}_omi_internal_gateway_values.yaml"
ML_IP="$(gcloud compute addresses describe "$ML_ADDRESS" --project="$ML_PROJECT" \
  --region="$ML_REGION" --format='value(address)')"
test -n "$ML_IP"
ML_BASE="http://${ML_IP}"
# Gateway readiness is checked after its first route is installed below.
```

Both clusters were inspected on 2026-10-14: GKE `1.35.8-gke.1380001`, VPC-native,
HTTP load balancing enabled. URL rewrites require GKE >=1.27; policies are supported
on these versions ([policy reference](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/configure-gateway-resources)).
Gateway API was not enabled in the cluster descriptions. Dev kubectl CRD/Ingress
inspection returned a prod-bot identity despite ro-dev selection; do not interpret
that permission failure as absence. The lead checks CRDs after enabling.

Dev frontend subnet: `172.16.48.0/20`; prod: `172.16.160.0/20`. Reserve the VIP in
these ordinary subnets, **not** the proxy-only subnets. Dev proxy subnet is
`pusher-lb-subnet` (`172.16.32.0/20`); prod is `pusher-lb-subnet-prod`
(`172.16.144.0/20`). Cloud Run backend in both environments was confirmed to use
private-ranges-only Direct VPC egress on its corresponding `ML_NETWORK` and
`ML_RUN_SUBNET`. The proxy source range matches today's regional internal
Ingresses. Remaining differences: a new VIP, separate NEGs/backend services and
controller-created health checks/firewall rules. Any destination-VIP-specific
firewall, source tags, NetworkPolicy, or other Cloud Run service's network binding
still needs the probes below; same-VPC placement alone is not a success receipt.

### 1. Install diarizer-batch first and qualify the new route

The separate `diarizer-batch-pool` must already exist in each cluster, with
`service=diarizer-batch`, `env=$ML_ENV`, GPU capacity and
`omi.ai/diarizer-batch=true:NoSchedule`. Its provisioning and HPA metrics readiness
belong to the batch-capacity rollout. This chart must never replace the embedding
release. Dev overlay caps qualification at one GPU; prod retains floor 1/max 18.
Use the batch lane's published, qualified digest (never `latest` or a local build).

```bash
: "${ML_BATCH_DIGEST:?Set the qualified batch image digest sha256:<64 hex characters>}"
kubectl --context="$ML_CONTEXT" get nodes \
  -l "cloud.google.com/gke-nodepool=diarizer-batch-pool,service=diarizer-batch,env=$ML_ENV"
helm upgrade --install "${ML_ENV}-omi-diarizer-batch" backend/charts/diarizer \
  --kube-context="$ML_CONTEXT" --namespace="$ML_NAMESPACE" \
  -f "backend/charts/diarizer/${ML_ENV}_omi_diarizer_values.yaml" \
  -f "backend/charts/diarizer/${ML_ENV}_omi_diarizer_batch_values.yaml" \
  --set-string image.tag= --set-string "image.digest=$ML_BATCH_DIGEST" \
  --wait --timeout=35m
kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" rollout status \
  "deployment/${ML_ENV}-omi-diarizer-batch" --timeout=35m
```

Define verification once; call it after **each** chart installation. Use a
currently served backend image for Python probes, with no customer credentials.
The synthetic batch request is three seconds of PCM silence: it proves routing,
request admission and the v2 response contract, not diarization accuracy.

```bash
ML_PROBE_IMAGE="$(gcloud run services describe backend --project="$ML_PROJECT" \
  --region="$ML_REGION" --format='value(spec.template.spec.containers[0].image)')"
test -n "$ML_PROBE_IMAGE"
ML_PROBE_CODE="$(cat <<'PY'
import json, os, urllib.request
base = os.environ['ML_URL'].rstrip('/')
mode = os.environ['ML_MODE']
if mode == 'batch':
    request = urllib.request.Request(base + '/v2/diarization', data=bytes(3 * 32000), headers={'Content-Type': 'audio/pcm'})
    with urllib.request.urlopen(request, timeout=900) as response:
        assert response.status == 200
        result = json.load(response)
        assert result['provenance']['backend'] == 'pyannote'
        assert all(key in result for key in ('turns', 'overlaps', 'centroids', 'embedding_space'))
    print('batch-v2=200')
else:
    with urllib.request.urlopen(base + '/health', timeout=10) as response:
        assert response.status == 200
    print('health=200')
PY
)"
verify_route() {
  local prefix="$1" mode="${2:-health}" release="${ML_ENV}-omi-$1"
  if [ "$prefix" = nllb ]; then release="${ML_ENV}-omi-nllb-translation"; fi
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" wait \
    --for=condition=Programmed "gateway/$ML_GATEWAY" --timeout=15m
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" get "gateway/$ML_GATEWAY" \
    -o json > "$ML_STATE/gateway.json"
  python3 - "$ML_STATE/gateway.json" "$ML_IP" <<'PY'
import json, sys
gateway = json.load(open(sys.argv[1]))
assert sys.argv[2] in [a['value'] for a in gateway['status']['addresses']]
condition = next(c for c in gateway['status']['conditions'] if c['type'] == 'Programmed')
assert condition['status'] == 'True'
assert condition['observedGeneration'] == gateway['metadata']['generation']
PY
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" get \
    "httproute/${release}-gw" -o json > "$ML_STATE/$prefix-route.json"
  python3 - "$ML_STATE/$prefix-route.json" "$ML_GATEWAY" <<'PY'
import json, sys
route = json.load(open(sys.argv[1]))
parents = [p for p in route.get('status', {}).get('parents', []) if p['parentRef']['name'] == sys.argv[2]]
assert len(parents) == 1
conditions = {c['type']: c for c in parents[0]['conditions']}
for kind in ('Accepted', 'ResolvedRefs'):
    assert conditions[kind]['status'] == 'True', conditions[kind]
    assert conditions[kind]['observedGeneration'] == route['metadata']['generation']
PY
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" get \
    healthcheckpolicy,gcpbackendpolicy "${release}-gw" -o json > "$ML_STATE/$prefix-policies.json"
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" wait --for=condition=Attached \
    "healthcheckpolicy/${release}-gw" "gcpbackendpolicy/${release}-gw" --timeout=15m
  # Inspect policy status before probing; missing/conflicting attachment is a stop.
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" describe \
    healthcheckpolicy,gcpbackendpolicy "${release}-gw"
  local probe="ml-${ML_ENV}-${prefix}-${mode}-$(date +%s)"
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" run "$probe" \
    --image="$ML_PROBE_IMAGE" --restart=Never --rm -i --attach \
    --pod-running-timeout=5m --env="ML_URL=$ML_BASE/$prefix" --env="ML_MODE=$mode" \
    --command -- python -c "$ML_PROBE_CODE"
  gcloud run jobs deploy "$probe" --project="$ML_PROJECT" --region="$ML_REGION" \
    --image="$ML_PROBE_IMAGE" --network="$ML_NETWORK" --subnet="$ML_RUN_SUBNET" \
    --vpc-egress=private-ranges-only --set-env-vars="ML_URL=$ML_BASE/$prefix,ML_MODE=$mode" \
    --command=python --args="^@^-c@$ML_PROBE_CODE" --task-timeout=960s --max-retries=0 --quiet
  # On failure, retain the job for lead diagnosis; never advance to the next service.
  gcloud run jobs execute "$probe" --project="$ML_PROJECT" --region="$ML_REGION" --wait --quiet
  gcloud run jobs delete "$probe" --project="$ML_PROJECT" --region="$ML_REGION" --quiet
}
verify_route diarizer-batch
verify_route diarizer-batch batch
```

### 2. Existing services: nllb → vad → diarizer embeddings → parakeet

Capture the current release revision and all values without printing runtime env.
The install helper keeps the live immutable image and deployed values, enables
only the new route resources, and waits for the workload. Review captured manifests
locally; do not paste env or secrets into logs. The old Ingress remains usable.
If a served tag is mutable or missing, first qualify an immutable image through
its owning workflow; do not reset it to `latest` with a chart-only upgrade.

```bash
install_route() {
  local chart="$1" release="${ML_ENV}-omi-$1" image tag
  helm history "$release" --kube-context="$ML_CONTEXT" -n "$ML_NAMESPACE" -o json \
    > "$ML_STATE/$chart-history.json"
  helm get values "$release" --all --kube-context="$ML_CONTEXT" -n "$ML_NAMESPACE" -o yaml \
    > "$ML_STATE/$chart-values.yaml"
  helm get manifest "$release" --kube-context="$ML_CONTEXT" -n "$ML_NAMESPACE" \
    > "$ML_STATE/$chart-before.yaml"
  image="$(kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" get deployment "$release" \
    -o jsonpath='{.spec.template.spec.containers[0].image}')"
  local image_args=()
  if [[ "$chart" = diarizer && "$image" = *@sha256:* ]]; then
    image_args=(--set-string "image.digest=${image##*@}" --set-string image.tag=)
  else
    [[ "$image" != *@* && "$image" = *:* ]] || return 1
    tag="${image##*:}"
    [[ "$tag" =~ ^[a-f0-9]{7,40}$ ]] || { echo 'Require an immutable commit tag'; return 1; }
    image_args=(--set-string "image.tag=$tag")
  fi
  helm upgrade "$release" "backend/charts/$chart" \
    --kube-context="$ML_CONTEXT" --namespace="$ML_NAMESPACE" \
    -f "backend/charts/$chart/${ML_ENV}_omi_${chart//-/_}_values.yaml" \
    -f "$ML_STATE/$chart-values.yaml" "${image_args[@]}" \
    --set gateway.enabled=true --set-string "gateway.name=$ML_GATEWAY" \
    --wait --timeout=35m
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" rollout status \
    "deployment/$release" --timeout=35m
}
install_route nllb-translation
verify_route nllb
# Lead commits/deploys NLLB caller diff below, then watches ≥30 minutes.
install_route vad
verify_route vad
# Lead commits/deploys VAD caller diff below, then watches ≥30 minutes.
install_route diarizer
verify_route diarizer
# Lead commits/deploys embeddings caller diff below, then watches ≥30 minutes.
install_route parakeet
verify_route parakeet
# Lead additionally qualifies /v3/stream handshake + bidirectional audio,
# /v1/transcribe windows and /v2/transcribe before its caller switch.
# Lead commits/deploys Parakeet caller diff below, then watches ≥30 minutes.
```

Stop between services until error rate, p95, fallbacks and load balancer backend
health have been watched for at least 30 minutes on real switched traffic. NLLB's
current fallback is Gemini (the legacy `google` token resolves to Gemini), not an
assumed independent Google Translate path. Parakeet goes last; it may slip without
blocking the batch cohort. Keep every old Ingress/IP/DNS for at least seven days
after its last caller migrates. Do not remove them in this rollout.

### Caller diffs: separate lead-owned commits, one service at a time

Substitute the verified **environment-specific** `$ML_IP` in the following exact
values. No caller env is modified by this PR. Source of truth for backend/listen/
pusher bindings is `backend/deploy/runtime_env/{dev,prod}.overlay.yaml` and `_base.yaml`;
regenerate `runtime_env.yaml` with
`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`. Update matching
chart env literals in the same commit; they are checked against the manifest.
Run `backend/.venv/bin/python backend/scripts/validate-backend-runtime-env.py`
and the owning workflow checks before deployment.

| Env | Old dev value | Old prod value | New full value (both, respective IP) |
| --- | --- | --- | --- |
| `HOSTED_DIARIZATION_API_URL` | unset | unset | `http://<ip>/diarizer-batch` |
| `HOSTED_TRANSLATION_API_URL` | `http://nllb.omiapi.com` | `http://nllb.omi.me` | `http://<ip>/nllb` |
| `HOSTED_VAD_API_URL` | `http://vad.omiapi.com:80/v1/vad` | `http://vad.omi.me:80/v1/vad` | `http://<ip>/vad/v1/vad` |
| `HOSTED_SPEAKER_EMBEDDING_API_URL` | `http://diarizer.omiapi.com:80` | `http://diarizer.omi.me:80` | `http://<ip>/diarizer` |
| `HOSTED_PARAKEET_API_URL` | `http://parakeet.omiapi.com` | `http://parakeet.omi.me` | `http://<ip>/parakeet` |

Exact source/caller ownership as reviewed on origin/main:

- Batch: binding is currently absent from deployed chart/manifest values. The
  lead's batch feature commit adds `HOSTED_DIARIZATION_API_URL=$ML_BASE/diarizer-batch`
  only to final-pass hosts; pyannote adapter appends `/v2/diarization`. Do not change
  `HOSTED_NEMOTRON_DIARIZATION_API_URL` (the other rollout lane).
- NLLB: backend-listen in each runtime overlay. The httpx client retains `/nllb`
  when posting `/v1/translate`. Deploy through `gcp_backend_listen_helm.yml`.
- VAD: backend-listen env in each `backend/charts/backend-listen/*_values.yaml`
  (not currently owned by runtime_env manifest). The two VAD clients POST the
  complete env URL, so include `/v1/vad`. This also covers speech-profile calls.
  Deploy through `gcp_backend_listen_helm.yml`.
- Embeddings: backend-listen, pusher, Cloud Run `backend`, `backend-sync`,
  `backend-sync-backfill`, `backend-integration` in both runtime overlays. All
  speaker-ID hosts must switch together to satisfy the identical-binding validator.
  Pusher/listen use their owning workflows; Cloud Run uses `gcp_backend.yml`.
  Parakeet's additional fallback binding is declared directly in its chart values:
  dev old `http://dev-omi-diarizer.dev-omi-backend.svc.cluster.local:8080`, prod old
  `http://prod-omi-diarizer.prod-omi-backend.svc.cluster.local:8080`; **both** become
  `http://<ip>/diarizer` in the same embedding switch commit, via `gcp_parakeet.yml`.
  Clients append `/v2/embedding` without dropping the prefix.
- Parakeet: backend-listen and all four Cloud Run services above in both overlays;
  dev pusher in its runtime overlay; prod pusher directly in its chart values
  (the reviewed prod manifest does not own this binding). All become
  `http://<ip>/parakeet`. Backend proxy/prerecorded calls append `/v2/transcribe`,
  window clients append `/v1/transcribe`, streaming converts scheme and appends
  `/v3/stream` without stripping the prefix. Deploy with backend/listen/pusher owners.

### Rollback, per service

First revert that service's lead-owned caller commit and redeploy through the
same owning workflows. Restore **every** old value from the table, including
Parakeet's embedding fallback URLs; for batch remove the new binding and disable
its feature/cohort before removing capacity. Confirm recovery through the old URL.
Then restore the previous Helm revision captured before that route upgrade:

```bash
rollback_route() {
  local chart="$1" release="${ML_ENV}-omi-$1" previous
  previous="$(python3 - "$ML_STATE/$chart-history.json" <<'PY'
import json, sys
print(max(int(r['revision']) for r in json.load(open(sys.argv[1])) if r['status'] == 'deployed'))
PY
)"
  helm rollback "$release" "$previous" --kube-context="$ML_CONTEXT" \
    --namespace="$ML_NAMESPACE" --wait --timeout=35m
  kubectl --context="$ML_CONTEXT" -n "$ML_NAMESPACE" rollout status \
    "deployment/$release" --timeout=35m
}
# Invoke only for the affected, caller-reverted service:
# rollback_route nllb-translation
# rollback_route vad
# rollback_route diarizer
# rollback_route parakeet
# Batch is new: after disabling its callers/cohort, remove only its own release.
# helm uninstall "${ML_ENV}-omi-diarizer-batch" --kube-context="$ML_CONTEXT" -n "$ML_NAMESPACE"
```

If the shared Gateway itself must roll back, first restore all caller URLs and
remove/revert all its routes. Only then uninstall `$ML_GATEWAY` with the explicit
context/namespace. Retain its reserved address for diagnosis/retry. Do not disable
cluster Gateway API, delete the proxy subnet, or delete old Ingress addresses.

## Local contract verification

```bash
backend/.venv/bin/python -m pytest -q backend/tests/unit/test_internal_gateway_helm.py \
  backend/tests/unit/test_diarizer_batch_prereqs.py
make preflight
```

Rendering covers dev/prod, Gateway class/address, routes and rewrites, native
health paths, separate selectors, timeouts/draining, off-by-default behavior,
required configuration errors, batch without Ingress, and unchanged legacy
resource content. Cluster programming and live caller qualification are lead-owned.
