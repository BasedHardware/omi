# omi-onprem — Helm chart (Kubernetes on-prem target)

The Helm mirror of the compose stack (ADR-0049; study
`docs/analysis/kubernetes-onprem-helm-kind-k0s.md`). Same images, same config philosophy — a target
**in addition to** compose, not a replacement. One chart runs on **Kind** (dev/CI) and **k0s** (prod);
only the `values-<env>.yaml` differ.

Milestone status: **core** (backend + valkey + mongo replica-set) plus the **chat** (Qdrant), **objstore**
(RustFS), **push** (ntfy) and **ingress** (Gateway API / Envoy Gateway) profiles are validated live on
Kind. `auth` (Keycloak/OIDC), TLS, and GPU `inference` (k0s) are later phases.

## Prerequisites

`kind`, `kubectl`, `helm` on PATH. The backend image built locally (`omi-onprem-backend:latest`); public
images (mongo/valkey/qdrant/rustfs/ntfy/minio-mc) are pulled by the node.

## Dev on Kind (reproducible)

```bash
cd deploy/onprem/helm

# 1. Cluster — ONLY via the declarative config (never ad-hoc `kind create cluster`)
kind create cluster --config kind-cluster.yaml

# 2. Load the local backend image (no registry; public images the node pulls itself)
kind load docker-image omi-onprem-backend:latest --name omi-dev

# 3. Ingress prerequisite: Envoy Gateway (cluster-level controller + Gateway API CRDs)
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.2.1 \
  -n envoy-gateway-system --create-namespace --wait

# 4. TLS Secret for the Gateway HTTPS listener (only when the auth profile is on). Creates omi-tls.
kubectl create namespace omi-dev --dry-run=client -o yaml | kubectl apply -f -
./gen-certs.sh omi-dev omi-tls localhost

# 5. Install the stack (core + the profiles enabled in values-dev)
helm install omi ./omi-onprem -n omi-dev --create-namespace -f omi-onprem/values-dev.yaml --wait

# 6. Reach it. Auth off -> HTTP + `Bearer dev`; auth on -> HTTPS issuer + a real Keycloak token:
curl http://localhost:8080/v1/health          # {"status":"ok"}
TOK=$(curl -k -s -X POST https://localhost:8443/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k https://localhost:8443/v1/users/people -H "Authorization: Bearer $TOK"
```

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
| `inference` | later phase (GPU on k0s) | — |

## Notes

- **Mongo replica-set**: StatefulSet + PVC + an idempotent init Job (self-contained, §6.1). Init Jobs are
  named per release revision (+ ttl) so `helm upgrade` re-runs a fresh idempotent Job instead of patching
  an immutable one.
- **Ingress**: Gateway API via Envoy Gateway (ADR-0049 Q3). On Kind the Envoy proxy Service is a NodePort
  pinned to 30080 (mapped to host 8080 by `kind-cluster.yaml`); on k0s/bare-metal use MetalLB + a
  LoadBalancer instead.
- **Images**: `kind load docker-image` cannot import Docker's multi-arch/containerd-store images (public
  ones are pulled by the node); a fully air-gapped node needs a pre-seeded local registry.
