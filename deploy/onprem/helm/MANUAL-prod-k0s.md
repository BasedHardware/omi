# Omi self-hosted — Production manual (k0s, on a GPU server)

Step-by-step to run the whole Omi backend on your own hardware, on a real single-node Kubernetes cluster
(k0s). **Speech-to-text, speaker diarization and translation run on the GPU inside the cluster** — only the
chat LLM and the embeddings model are external (any OpenAI-compatible server you run). Nothing else leaves
your machines.

Everything below was executed and verified on Ubuntu 24.04 with an NVIDIA RTX 5060 Ti (16 GB).

---

## 1. Requirements

**Hardware**
- A Linux server (the "node"). Tested on Ubuntu 24.04.
- An NVIDIA GPU with **≥ 16 GB** VRAM (the default STT + diarization + translation share one card via GPU
  time-slicing). More VRAM / more GPUs = more headroom.
- ~60 GB free disk (container images + model weights).

**Software on the node (install these first)**
- **NVIDIA driver** — `nvidia-smi` must print your GPU.
- **NVIDIA Container Toolkit** — `sudo apt-get install -y nvidia-container-toolkit` (provides
  `nvidia-ctk` and `nvidia-container-runtime`).
- **Docker** — to build the Omi images and run a local image registry.
- **kubectl**, **helm** (v3.16+), **openssl**, **git**, **curl**.

**External service you provide**
- An **OpenAI-compatible LLM + embeddings endpoint** reachable from the node — e.g. [Ollama](https://ollama.com)
  serving a chat model and an embeddings model (`bge-m3`). Note its URL.

**A Hugging Face account + token** — one of the diarization models (`pyannote`) is license-gated, so
provisioning it (step 5) needs a free token whose account has accepted the model terms.

Get the code:
```bash
git clone <your fork of omi> && cd omi/deploy/onprem/helm
```

---

## 2. Two addresses you will use (important — they are different machines)

This deployment uses **two IP addresses on your LAN**. Keep them straight:

| In this manual | What it is | How to choose it |
|---|---|---|
| **`NODE_IP`** = `192.168.100.122` | **The server's own IP** — where k0s, Docker and the image registry run, and where the node reaches your external LLM. | Your machine's real LAN address. Find it: `ip -4 addr` or `hostname -I`. |
| **`ENTRY_IP`** = `192.168.100.190` | **The cluster's entry point** — a *second, separate, currently-unused* IP on the **same** LAN. MetalLB "borrows" it and answers for it, so users/apps reach Omi (HTTPS + the login page) here. The OIDC issuer and the TLS certificate are pinned to it. | Any **free** address on your LAN subnet — NOT the node's own IP, and not used by any other device or handed out by your DHCP server. Verify it's free: `ping -c1 <ENTRY_IP>` must get **no** reply. |

Why two: the node already has its own IP for host things (registry, SSH, the LLM). The cluster needs its own
stable "service" IP that is independent of any single pod — that's what MetalLB provides on `ENTRY_IP`.

Set them once for the shell you'll work in (replace with your real values):
```bash
export NODE_IP=192.168.100.122
export ENTRY_IP=192.168.100.190
export REG=$NODE_IP:5000                       # the registry runs on the node, port 5000
export LLM=http://$NODE_IP:11434/v1            # your external LLM/embeddings (example: Ollama on the node)
```

---

## 3. Install k0s (single node)

```bash
curl -sSLf https://get.k0s.sh | sudo sh          # install the k0s binary
sudo k0s install controller --single             # one machine = controller + worker
sudo k0s start
sudo k0s status                                  # wait for "Kube-api ... Running"

# kubeconfig for kubectl/helm (repeat the export in every new shell, or add it to your ~/.bashrc)
sudo k0s kubeconfig admin > ~/.kube/k0s.conf
export KUBECONFIG=~/.kube/k0s.conf
kubectl get nodes                                # your node should be Ready
```

---

## 4. Give k0s access to the GPU

k0s runs its own containerd, so the GPU is wired at the containerd level, then a device plugin advertises
the GPU to Kubernetes. On one GPU we also turn on **time-slicing** so several inference pods can share it.

```bash
# 4a. Describe the GPU to the container runtime
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# 4b. Make the NVIDIA runtime the containerd default + enable CDI
sudo mkdir -p /etc/k0s/containerd.d
sudo tee /etc/k0s/containerd.d/nvidia.toml >/dev/null <<'EOF'
version = 3
[plugins]
  [plugins."io.containerd.cri.v1.runtime"]
    enable_cdi = true
    cdi_spec_dirs = ["/etc/cdi", "/var/run/cdi"]
    [plugins."io.containerd.cri.v1.runtime".containerd]
      default_runtime_name = "nvidia"
      [plugins."io.containerd.cri.v1.runtime".containerd.runtimes.nvidia]
        runtime_type = "io.containerd.runc.v2"
        [plugins."io.containerd.cri.v1.runtime".containerd.runtimes.nvidia.options]
          BinaryName = "/usr/bin/nvidia-container-runtime"
          SystemdCgroup = true
EOF
sudo k0s stop && sudo k0s start                  # reload k0s with the drop-in

# 4c. Device plugin WITH time-slicing (advertises 4 shareable GPU units — tune in the file's comments)
kubectl apply -f nvidia-device-plugin-k0s.yaml
kubectl -n kube-system rollout status ds/nvidia-device-plugin-daemonset
kubectl get node -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}{"\n"}'   # -> 4
```

---

## 5. Build the images, publish them, and provide the model weights

### 5a. Build the Omi images

Omi ships **five** images we build ourselves: the API (`backend`) and the four inference servers
(`whisper`, `parakeet`, `diarizer`, `nllb`). Everything else — MongoDB, Valkey, Qdrant, RustFS, ntfy,
Keycloak — are public images the cluster pulls on its own; you do **not** build those.

Build all five from the compose files (needs internet for the base images; can take a while):

```bash
cd ..                                            # deploy/onprem
docker compose -f compose.prod.yaml --profile inference build
cd helm
docker images | grep omi-oss                     # you should see the 5 omi-oss-* images
```

### 5b. Publish the images to a local registry (so k0s can pull them)

The images now live in **Docker** on the node — but **k0s uses its own container store (containerd)** and
cannot see Docker's images. The bridge is a small **image registry** running on the node: you push the images
into it, and you tell k0s's containerd it may pull from it.

```bash
# 1. Run a registry on the node (port 5000)
docker run -d --name omi-registry --restart=unless-stopped -p 0.0.0.0:5000:5000 \
  -v omi-registry-data:/var/lib/registry registry:2

# 2. Tag each of the 5 images for the registry and push them
for img in backend whisper parakeet diarizer nllb; do
  docker tag  omi-oss-$img:latest $REG/omi-oss-$img:latest
  docker push $REG/omi-oss-$img:latest
done
curl -s http://$REG/v2/_catalog                  # -> lists the 5 repositories

# 3. Tell k0s's containerd it may pull from this (plain-HTTP) registry
sudo mkdir -p /etc/k0s/containerd.d/certs.d/$REG
sudo tee /etc/k0s/containerd.d/certs.d/$REG/hosts.toml >/dev/null <<EOF
server = "http://$REG"
[host."http://$REG"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
sudo tee /etc/k0s/containerd.d/registry.toml >/dev/null <<'EOF'
version = 3
[plugins]
  [plugins."io.containerd.cri.v1.images"]
    [plugins."io.containerd.cri.v1.images".registry]
      config_path = "/etc/k0s/containerd.d/certs.d"
EOF
sudo k0s stop && sudo k0s start
```

At install (step 7) you pass `--set imageRegistry=$REG`; the chart prefixes it onto the five names, so the
pods pull `$REG/omi-oss-backend`, `$REG/omi-oss-whisper`, and so on.

### 5c. Provide the model weights

The GPU servers read their models from a **persistent volume** (a Kubernetes PVC) that the chart mounts
**read-only** into every inference pod. This is the portable, cluster-native way — it works on any Kubernetes,
including multi-node. There is no host directory to manage and nothing k0s-specific.

The models are downloaded into that volume **once**; after that inference needs no internet. The easiest way
is to let the chart do it for you at install: it creates the PVC and runs a one-time Job that fetches whisper
+ pyannote and converts nllb into it. You only need a **Hugging Face token**, because one of the diarization
models (pyannote) is license-gated:

```bash
# 1. Create a token at https://huggingface.co/settings/tokens
# 2. On each pyannote model page, click "Agree and access" once (the token's account needs the licenses):
#    huggingface.co/pyannote/speaker-diarization-community-1 · /pyannote/embedding · /pyannote/wespeaker-voxceleb-resnet34-LM
export HF_TOKEN=hf_xxxxxxxx
```

You pass this token in step 7 (two `--set` flags) and the chart handles the download. The provisioning Job
runs on **CPU** — it doesn't compete with the GPU — and skips any model already present, so it's cheap to
leave enabled. (The parakeet service needs no model; it is a thin gateway that forwards speech to whisper.)

- **Size:** the PVC is 40Gi by default — change with `--set inference.inCluster.models.size=60Gi`.
- **Multi-node:** if inference pods can land on different nodes, use a storage class that supports shared read
  access and add `--set inference.inCluster.models.accessModes[0]=ReadOnlyMany`.
- **Already have the weights** on a PVC? Point the chart at it and skip provisioning:
  `--set inference.inCluster.models.existingClaim=<your-pvc>`.

---

## 6. Cluster add-ons

Three cluster-level components the chart relies on (installed once, like on any Kubernetes):

```bash
# 6a. Envoy Gateway — the HTTPS entry point (Gateway API)
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.2.1 \
  -n envoy-gateway-system --create-namespace --wait

# 6b. OpenEBS — local persistent storage (gives the "openebs-hostpath" storage class)
helm repo add openebs https://openebs.github.io/openebs && helm repo update openebs
helm install openebs openebs/openebs -n openebs --create-namespace --wait \
  --set engines.replicated.mayastor.enabled=false \
  --set engines.local.lvm.enabled=false --set engines.local.zfs.enabled=false

# 6c. MetalLB — lets the cluster own ENTRY_IP on your LAN
helm repo add metallb https://metallb.github.io/metallb && helm repo update metallb
helm install metallb metallb/metallb -n metallb-system --create-namespace --wait
# Put YOUR ENTRY_IP into the pool file, then apply it:
sed -i "s#192.168.100.190/32#$ENTRY_IP/32#" metallb-pool-k0s.yaml
kubectl apply -f metallb-pool-k0s.yaml
```

---

## 7. TLS certificate + install Omi

```bash
export KUBECONFIG=~/.kube/k0s.conf

# A TLS cert whose SAN carries ENTRY_IP (self-signed; bring your own CA-signed cert for real prod)
kubectl create namespace omi --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=$ENTRY_IP ./gen-certs.sh omi omi-tls $ENTRY_IP

# Install. Everything site-specific is passed here, so no IP/secret is committed in the chart files.
helm install omi ./omi-oss -n omi -f omi-oss/values-k0s.yaml \
  --set imageRegistry=$REG \
  --set ingress.loadBalancerIP=$ENTRY_IP \
  --set inference.inCluster.models.provision.enabled=true \
  --set inference.inCluster.models.provision.huggingFaceToken=$HF_TOKEN \
  --set inference.openai.baseUrl=$LLM \
  --set inference.embeddings.baseUrl=$LLM \
  --set inference.embeddings.model=bge-m3 \
  --set backend.encryptionSecret="$(openssl rand -hex 32)"
```

Watch it come up (first start pulls images and loads GPU models — give it a few minutes):
```bash
kubectl -n omi get pods -w
```
You want everything `Running`/`Completed`: `backend`, `mongo-0`, `valkey-0`, `qdrant-0`, `rustfs-0`,
`ntfy-0`, `keycloak-0`, `keycloak-postgres-0`, and the inference `whisper`, `parakeet`, `diarizer`, `nllb`.

> **Embeddings dimension.** The default embeddings model is `bge-m3` (1024-dim) and the vector store is
> already set to 1024 — nothing to do. If you use a **different** embeddings model, also pass its dimension,
> e.g. `--set chat.vectorDim=768` (nomic-embed-text) — otherwise vector writes are rejected.

---

## 8. Passwords & secrets — where they go

The install above sets **one** real secret and leaves the rest as **throwaway defaults suitable for a first
run**. Before real production, set them all. There are two ways.

**What the secrets are**
| Secret | Used by | Default in `values-k0s.yaml` |
|---|---|---|
| `backend.encryptionSecret` | encrypts stored user data (required, no default) | you pass it via `--set` (the `openssl rand -hex 32` above) |
| `auth.adminPassword` | the Keycloak admin console | `admin` |
| `auth.keycloak.postgres.password` | Keycloak's database | `keycloak-dev` |
| `objstore.accessKey` / `objstore.secretKey` | the S3 object store (RustFS) | `rustfsadmin` / `rustfsadmin` |

**Option A — pass them at install (simplest).** Add `--set` flags for each; nothing is written to disk:
```bash
helm install omi ./omi-oss -n omi -f omi-oss/values-k0s.yaml \
  --set imageRegistry=$REG --set ingress.loadBalancerIP=$ENTRY_IP \
  --set inference.inCluster.models.provision.enabled=true \
  --set inference.inCluster.models.provision.huggingFaceToken=$HF_TOKEN \
  --set inference.openai.baseUrl=$LLM --set inference.embeddings.baseUrl=$LLM --set inference.embeddings.model=bge-m3 \
  --set backend.encryptionSecret="$(openssl rand -hex 32)" \
  --set auth.adminPassword="$(openssl rand -base64 24)" \
  --set auth.keycloak.postgres.password="$(openssl rand -base64 24)" \
  --set objstore.accessKey="omi-s3" --set objstore.secretKey="$(openssl rand -base64 24)"
```
Keep these values somewhere safe — you must pass the **same** ones on every future `helm upgrade`, or the
components (and any data encrypted with the old `encryptionSecret`) won't line up.

**Option B — a Kubernetes Secret you manage (recommended for real prod).** Create the Secret yourself (from a
vault, Sealed Secrets, External Secrets, …) and tell the chart not to build one:
```bash
kubectl -n omi create secret generic backend-secret \
  --from-literal=ENCRYPTION_SECRET="$(openssl rand -hex 32)" \
  --from-literal=KC_ADMIN_PASSWORD="…" \
  --from-literal=KC_DB_PASSWORD="…" \
  --from-literal=S3_ACCESS_KEY="…" --from-literal=S3_SECRET_KEY="…"
# then install with:
helm install omi ./omi-oss -n omi -f omi-oss/values-k0s.yaml --set secrets.create=false \
  --set imageRegistry=$REG --set ingress.loadBalancerIP=$ENTRY_IP \
  --set inference.inCluster.models.provision.enabled=true \
  --set inference.inCluster.models.provision.huggingFaceToken=$HF_TOKEN \
  --set inference.openai.baseUrl=$LLM --set inference.embeddings.baseUrl=$LLM --set inference.embeddings.model=bge-m3
```
With `secrets.create=false` the chart references the Secret by name and never sees the values.

---

## 9. Verify

```bash
# API health
curl -k https://$ENTRY_IP/v1/health                              # {"status":"ok"}

# Login works (a real token is accepted, a bad one is rejected)
TOK=$(curl -k -s -X POST https://$ENTRY_IP/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k -o /dev/null -w 'valid token -> %{http_code}\n' https://$ENTRY_IP/v1/users/people -H "Authorization: Bearer $TOK"   # 200
curl -k -o /dev/null -w 'bad   token -> %{http_code}\n' https://$ENTRY_IP/v1/users/people -H "Authorization: Bearer nope"   # 401

# Inference runs on the GPU inside the cluster (translation shown; STT + diarization work the same way):
kubectl -n omi exec deploy/backend -c backend -- \
  curl -fsS -X POST http://nllb:8080/v1/translate -H 'Content-Type: application/json' \
  -d '{"contents":["The on-prem cluster runs inference on the GPU."],"target_language_code":"it"}'
#   -> "Il cluster on-premise esegue inferenze sulla GPU."
```

---

## 10. Day-two operations

- **What runs where.** In the cluster: the API, the datastore (MongoDB), cache (Valkey), vector store
  (Qdrant), object store (RustFS), push server (ntfy), login (Keycloak + Postgres), and the GPU inference
  servers (whisper + parakeet gateway, diarizer, nllb). Outside: only the chat LLM and the embeddings model.
- **One GPU, several models.** The device plugin advertises 4 GPU units (step 4c) so whisper, diarizer and
  nllb share the card. If you add engines or hit out-of-memory, raise VRAM / add a GPU, or lower the GPU
  services (`--set inference.inCluster.services.<name>.enabled=false`).
- **Use external inference instead** (no in-cluster GPU): `--set inference.inCluster.enabled=false`, and point
  `inference.openai.baseUrl` / the speech endpoints at your own servers.
- **Change anything:** re-run the command with `helm upgrade` instead of `helm install` — and pass the **same**
  `--set` secrets/values each time.
- **Uninstall:** `helm uninstall omi -n omi` (data volumes remain until you delete the PVCs or the cluster).
