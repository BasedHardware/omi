# omi-oss — Helm chart (Kubernetes on-prem target)

The Helm mirror of the compose stack (ADR-0049; study
`docs/analysis/kubernetes-onprem-helm-kind-k0s.md`). Same images, same config philosophy — a target
**in addition to** compose, not a replacement. One chart runs on **Kind** (dev/CI) and **k0s** (prod);
only the `values-<env>.yaml` differ.

Milestone status: all seven profiles are validated live on Kind — **core** (backend + valkey + mongo
replica-set), **chat** (Qdrant), **objstore** (RustFS), **push** (ntfy), **ingress** (Gateway API / Envoy
Gateway), **auth** (Keycloak OIDC + Gateway TLS) and **inference** (external OpenAI-compatible endpoint).
Validated live on a real **k0s** node too (`values-k0s.yaml`), in phases: **A** core (backend image pulled
from a local registry, OpenEBS storage), **B** ingress + auth (MetalLB LoadBalancer on a real LAN IP, Envoy
Gateway, Keycloak-on-Postgres OIDC/TLS, real-token 200 / invalid-token 401), **C** in-cluster **GPU**
inference (`inference.inCluster`, ADR-0053 — nllb on `nvidia.com/gpu`, real EN→IT translation reached by the
backend at `http://nllb:8080`).

## Prerequisites

`kind`, `kubectl`, `helm`, `openssl` on PATH. The backend image built locally (`omi-oss-backend:latest`);
public images are pulled by the node. `values-dev.yaml` replicates the **prod topology** on Kind (phase B):
so it needs three cluster add-ons — **Envoy Gateway** (ingress), **OpenEBS** (storage class), **MetalLB**
(LoadBalancer). For a bare Kind without them, override to the simple path (see the note after the recipe).

## Dev on Kind (reproducible, prod-topology)

```bash
cd deploy/onprem/helm

# 1. Cluster — ONLY via the declarative config (never ad-hoc `kind create cluster`)
kind create cluster --config kind-cluster.yaml

# 2. Load the local backend image (no registry; public images the node pulls itself)
kind load docker-image omi-oss-backend:latest --name omi-dev

# 3. Cluster add-ons (like the app, installed once):
#    3a. Envoy Gateway — Gateway API controller + CRDs
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.2.1 \
  -n envoy-gateway-system --create-namespace --wait
#    3b. OpenEBS — provides the `openebs-hostpath` storage class
helm repo add openebs https://openebs.github.io/openebs && helm repo update openebs
helm install openebs openebs/openebs -n openebs --create-namespace --wait \
  --set loki.enabled=false --set minio.enabled=false \
  --set engines.replicated.mayastor.enabled=false \
  --set engines.local.lvm.enabled=false --set engines.local.zfs.enabled=false
#    3c. MetalLB — LoadBalancer IPs, then the address pool (from the kind network subnet)
helm repo add metallb https://metallb.github.io/metallb && helm repo update metallb
helm install metallb metallb/metallb -n metallb-system --create-namespace --wait
kubectl apply -f metallb-pool.yaml

# 4. TLS Secret for the Gateway HTTPS listener. SAN must carry the LoadBalancer IP (values-dev pins it):
kubectl create namespace omi-dev --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=172.18.255.200 ./gen-certs.sh omi-dev omi-tls localhost

# 5. Install the stack (all profiles enabled in values-dev)
helm install omi ./omi-oss -n omi-dev --create-namespace -f omi-oss/values-dev.yaml --wait

# 6. Reach it through the LoadBalancer IP (Keycloak issuer + API over HTTPS):
LBIP=172.18.255.200
curl -k https://$LBIP/v1/health                # {"status":"ok"}
TOK=$(curl -k -s -X POST https://$LBIP/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k https://$LBIP/v1/users/people -H "Authorization: Bearer $TOK"
```

**Simple path (bare Kind, no OpenEBS/MetalLB):** `helm install ... -f values-dev.yaml
--set storageClassName= --set ingress.service.type=NodePort --set ingress.loadBalancerIP=
--set auth.hostname=https://localhost:8443 --set auth.keycloak.db=dev-file` — then reach it on
`http://localhost:8080` / `https://localhost:8443` (the kind port-mappings). gen-certs with `localhost`.

Teardown: `kind delete cluster --name omi-dev` (and `helm uninstall eg -n envoy-gateway-system`).

## Prod on k0s (real bare-metal)

Same chart, `values-k0s.yaml` (the concrete counterpart to the generic `values-prod.yaml`). Differences
from Kind: the backend image is pulled from a **local registry** (there is no `kind load`), the MetalLB pool
is a **free LAN IP** the operator owns (`metallb-pool-k0s.yaml`), and phase C runs **in-cluster GPU**
inference (needs the NVIDIA device plugin on the node).

```bash
# 0. Registry the node can pull from (containerd hosts.toml -> your registry, skip_verify), then push:
docker tag omi-oss-backend:latest <registry>/omi-oss-backend:latest && docker push <registry>/omi-oss-backend:latest
docker tag omi-oss-nllb:latest    <registry>/omi-oss-nllb:latest    && docker push <registry>/omi-oss-nllb:latest   # phase C

# 1. Add-ons: Envoy Gateway + OpenEBS as on Kind; MetalLB with the LAN pool:
kubectl apply -f metallb-pool-k0s.yaml           # edit the address to a FREE IP on your LAN first
kubectl create namespace omi --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=<lan-ip> ./gen-certs.sh omi omi-tls <lan-ip>

# 2. Install (edit values-k0s.yaml: registry host, loadBalancerIP, auth.hostname, modelsHostPath):
helm install omi ./omi-oss -n omi -f omi-oss/values-k0s.yaml \
  --set backend.encryptionSecret="$(openssl rand -hex 32)"   # never store the secret in the values file

# 3. Verify (LAN IP): health, OIDC 200/401, and the in-cluster GPU translation:
LBIP=<lan-ip>
curl -k https://$LBIP/v1/health
TOK=$(curl -k -s -X POST https://$LBIP/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k -o /dev/null -w '%{http_code}\n' https://$LBIP/v1/users/people -H "Authorization: Bearer $TOK"   # 200
```

Add a GPU inference engine (whisper/diarizer/parakeet) by pushing its image and adding one entry under
`inference.inCluster.services` (same shape as `nllb`) — no new template. On a single-GPU node enable only
what fits at once. Teardown: `helm uninstall omi -n omi`.

## Profiles (compose parity)

`core` is always on. Toggle the rest in `values-<env>.yaml`:

| Value | Brings up | Backend wiring |
|---|---|---|
| `chat.enabled` | Qdrant vector store | `VECTOR_STORE_BACKEND=qdrant` |
| `objstore.enabled` | RustFS S3 + bucket-init | `OBJECT_STORE_BACKEND=s3` |
| `push.enabled` | ntfy UnifiedPush | `PUSH_NOTIFICATION_BACKEND=unifiedpush` |
| `ingress.enabled` | Gateway API edge (Envoy) | GatewayClass/Gateway/HTTPRoute → backend |
| `auth.enabled` | Keycloak OIDC + Gateway HTTPS (TLS from `omi-tls` Secret) | `AUTH_BACKEND=oidc`, `OIDC_ISSUER`/`OIDC_JWKS_URL` |
| `inference.enabled` | nothing in-cluster — wires an **external** OpenAI-compatible endpoint | `OPENAI_BASE_URL`, `OMI_EMBEDDINGS_BASE_URL`/`MODEL` (keys in Secret) |

`inference` runs no GPU pods (ADR-0035): set `inference.openai.baseUrl` / `inference.embeddings.baseUrl` to
the operator's OpenAI/vLLM/Ollama endpoint (outside the cluster). GPU services stay on k0s in prod.

## Notes

- **Mongo replica-set**: StatefulSet + PVC + an idempotent init Job (self-contained, §6.1). Init Jobs are
  named per release revision (+ ttl) so `helm upgrade` re-runs a fresh idempotent Job instead of patching
  an immutable one.
- **Ingress**: Gateway API via Envoy Gateway (ADR-0049 Q3). On Kind the Envoy proxy Service is a NodePort
  pinned to 30080 (mapped to host 8080 by `kind-cluster.yaml`); on k0s/bare-metal use MetalLB + a
  LoadBalancer instead.
- **Images**: `kind load docker-image` cannot import Docker's multi-arch/containerd-store images (public
  ones are pulled by the node); a fully air-gapped node needs a pre-seeded local registry.
- **Storage**: the chart is **provisioner-agnostic** — every PVC declares only `storageClassName` +
  a size, nothing provisioner-specific. On dev/Kind we inherit the cluster default (`standard` =
  `rancher.io/local-path`; single-node, `reclaim=Delete`, gone with the cluster). For a real cluster
  install the storage provisioner as a prerequisite (like Envoy Gateway) and set `storageClassName`.
  Reference example: **OpenEBS** on both Kind and k0s (e.g. `openebs-hostpath` for local PV, or a
  replicated OpenEBS class for HA).
