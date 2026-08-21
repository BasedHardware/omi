# Omi self-hosted — Production manual (k0s, on a GPU server)

Step-by-step to run the whole Omi backend on your own hardware, on a real single-node Kubernetes cluster
(k0s). **Speech-to-text, speaker diarization and translation run on the GPU inside the cluster** — only the
chat LLM and the embeddings model are external (any OpenAI-compatible server you run). Nothing else leaves
your machines.

The manual has two parts: **Part 1** sets up the cluster (k0s + its dependencies); **Part 2** installs Omi on
top of it. Every command is in its own copy box. Verified on Ubuntu 24.04 with an NVIDIA RTX 5060 Ti (16 GB).

---

## Requirements

**Hardware**
- A Linux server (the "node"). Tested on Ubuntu 24.04.
- An NVIDIA GPU with **≥ 16 GB** VRAM (the default STT + diarization + translation share one card via GPU
  time-slicing). More VRAM / more GPUs = more headroom.
- ~60 GB free disk (container images + model weights).

**Software on the node (install these first)**
- **NVIDIA driver** — `nvidia-smi` must print your GPU. (The GPU Operator in Step 2 installs the container
  toolkit and configures containerd for you, so you don't need to set those up by hand.)
- **Docker** — to build the Omi images and run a local image registry.
- **kubectl**, **helm** (v3.16+), **openssl**, **git**, **curl**.

**External services / accounts you provide**
- An **OpenAI-compatible LLM + embeddings endpoint** reachable from the node — e.g. [Ollama](https://ollama.com)
  serving a chat model and an embeddings model (`bge-m3`). Note its URL.
- A **Hugging Face account + token** — one of the diarization models (`pyannote`) is license-gated, so
  downloading it (Step 5) needs a free token whose account has accepted the model terms.

**Get the code:**
```bash
git clone <your fork of omi> && cd omi/deploy/onprem/helm
```

### The four variables you'll use

Set these once for the shell you work in (every later command uses them). Two are **IP addresses on your
LAN** — and they are *different machines*, so keep them straight:

| Variable | What it is | How to choose it |
|---|---|---|
| **`NODE_IP`** = `192.168.100.122` | **The server's own IP** — where k0s, Docker and the image registry run, and where the node reaches your external LLM. | Your machine's real LAN address: `ip -4 addr` / `hostname -I`. |
| **`ENTRY_IP`** = `192.168.100.190` | **The cluster's entry point** — a *second, free, currently-unused* IP on the **same** LAN. MetalLB "borrows" it so users/apps reach Omi (HTTPS + login) here; the OIDC issuer and TLS cert are pinned to it. | Any **free** address on your LAN — NOT the node's IP, not used by another device or your DHCP pool. Verify: `ping -c1 <ENTRY_IP>` gets **no** reply. |
| **`REG`** = `NODE_IP:5000` | **The image registry** — a small registry you run on the node (Step 4) so k0s can pull the Omi images. | Just the node's IP with port `5000`. |
| **`LLM`** | **Your external LLM + embeddings** endpoint (OpenAI-compatible). | The URL of your Ollama/vLLM/OpenAI server, e.g. `http://<NODE_IP>:11434/v1`. |

Why two IPs: the node already has its own IP for host things (registry, SSH, the LLM). The cluster needs its
own stable "service" IP, independent of any single pod — that's what MetalLB gives it on `ENTRY_IP`.

```bash
export NODE_IP=192.168.100.122            # your server's LAN IP
export ENTRY_IP=192.168.100.190           # a free LAN IP for the cluster's entry point
export REG=$NODE_IP:5000                  # the image registry, on the node
export LLM=http://$NODE_IP:11434/v1       # your external LLM/embeddings (example: Ollama on the node)
```

---

# Part 1 — Set up the cluster

A plain Kubernetes cluster with a GPU and the three add-ons Omi relies on. Nothing Omi-specific yet.

## Step 1 — Install k0s (single node)

Install the k0s binary:
```bash
curl -sSLf https://get.k0s.sh | sudo sh
```

Install a single-node cluster (controller + worker on one machine) and start it:
```bash
sudo k0s install controller --single
sudo k0s start
sudo k0s status                           # wait for "Kube-api ... Running"
```

Get a kubeconfig for kubectl/helm (repeat the `export` in every new shell, or add it to your `~/.bashrc`):
```bash
sudo k0s kubeconfig admin > ~/.kube/k0s.conf
export KUBECONFIG=~/.kube/k0s.conf
kubectl get nodes                         # your node should be Ready
```

## Step 2 — Enable the GPU (NVIDIA GPU Operator)

k0s recommends the **NVIDIA GPU Operator**: one install deploys the container toolkit, wires k0s's own
containerd for the GPU, and runs the device plugin — you never edit containerd by hand. The node only needs
the NVIDIA driver (Step 1 requirements); the Operator does the rest.

Add the NVIDIA helm repo:
```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia && helm repo update nvidia
```

Install the Operator. `driver.enabled=false` reuses the driver already on the node; the `toolkit.env`
values are the **k0s-specific** containerd config path + socket + runtime class:
```bash
helm install gpu-operator -n gpu-operator --create-namespace nvidia/gpu-operator \
  --set driver.enabled=false \
  --set toolkit.env[0].name=CONTAINERD_CONFIG --set toolkit.env[0].value=/etc/k0s/containerd.d/nvidia.toml \
  --set toolkit.env[1].name=CONTAINERD_SOCKET --set toolkit.env[1].value=/run/k0s/containerd.sock \
  --set toolkit.env[2].name=CONTAINERD_RUNTIME_CLASS --set toolkit.env[2].value=nvidia \
  --wait
```

Turn on **GPU time-slicing** so the STT/diarization/translation pods can share one card, and point the
Operator at the config (skip this if you have a GPU per inference service):
```bash
kubectl apply -f gpu-operator-timeslicing.yaml
kubectl patch clusterpolicy cluster-policy --type merge \
  -p '{"spec":{"devicePlugin":{"config":{"name":"time-slicing-config","default":"any"}}}}'
```

Verify the node now offers GPU units:
```bash
kubectl get node -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}{"\n"}'   # -> 4
```

> Prefer not to run the Operator? The repo also ships `nvidia-device-plugin-k0s.yaml` for a lighter manual
> setup (a containerd drop-in + a plain device plugin with the same time-slicing). The Operator is the
> k0s-recommended path and is what the rest of this manual assumes.

## Step 3 — Install the cluster dependencies

Three cluster-level components the chart relies on (installed once, like on any Kubernetes).

**a. Envoy Gateway** — the HTTPS entry point (Gateway API):
```bash
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.2.1 \
  -n envoy-gateway-system --create-namespace --wait
```

**b. OpenEBS** — local persistent storage (gives the `openebs-hostpath` storage class):
```bash
helm repo add openebs https://openebs.github.io/openebs && helm repo update openebs
```
```bash
helm install openebs openebs/openebs -n openebs --create-namespace --wait \
  --set engines.replicated.mayastor.enabled=false \
  --set engines.local.lvm.enabled=false --set engines.local.zfs.enabled=false
```

**c. MetalLB** — lets the cluster own `ENTRY_IP` on your LAN:
```bash
helm repo add metallb https://metallb.github.io/metallb && helm repo update metallb
```
```bash
helm install metallb metallb/metallb -n metallb-system --create-namespace --wait
```
Put YOUR `ENTRY_IP` into the pool file and apply it:
```bash
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

**a.** Build the five images from the compose files (needs internet for the base images; can take a while):
```bash
# OMI_OSS_REVISION is optional but recommended: it stamps the commit into each image, so
# `docker inspect <image>` later tells you exactly what is running.
OMI_OSS_REVISION=$(git rev-parse HEAD) docker compose -f ../compose.prod.yaml --profile inference build
```
```bash
docker images | grep omi-oss              # you should see the 5 omi-oss-* images
```

The images now live in **Docker** on the node — but **k0s uses its own container store (containerd)** and
cannot see Docker's images. The bridge is a small **image registry** on the node.

**b.** Run a registry on the node (port 5000):
```bash
docker run -d --name omi-registry --restart=unless-stopped -p 0.0.0.0:5000:5000 \
  -v omi-registry-data:/var/lib/registry registry:2
```

The build tags every image with the **release** — one number describing this whole stack, kept in
`deploy/onprem/omi.oss.release.env`. Read it once; the chart uses the same value by default, so the tag you
push and the tag the cluster pulls cannot disagree:
```bash
RELEASE=$(grep '^OMI_OSS_RELEASE=' ../omi.oss.release.env | cut -d= -f2)
echo $RELEASE                             # -> e.g. 0.2.0
```

**c.** Tag each of the five images for the registry and push them:
```bash
for img in backend whisper parakeet diarizer nllb; do
  docker tag  omi-oss-$img:$RELEASE $REG/omi-oss-$img:$RELEASE
  docker push $REG/omi-oss-$img:$RELEASE
done
```
(The build also produces `:latest` as a local alias for development. Do **not** push or deploy that one:
a mutable tag makes a later `helm upgrade` leave the pod spec unchanged, so the node keeps serving the
cached image and the upgrade silently does nothing.)
```bash
curl -s http://$REG/v2/_catalog           # -> lists the 5 repositories
```

**d.** Tell k0s's containerd it may pull from this (plain-HTTP) registry:
```bash
sudo mkdir -p /etc/k0s/containerd.d/certs.d/$REG
sudo tee /etc/k0s/containerd.d/certs.d/$REG/hosts.toml >/dev/null <<EOF
server = "http://$REG"
[host."http://$REG"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
```
```bash
sudo tee /etc/k0s/containerd.d/registry.toml >/dev/null <<'EOF'
version = 3
[plugins]
  [plugins."io.containerd.cri.v1.images"]
    [plugins."io.containerd.cri.v1.images".registry]
      config_path = "/etc/k0s/containerd.d/certs.d"
EOF
```
```bash
sudo k0s stop && sudo k0s start
```

At install (Step 6) you pass `--set imageRegistry=$REG`; the chart prefixes it onto the five names, so the
pods pull `$REG/omi-oss-backend`, `$REG/omi-oss-whisper`, and so on.

### Already run your own registry?

Steps **b–d** stand up a throwaway registry on the node. If you already operate one — Harbor, GitLab, a
shared Docker registry — **skip step b** and instead:

- Set `REG` to your registry's `host:port` and **push the five images there** (step **c**). If it requires
  a login, run `docker login $REG` first.
- Point k0s's containerd at it (step **d**). If your registry serves **HTTPS with a certificate the node
  already trusts**, drop the `server = …` / `skip_verify = true` lines — containerd validates it normally;
  keep them only for a plain-HTTP or self-signed registry.

**Authenticated registry.** A registry that needs a login also needs the *cluster* to authenticate when it
pulls. Create a pull Secret in the release namespace (created in Step 6) and tell the chart to use it — it
attaches the Secret to **every** pod, so it covers both our `omi-oss-*` images and any third-party images
you mirror through your registry:
```bash
kubectl -n omi create secret docker-registry regcred \
  --docker-server=$REG --docker-username=<user> --docker-password=<password>
```
Then add `--set imagePullSecrets[0].name=regcred` to the `helm install` in Step 6. Leave it out entirely
for an anonymous registry (the default). No cluster-level "credential manager" is needed — this one Secret
per registry is the whole mechanism.

## Step 5 — Provide the model weights

The GPU servers read their models from a **persistent volume** (a Kubernetes PVC) that the chart mounts
**read-only** into every inference pod. This is the portable, cluster-native way — it works on any Kubernetes,
including multi-node. There is no host directory to manage and nothing k0s-specific.

The models are downloaded into that volume **once**; after that inference needs no internet. The easiest way
is to let the chart do it at install: it creates the PVC and runs a one-time Job that fetches whisper +
pyannote and converts nllb into it. You only need a **Hugging Face token**, because the pyannote model is
license-gated.

Create a token at <https://huggingface.co/settings/tokens>, then on each pyannote model page click
"Agree and access" once (the token's account needs the licenses):
`pyannote/speaker-diarization-community-1`, `pyannote/embedding`, `pyannote/wespeaker-voxceleb-resnet34-LM`.
```bash
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

Create the release namespace, then the TLS certificate for the HTTPS entry point. The helper
`gen-certs.sh` generates a **self-signed** certificate whose SAN covers `ENTRY_IP` (plus `localhost` and
`127.0.0.1`) and loads it into a Kubernetes Secret named **`omi-tls`** — the Secret the gateway serves
HTTPS from. Its arguments are `./gen-certs.sh <namespace> <secret-name> <hostname>`, and the `HOST_IP=`
prefix adds the device-reachable IP to the certificate's SAN so both in-cluster and phone traffic
validate. It only needs `openssl` + `kubectl`, and re-running it simply replaces the Secret.
```bash
export KUBECONFIG=~/.kube/k0s.conf
kubectl create namespace omi --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=$ENTRY_IP ./gen-certs.sh omi omi-tls $ENTRY_IP
```
Because the certificate is self-signed, clients (curl, the phone app) see a trust warning until they trust
it. For real production you'll bring your own certificate instead — two cases:

**You already have a certificate + key.** Skip `gen-certs.sh` and create the `omi-tls` Secret straight from
your files. `tls.crt` must hold the **full chain** — your server (leaf) certificate first, then any
intermediate certificates — and `tls.key` its private key:
```bash
kubectl -n omi create secret tls omi-tls --cert=fullchain.pem --key=privkey.pem
```
That is the whole step: the gateway serves exactly what's in the Secret (re-run with `--dry-run=client -o
yaml | kubectl apply -f -` to rotate it in place).

**Your certificate is signed by a private / internal CA.** Just put the chain in `tls.crt` — leaf first,
then the intermediate(s) up to (but not including) the root. **No dedicated CA setting is needed on the
cluster**, because TLS is terminated at the edge and *nothing inside the cluster validates this
certificate*: the backend talks to Keycloak, ntfy and RustFS over plain HTTP on internal service names, and
validates OIDC tokens by fetching JWKS internally — never back through the HTTPS gateway. The custom CA is
purely a **client-trust** matter: install your root CA on the phone/device (and pass `--cacert ca.crt` to
curl) so they accept the chain. (An external LLM/embeddings endpoint behind its own private CA is a
separate concern — that's the backend trusting *that* endpoint, not this gateway certificate.)

Generate the passwords once and **save them** — you must pass the same ones on every future `helm upgrade`
(data encrypted with the old `ENCRYPTION_SECRET` can't be read with a different one):
```bash
export ENC_SECRET=$(openssl rand -hex 32)
export KC_ADMIN_PW=$(openssl rand -base64 24)
export KC_DB_PW=$(openssl rand -base64 24)
export S3_KEY=omi-s3;  export S3_SECRET=$(openssl rand -base64 24)
```

Install. This is the **one** install command — everything site-specific and every password is passed here,
so nothing secret or site-specific is committed in the chart files:
```bash
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
> the command above and drop the four password `--set` lines. The chart then references it by name.

Watch it come up (first start pulls images and loads GPU models — give it a few minutes):
```bash
kubectl -n omi get pods -w
```
You want everything `Running`/`Completed`: `backend`, `mongo-0`, `valkey-0`, `qdrant-0`, `rustfs-0`,
`ntfy-0`, `keycloak-0`, `keycloak-postgres-0`, and the inference `whisper`, `parakeet`, `diarizer`, `nllb`.

> **Embeddings dimension.** `bge-m3` is 1024-dim and the vector store is already 1024 — nothing to do. A
> different embeddings model needs its dimension too: `--set chat.vectorDim=768` (e.g. nomic-embed-text).

## Step 7 — Verify

API health:
```bash
curl -k https://$ENTRY_IP/v1/health                              # {"status":"ok"}
```

Login works (a real token is accepted, a bad one is rejected):
```bash
TOK=$(curl -k -s -X POST https://$ENTRY_IP/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k -o /dev/null -w 'valid token -> %{http_code}\n' https://$ENTRY_IP/v1/users/people -H "Authorization: Bearer $TOK"   # 200
curl -k -o /dev/null -w 'bad   token -> %{http_code}\n' https://$ENTRY_IP/v1/users/people -H "Authorization: Bearer nope"   # 401
```

Inference runs on the GPU inside the cluster (translation shown; STT + diarization work the same way):
```bash
kubectl -n omi exec deploy/backend -c backend -- \
  curl -fsS -X POST http://nllb:8080/v1/translate -H 'Content-Type: application/json' \
  -d '{"contents":["The on-prem cluster runs inference on the GPU."],"target_language_code":"it"}'
#   -> "Il cluster on-premise esegue inferenze sulla GPU."
```

---

### Chat (on-prem LLM) — verify it end to end

The chat path has its own script, driven from **outside** the cluster (a container in its own network
namespace, so the request leaves the host and comes back through the LoadBalancer, like a phone would):

```bash
ENTRY_IP=$ENTRY_IP deploy/onprem/helm/run-chat-e2e-k0s.sh
```

It gets a real Keycloak token, runs a chat turn, and rejects the canned apology chat returns when the
LLM call fails (a non-empty answer is not proof of success). It also asserts the negative half: the
`llm-gateway` must NOT answer on the entry point — inference is an authenticated capability of the
backend, not a service on the edge — and an unauthenticated `POST /v2/messages` must be 401.

Enable the gateway at install/upgrade time:
```bash
--set chat.enabled=true --set chat.llmGateway.enabled=true \
--set chat.llmGateway.serviceToken=$(openssl rand -hex 24) \
--set chat.llmGateway.model=<the model your endpoint serves> \
--set inference.openai.baseUrl=http://<your-endpoint>/v1 --set inference.openai.apiKey=<placeholder>
```
The API key can be a placeholder for a local endpoint that ignores it (compose uses `ollama`), but it
must be **present**: the gateway treats a missing credential as `invalid_config` and answers 503 on
every turn, which reaches the user as a generic apology.

## Day-two operations

- **What runs where.** In the cluster: the API, the datastore (MongoDB), cache (Valkey), vector store
  (Qdrant), object store (RustFS), push server (ntfy), login (Keycloak + Postgres), and the GPU inference
  servers (whisper + parakeet gateway, diarizer, nllb). Outside: only the chat LLM and the embeddings model.
- **One GPU, several models.** The Operator advertises 4 GPU units (Step 2) so whisper, diarizer and nllb
  share the card. If you add engines or hit out-of-memory, raise VRAM / add a GPU, or lower the GPU services
  (`--set inference.inCluster.services.<name>.enabled=false`).
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
| `imagePullSecrets` | `[]` | `--set` | Pull secrets for a **private/authenticated** registry (Harbor, GitLab, …). Names of pre-created `docker-registry` Secrets; attached to every pod. Empty = anonymous pull (the default local registry). |
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

**Persistent volume sizes** (each takes a `--set …storage=` / `…size=` override)

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
