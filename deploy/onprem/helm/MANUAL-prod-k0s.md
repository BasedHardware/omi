# Omi self-hosted — Production manual (k0s, on a GPU server)

Step-by-step to run the whole Omi backend on your own hardware, on a real single-node Kubernetes cluster
(k0s). **Speech-to-text, speaker diarization and translation run on the GPU inside the cluster** — only the
chat LLM and the embeddings model are external (any OpenAI-compatible server you run). Nothing else leaves
your machines.

The manual has two parts: **Part 1** sets up the cluster (k0s + its dependencies); **Part 2** installs Omi on
top of it. Everything below was executed and verified on Ubuntu 24.04 with an NVIDIA RTX 5060 Ti (16 GB).

---

## Requirements

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

**External services / accounts you provide**
- An **OpenAI-compatible LLM + embeddings endpoint** reachable from the node — e.g. [Ollama](https://ollama.com)
  serving a chat model and an embeddings model (`bge-m3`). Note its URL.
- A **Hugging Face account + token** — one of the diarization models (`pyannote`) is license-gated, so
  downloading it (Step 5) needs a free token whose account has accepted the model terms.

**Get the code**
```bash
git clone <your fork of omi> && cd omi/deploy/onprem/helm
```

### Two addresses you will use (important — they are different machines)

This deployment uses **two IP addresses on your LAN**. Keep them straight:

| In this manual | What it is | How to choose it |
|---|---|---|
| **`NODE_IP`** = `192.168.100.122` | **The server's own IP** — where k0s, Docker and the image registry run, and where the node reaches your external LLM. | Your machine's real LAN address. Find it: `ip -4 addr` or `hostname -I`. |
| **`ENTRY_IP`** = `192.168.100.190` | **The cluster's entry point** — a *second, separate, currently-unused* IP on the **same** LAN. MetalLB "borrows" it and answers for it, so users/apps reach Omi (HTTPS + the login page) here. The OIDC issuer and the TLS certificate are pinned to it. | Any **free** address on your LAN subnet — NOT the node's own IP, and not used by any other device or handed out by your DHCP server. Verify it's free: `ping -c1 <ENTRY_IP>` must get **no** reply. |

Why two: the node already has its own IP for host things (registry, SSH, the LLM). The cluster needs its own
stable "service" IP, independent of any single pod — that's what MetalLB provides on `ENTRY_IP`.

Set them once for the shell you'll work in (replace with your real values):
```bash
export NODE_IP=192.168.100.122
export ENTRY_IP=192.168.100.190
export REG=$NODE_IP:5000                       # the registry runs on the node, port 5000
export LLM=http://$NODE_IP:11434/v1            # your external LLM/embeddings (example: Ollama on the node)
```

---

# Part 1 — Set up the cluster

A plain Kubernetes cluster with a GPU and the three add-ons Omi relies on. Nothing Omi-specific yet.

## Step 1 — Install k0s (single node)

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

## Step 2 — Enable the GPU

k0s runs its own containerd, so the GPU is wired at the containerd level, then a device plugin advertises it
to Kubernetes. On one GPU we also turn on **time-slicing** so several inference pods can share it.

```bash
# a. Describe the GPU to the container runtime
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# b. Make the NVIDIA runtime the containerd default + enable CDI
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

# c. Device plugin WITH time-slicing (advertises 4 shareable GPU units — tune in the file's comments)
kubectl apply -f nvidia-device-plugin-k0s.yaml
kubectl -n kube-system rollout status ds/nvidia-device-plugin-daemonset
kubectl get node -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}{"\n"}'   # -> 4
```

## Step 3 — Install the cluster dependencies

Three cluster-level components the chart relies on (installed once, like on any Kubernetes):

```bash
# a. Envoy Gateway — the HTTPS entry point (Gateway API)
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.2.1 \
  -n envoy-gateway-system --create-namespace --wait

# b. OpenEBS — local persistent storage (gives the "openebs-hostpath" storage class)
helm repo add openebs https://openebs.github.io/openebs && helm repo update openebs
helm install openebs openebs/openebs -n openebs --create-namespace --wait \
  --set engines.replicated.mayastor.enabled=false \
  --set engines.local.lvm.enabled=false --set engines.local.zfs.enabled=false

# c. MetalLB — lets the cluster own ENTRY_IP on your LAN
helm repo add metallb https://metallb.github.io/metallb && helm repo update metallb
helm install metallb metallb/metallb -n metallb-system --create-namespace --wait
# Put YOUR ENTRY_IP into the pool file, then apply it:
sed -i "s#192.168.100.190/32#$ENTRY_IP/32#" metallb-pool-k0s.yaml
kubectl apply -f metallb-pool-k0s.yaml
```

The cluster is now ready. Everything from here installs Omi.

---

# Part 2 — Install Omi

## Step 4 — Build & publish the images

Omi ships **five** images we build ourselves: the API (`backend`) and the four inference servers (`whisper`,
`parakeet`, `diarizer`, `nllb`). Everything else — MongoDB, Valkey, Qdrant, RustFS, ntfy, Keycloak — are
public images the cluster pulls on its own; you do **not** build those.

```bash
# a. Build the five images from the compose files (needs internet for the base images; can take a while)
cd ..                                            # deploy/onprem
docker compose -f compose.prod.yaml --profile inference build
cd helm
docker images | grep omi-oss                     # you should see the 5 omi-oss-* images
```

The images now live in **Docker** on the node — but **k0s uses its own container store (containerd)** and
cannot see Docker's images. The bridge is a small **image registry** on the node: you push the images into it
and tell k0s's containerd it may pull from it.

```bash
# b. Run a registry on the node (port 5000)
docker run -d --name omi-registry --restart=unless-stopped -p 0.0.0.0:5000:5000 \
  -v omi-registry-data:/var/lib/registry registry:2

# c. Tag each of the 5 images for the registry and push them
for img in backend whisper parakeet diarizer nllb; do
  docker tag  omi-oss-$img:latest $REG/omi-oss-$img:latest
  docker push $REG/omi-oss-$img:latest
done
curl -s http://$REG/v2/_catalog                  # -> lists the 5 repositories

# d. Tell k0s's containerd it may pull from this (plain-HTTP) registry
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

At install (Step 6) you pass `--set imageRegistry=$REG`; the chart prefixes it onto the five names, so the
pods pull `$REG/omi-oss-backend`, `$REG/omi-oss-whisper`, and so on.

## Step 5 — Provide the model weights

The GPU servers read their models from a **persistent volume** (a Kubernetes PVC) that the chart mounts
**read-only** into every inference pod. This is the portable, cluster-native way — it works on any Kubernetes,
including multi-node. There is no host directory to manage and nothing k0s-specific.

The models are downloaded into that volume **once**; after that inference needs no internet. The easiest way
is to let the chart do it for you at install: it creates the PVC and runs a one-time Job that fetches whisper
+ pyannote and converts nllb into it. You only need a **Hugging Face token**, because the pyannote model is
license-gated:

```bash
# 1. Create a token at https://huggingface.co/settings/tokens
# 2. On each pyannote model page, click "Agree and access" once (the token's account needs the licenses):
#    huggingface.co/pyannote/speaker-diarization-community-1 · /pyannote/embedding · /pyannote/wespeaker-voxceleb-resnet34-LM
export HF_TOKEN=hf_xxxxxxxx
```

You pass this token in Step 6 and the chart handles the download. The provisioning Job runs on **CPU** — it
doesn't compete with the GPU — and skips any model already present, so it's cheap to leave enabled. (The
parakeet service needs no model; it is a thin gateway that forwards speech to whisper.)

- **Size:** the PVC is 40Gi by default — change with `--set inference.inCluster.models.size=60Gi`.
- **Multi-node:** if inference pods can land on different nodes, use a storage class that supports shared read
  access and add `--set inference.inCluster.models.accessModes[0]=ReadOnlyMany`.
- **Already have the weights** on a PVC? Point the chart at it and skip provisioning:
  `--set inference.inCluster.models.existingClaim=<your-pvc>`.

## Step 6 — TLS certificate + install Omi

First a TLS cert whose SAN carries `ENTRY_IP` (self-signed here; bring your own CA-signed cert for real prod):
```bash
export KUBECONFIG=~/.kube/k0s.conf
kubectl create namespace omi --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=$ENTRY_IP ./gen-certs.sh omi omi-tls $ENTRY_IP
```

Generate the secrets, then install. This is the **one** install command — everything site-specific and every
password is passed here, so nothing secret or site-specific is committed in the chart files:
```bash
# Generate the passwords once and SAVE them — you must pass the same ones on every future `helm upgrade`
# (data encrypted with the old ENCRYPTION_SECRET can't be read with a different one).
export ENC_SECRET=$(openssl rand -hex 32)
export KC_ADMIN_PW=$(openssl rand -base64 24)
export KC_DB_PW=$(openssl rand -base64 24)
export S3_KEY=omi-s3;  export S3_SECRET=$(openssl rand -base64 24)

helm install omi ./omi-oss -n omi -f omi-oss/values-k0s.yaml \
  --set imageRegistry=$REG \
  --set ingress.loadBalancerIP=$ENTRY_IP \
  --set inference.inCluster.models.provision.enabled=true \
  --set inference.inCluster.models.provision.huggingFaceToken=$HF_TOKEN \
  --set inference.openai.baseUrl=$LLM \
  --set inference.embeddings.baseUrl=$LLM \
  --set inference.embeddings.model=bge-m3 \
  --set backend.encryptionSecret=$ENC_SECRET \
  --set auth.adminPassword=$KC_ADMIN_PW \
  --set auth.keycloak.postgres.password=$KC_DB_PW \
  --set objstore.accessKey=$S3_KEY --set objstore.secretKey=$S3_SECRET
```

**The passwords, explained** — the four `--set` above cover every secret the stack needs:

| Secret flag | Protects |
|---|---|
| `backend.encryptionSecret` | encrypts stored user data (required — no default) |
| `auth.adminPassword` | the Keycloak admin console |
| `auth.keycloak.postgres.password` | Keycloak's database |
| `objstore.accessKey` / `objstore.secretKey` | the S3 object store (RustFS) |

> Leaving a password off just uses a throwaway default (`admin` / `keycloak-dev` / `rustfsadmin`) — fine for a
> first try, **not** for production. **Prefer an externally-managed Secret?** Create a Secret named
> `backend-secret` yourself (vault / Sealed Secrets / External Secrets) with keys `ENCRYPTION_SECRET`,
> `KC_ADMIN_PASSWORD`, `KC_DB_PASSWORD`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`; add `--set secrets.create=false` to
> the command above and drop the four password `--set` lines. The chart then references it by name and never
> sees the values.

Watch it come up (first start pulls images and loads GPU models — give it a few minutes):
```bash
kubectl -n omi get pods -w
```
You want everything `Running`/`Completed`: `backend`, `mongo-0`, `valkey-0`, `qdrant-0`, `rustfs-0`,
`ntfy-0`, `keycloak-0`, `keycloak-postgres-0`, and the inference `whisper`, `parakeet`, `diarizer`, `nllb`.

> **Embeddings dimension.** The default embeddings model is `bge-m3` (1024-dim) and the vector store is
> already set to 1024 — nothing to do. If you use a **different** embeddings model, also pass its dimension,
> e.g. `--set chat.vectorDim=768` (nomic-embed-text) — otherwise vector writes are rejected.

## Step 7 — Verify

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

## Day-two operations

- **What runs where.** In the cluster: the API, the datastore (MongoDB), cache (Valkey), vector store
  (Qdrant), object store (RustFS), push server (ntfy), login (Keycloak + Postgres), and the GPU inference
  servers (whisper + parakeet gateway, diarizer, nllb). Outside: only the chat LLM and the embeddings model.
- **One GPU, several models.** The device plugin advertises 4 GPU units (Step 2c) so whisper, diarizer and
  nllb share the card. If you add engines or hit out-of-memory, raise VRAM / add a GPU, or lower the GPU
  services (`--set inference.inCluster.services.<name>.enabled=false`).
- **Use external inference instead** (no in-cluster GPU): `--set inference.inCluster.enabled=false`, and point
  `inference.openai.baseUrl` / the speech endpoints at your own servers.
- **Change anything:** re-run the Step 6 command with `helm upgrade` instead of `helm install` — passing the
  **same** `--set` secrets and values each time.
- **Uninstall:** `helm uninstall omi -n omi` (data volumes remain until you delete the PVCs or the cluster).

---

## Configuration reference (all values)

Every value the chart accepts. **"How"** shows how you'd normally set it for this k0s production install:
`values-k0s.yaml` = already set for you by the prod overlay; `--set` = you pass it at install (Step 6);
`default` = leave it unless you have a reason. Override any of them with `--set path=value`.

**Global**

| Value | Default | How | What it does |
|---|---|---|---|
| `imageRegistry` | `""` | `--set` | Registry prefix for the 5 images we build (e.g. `192.168.100.122:5000`). Empty = image already on the node. |
| `storageClassName` | `""` | values-k0s (`openebs-hostpath`) | Storage class for every PVC. Empty = cluster default. |
| `secrets.create` | `true` | default | Chart builds `backend-secret` from values. `false` = you supply the Secret yourself. |
| `networkPolicy.enabled` | `false` | default | Default-deny egress (needs a policy-enforcing CNI: Calico/Cilium). |

**Backend (the API)**

| Value | Default | How | What it does |
|---|---|---|---|
| `backend.encryptionSecret` | `""` | `--set` (required) | Encrypts stored user data. Must stay the same forever. |
| `backend.replicas` | `1` | values-k0s | Number of API pods. |
| `backend.imagePullPolicy` | `Never` | values-k0s (`IfNotPresent`) | Kind loads images; k0s pulls from the registry. |
| `backend.resources` | `{}` | default | CPU/memory requests & limits (values-k0s sets modest ones). |
| `backend.env.*` | offline defaults | default | Non-secret backend env (`STORAGE_BACKEND=mongo`, stage flags, Redis host…). |

**Login — `auth` profile (Keycloak)**

| Value | Default | How | What it does |
|---|---|---|---|
| `auth.enabled` | `false` | values-k0s (`true`) | Turn on OIDC login. |
| `auth.hostname` | `""` | derived | OIDC issuer; empty = `https://<ingress.loadBalancerIP>` (the ENTRY_IP). |
| `auth.adminPassword` | `""` | `--set` | Keycloak admin console password (default `admin`). |
| `auth.keycloak.db` | `dev-file` | values-k0s (`postgres`) | Keycloak's database backend. |
| `auth.keycloak.postgres.password` | `""` | `--set` | Keycloak DB password when `db=postgres` (default `keycloak-dev`). |

**Vector store — `chat` profile (Qdrant)**

| Value | Default | How | What it does |
|---|---|---|---|
| `chat.enabled` | `false` | values-k0s (`true`) | Turn on the on-prem vector store. |
| `chat.vectorDim` | `1024` | default | **Must equal your embeddings model's dimension** (`bge-m3`=1024, `nomic-embed-text`=768…). |

**Object store — `objstore` profile (RustFS / S3)**

| Value | Default | How | What it does |
|---|---|---|---|
| `objstore.enabled` | `false` | values-k0s (`true`) | Turn on the on-prem S3 store. |
| `objstore.accessKey` / `objstore.secretKey` | `""` | `--set` | S3 credentials (default `rustfsadmin`). |
| `objstore.publicEndpoint` | `http://rustfs:9000` | default | Public base URL for object links. |

**Push — `push` profile (ntfy)**

| Value | Default | How | What it does |
|---|---|---|---|
| `push.enabled` | `false` | values-k0s (`true`) | Turn on the on-prem UnifiedPush server. |
| `push.baseUrl` | `http://ntfy` | default | Device-facing URL for the phone's push distributor. |

**Edge — `ingress` profile (Envoy Gateway + MetalLB)**

| Value | Default | How | What it does |
|---|---|---|---|
| `ingress.enabled` | `false` | values-k0s (`true`) | Turn on the HTTPS entry point. |
| `ingress.service.type` | `NodePort` | values-k0s (`LoadBalancer`) | How the edge is exposed (MetalLB on k0s). |
| `ingress.loadBalancerIP` | `""` | `--set` | The ENTRY_IP MetalLB gives the edge. |
| `ingress.tlsSecretName` | `omi-tls` | default | TLS Secret (created by `gen-certs.sh`). |

**Inference — LLM + embeddings external, the rest in-cluster on GPU**

| Value | Default | How | What it does |
|---|---|---|---|
| `inference.enabled` | `false` | values-k0s (`true`) | Wire the external LLM + embeddings. |
| `inference.openai.baseUrl` | `""` | `--set` | External OpenAI-compatible LLM URL. |
| `inference.embeddings.baseUrl` / `.model` | `""` | `--set` | External embeddings endpoint + model (e.g. `bge-m3`). |
| `inference.inCluster.enabled` | `false` | values-k0s (`true`) | Run STT/diarization/translation as GPU pods in-cluster. |
| `inference.inCluster.models.existingClaim` | `""` | `--set` (optional) | Use a models PVC you already have; else the chart creates one. |
| `inference.inCluster.models.size` | `40Gi` | `--set` (optional) | Size of the models PVC. |
| `inference.inCluster.models.accessModes` | `[ReadWriteOnce]` | `--set` for multi-node | `[ReadOnlyMany]` when inference pods span nodes (needs an RWX/ROX class). |
| `inference.inCluster.models.provision.enabled` | `false` | `--set` (`true`) | One-time Job that downloads the weights into the PVC. |
| `inference.inCluster.models.provision.huggingFaceToken` | `""` | `--set` | HF token for the gated pyannote model. |
| `inference.inCluster.nodeSelector` | `{}` | `--set` for multi-node | Pin GPU pods to the GPU node(s). |
| `inference.inCluster.services.<name>.enabled` | `true` | `--set` to disable | Turn an engine off (`whisper`/`parakeet`/`diarizer`/`nllb`). |
| `inference.inCluster.services.<name>.gpu` | `1` | default | GPU units the engine requests (`parakeet` uses none — CPU gateway). |

**Persistent volume sizes** (all take a `--set …storage=` / `…size=` override)

| Component | Value | Default |
|---|---|---|
| MongoDB | `mongo.storage` | `2Gi` |
| Valkey | `valkey.storage` | `1Gi` |
| Qdrant (chat) | `chat.qdrant.storage` | `2Gi` |
| RustFS (objstore) | `objstore.rustfs.storage` | `5Gi` |
| ntfy (push) | `push.ntfy.storage` | `1Gi` |
| Keycloak (auth) | `auth.keycloak.storage` | `1Gi` |
| Keycloak DB (auth) | `auth.keycloak.postgres.storage` | `2Gi` |
| Inference models | `inference.inCluster.models.size` | `40Gi` |

Third-party image pins (mongo, valkey, qdrant, rustfs, ntfy, keycloak, postgres) also live in the values but
you rarely change them — see `omi-oss/values.yaml` for the exact tags/digests.
