# omi-oss — Helm chart (Kubernetes on-prem target)

The Helm mirror of the compose stack (ADR-0049; study
`docs/analysis/kubernetes-onprem-helm-kind-k0s.md`). Same images, same config philosophy — a target
**in addition to** compose, not a replacement. One chart runs on **Kind** (dev/CI) and **k0s** (prod);
only the `values-<env>.yaml` differ.

Milestone status: all seven profiles are validated live on Kind — **core** (backend + valkey + mongo
replica-set), **chat** (Qdrant), **objstore** (RustFS), **push** (ntfy), **ingress** (Gateway API / Envoy
Gateway), **auth** (Keycloak OIDC + Gateway TLS) and **inference** (external OpenAI-compatible endpoint).
Prod/k0s hardening (MetalLB, real-SAN TLS, Keycloak on Postgres, a GPU inference node) is future work.

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
