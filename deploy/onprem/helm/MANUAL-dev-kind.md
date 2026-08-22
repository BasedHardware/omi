# Omi self-hosted — Developer manual (Kind, on your laptop)

Step-by-step to run the whole Omi backend locally in [Kind](https://kind.sigs.k8s.io) (Kubernetes in Docker).
This mirrors the production topology (login, storage, vector/object/push stores, HTTPS entry point) so you
can develop against a realistic cluster on one machine.

**Difference from production:** on Kind the GPU is not reliable, so the **inference (speech-to-text,
diarization, translation) is external** — you point the backend at endpoints you provide, or leave them off.
The in-cluster GPU inference is a production (k0s) feature; see `MANUAL-prod-k0s.md`.

---

## 1. Requirements

**Software (install these first)**
- **Docker** — Kind runs the cluster as containers.
- **kind**:
  ```bash
  curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
  chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
  ```
- **kubectl**:
  ```bash
  curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl && sudo mv kubectl /usr/local/bin/
  ```
- **helm** (v3.16+):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  ```
- **openssl**, **git**, **curl**, **python3**.

**External service you provide (for the chat/RAG path)**
- An OpenAI-compatible **LLM + embeddings** endpoint reachable from the cluster — e.g. Ollama on your host
  (`http://host.docker.internal:11434/v1`) serving a chat model + `bge-m3`. Optional: skip it and leave the
  chat/inference features off.

Get the code:
```bash
git clone <your fork of omi> && cd omi/deploy/onprem/helm
```

---

## 2. Create the cluster

```bash
# Declarative cluster (maps host ports 8080/8443 to the ingress) — do NOT use a bare `kind create cluster`.
kind create cluster --config kind-cluster.yaml
kubectl cluster-info --context kind-omi-dev
```

---

## 3. Build & load the backend image

Kind has no registry — you build the backend image and load it straight into the cluster.
```bash
# Build (from the repo). This tags the image with the release AND with :latest — the dev alias.
docker compose -f ../compose.prod.yaml build backend
kind load docker-image omi-oss-backend:latest --name omi-dev
```
(Public images — MongoDB, Valkey, Qdrant, RustFS, ntfy, Keycloak — are pulled by the cluster automatically.)

---

## 4. Cluster add-ons

The dev values reproduce the production topology, so install the same three add-ons (once):
```bash
# 4a. Envoy Gateway — HTTPS entry point
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.2.1 \
  -n envoy-gateway-system --create-namespace --wait

# 4b. OpenEBS — local storage class "openebs-hostpath"
helm repo add openebs https://openebs.github.io/openebs && helm repo update openebs
helm install openebs openebs/openebs -n openebs --create-namespace --wait \
  --set engines.replicated.mayastor.enabled=false \
  --set engines.local.lvm.enabled=false --set engines.local.zfs.enabled=false

# 4c. MetalLB — LoadBalancer IPs on Kind's docker network, then the pool
helm repo add metallb https://metallb.github.io/metallb && helm repo update metallb
helm install metallb metallb/metallb -n metallb-system --create-namespace --wait
kubectl apply -f metallb-pool.yaml          # already set to Kind's 172.18.255.200 range
```

> **Simpler path** (skip OpenEBS + MetalLB): install with the overrides shown in step 5's note and reach the
> stack on `http://localhost:8080` / `https://localhost:8443` via the Kind port mappings.

---

## 5. TLS certificate + install Omi

The gateway serves HTTPS from a Kubernetes Secret named `omi-tls`. The helper `gen-certs.sh` generates a
**self-signed** certificate — SAN = `localhost` + `127.0.0.1`, plus the `HOST_IP=` you pass — and loads it
into that Secret. Its arguments are `./gen-certs.sh <namespace> <secret-name> <hostname>`; it needs only
`openssl` + `kubectl`, and re-running it just replaces the Secret. Being self-signed, curl and the app show
a trust warning — expected in dev.

The chart carries no realm: copy the one for this environment first (ADR-0082). A Kind cluster is
throwaway, so the **dev** realm — with the `omi-test` client and `testuser` — is the right choice here;
prod is the variant without them (`omi-realm.example.json`), and getting that backwards is BACKLOG L47.

```bash
cp ../keycloak/omi-realm.dev.example.json omi-oss/files/omi-realm.json
```

```bash
# The cluster's entry point. On Kind this is an IP on Kind's OWN docker network (172.18.0.0/16), reachable
# from your machine (the docker host) — NOT your LAN. It is pinned in values-dev.yaml + metallb-pool.yaml,
# so you normally don't change it. (In production, k0s, this would be a real free IP on your LAN instead.)
LBIP=172.18.255.200

# A TLS cert whose SAN carries the entry-point IP
kubectl create namespace omi-dev --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=$LBIP ./gen-certs.sh omi-dev omi-tls localhost

# Install. To wire the external LLM/embeddings, add the two --set lines (optional):
helm install omi ./omi-oss -n omi-dev --create-namespace -f omi-oss/values-dev.yaml --wait \
  --set inference.openai.baseUrl=http://host.docker.internal:11434/v1 \
  --set inference.embeddings.baseUrl=http://host.docker.internal:11434/v1 \
  --set inference.embeddings.model=bge-m3
```

> **Bare-Kind path** (no OpenEBS/MetalLB): add
> `--set storageClassName= --set ingress.service.type=NodePort --set ingress.loadBalancerIP= --set auth.hostname=https://localhost:8443`
> and run `./gen-certs.sh omi-dev omi-tls localhost`. Then use `LBIP=localhost:8443` / `http://localhost:8080` below.

> **Embeddings dimension.** `bge-m3` is 1024-dim and the vector store is already 1024 — nothing to do. A
> different embeddings model needs its dimension too, e.g. `--set chat.vectorDim=768`.

---

## 6. Verify

```bash
LBIP=172.18.255.200

curl -k https://$LBIP/v1/health                                   # {"status":"ok"}

TOK=$(curl -k -s -X POST https://$LBIP/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k -o /dev/null -w 'valid token -> %{http_code}\n' https://$LBIP/v1/users/people -H "Authorization: Bearer $TOK"   # 200
curl -k -o /dev/null -w 'bad   token -> %{http_code}\n' https://$LBIP/v1/users/people -H "Authorization: Bearer nope"   # 401

kubectl -n omi-dev get pods                                       # all Running/Completed
```

---

## Notes

- **What runs where.** In the cluster: the API, MongoDB, Valkey, Qdrant, RustFS, ntfy, Keycloak (+Postgres).
  External on dev: the chat LLM, the embeddings model, and (unlike prod) the speech/translation inference.
- **Change something:** re-run the command with `helm upgrade` instead of `helm install`.
- **Teardown:** `kind delete cluster --name omi-dev` (and `helm uninstall eg -n envoy-gateway-system`).
- **Going to production?** Use `MANUAL-prod-k0s.md` — same chart, real cluster (k0s), and the inference runs
  on the GPU inside the cluster.
