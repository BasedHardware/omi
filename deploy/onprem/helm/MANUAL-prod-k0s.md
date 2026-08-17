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
- One **free IP address on the node's LAN** (the cluster's entry point). Below we use `192.168.100.190` —
  replace it everywhere with yours.

**Software on the node (install these first)**
- **NVIDIA driver** — `nvidia-smi` must print your GPU.
- **NVIDIA Container Toolkit** — `sudo apt-get install -y nvidia-container-toolkit` (provides
  `nvidia-ctk` and `nvidia-container-runtime`).
- **Docker** — to build the Omi images and run a local image registry.
- **kubectl**, **helm** (v3.16+), **openssl**, **git**, **curl**.

**External service you provide**
- An **OpenAI-compatible LLM + embeddings endpoint** reachable from the node — e.g. [Ollama](https://ollama.com)
  serving a chat model and an embeddings model (`bge-m3`). Note its URL, e.g. `http://192.168.100.122:11434/v1`.

Get the code:
```bash
git clone <your fork of omi> && cd omi/deploy/onprem/helm
```

---

## 2. Install k0s (single node)

```bash
# Install the k0s binary
curl -sSLf https://get.k0s.sh | sudo sh

# Install a single-node cluster (controller + worker on the same machine) and start it
sudo k0s install controller --single
sudo k0s start
sudo k0s status                       # wait until "Kube-api ... Running"

# Kubeconfig for kubectl/helm (do this in every new shell, or add to your profile)
sudo k0s kubeconfig admin > ~/.kube/k0s.conf
export KUBECONFIG=~/.kube/k0s.conf
kubectl get nodes                     # your node should be Ready
```

---

## 3. Give k0s access to the GPU

k0s runs its own containerd, so the GPU is wired at the containerd level, then a device plugin advertises
the GPU to Kubernetes. On one GPU we also turn on **time-slicing** so several inference pods can share it.

```bash
# 3a. Generate a CDI spec for your GPU (describes the device to the container runtime)
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# 3b. Make the NVIDIA runtime the containerd default + enable CDI. Create the drop-in:
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
sudo k0s stop && sudo k0s start       # restart k0s to load the drop-in

# 3c. Device plugin WITH time-slicing (advertises 4 shareable GPU units — see the file's comments to tune)
kubectl apply -f nvidia-device-plugin-k0s.yaml
kubectl -n kube-system rollout status ds/nvidia-device-plugin-daemonset
kubectl get node -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}{"\n"}'   # -> 4
```

---

## 4. Local image registry + build & push the Omi images

k0s pulls the images WE build (backend + the inference servers) from a registry on the node.

```bash
# 4a. Run a local registry on the node (port 5000). Replace 192.168.100.122 with the node's own IP.
docker run -d --name omi-registry --restart=unless-stopped -p 0.0.0.0:5000:5000 \
  -v omi-registry-data:/var/lib/registry registry:2
REG=192.168.100.122:5000

# 4b. Build the images (backend + whisper/parakeet/diarizer/nllb) from the compose files, then push.
#     (This can take a while and needs internet for the base images.)
cd ../                                                       # deploy/onprem
docker compose -f compose.prod.yaml --profile inference build
for img in backend whisper parakeet diarizer nllb; do
  docker tag  omi-oss-$img:latest $REG/omi-oss-$img:latest
  docker push $REG/omi-oss-$img:latest
done
cd helm

# 4c. Tell k0s's containerd it may pull from this (plain-HTTP) registry.
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

---

## 5. Provide the inference model weights

The GPU servers load their models from disk (no download at runtime). Provision the weights **once** into a
directory on the node and point the chart at it. The reproducible way is the compose inference recipe, which
downloads faster-whisper (`large-v3`), the NLLB translation model and the pyannote diarization model (the
pyannote repo is gated — you need a free Hugging Face token the first time) into a Docker volume:

```bash
# Follow deploy/onprem/SELFHOST_NOTES.md, section "Local inference", to populate the models volume, then:
docker volume inspect omi-oss_inference-models --format '{{.Mountpoint}}'
#   -> /var/lib/docker/volumes/omi-oss_inference-models/_data   (this is your modelsHostPath)
```

The default `inference.inCluster.modelsHostPath` already points there. If your weights live elsewhere, pass
`--set inference.inCluster.modelsHostPath=/your/path` in step 7.

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

# 6c. MetalLB — gives the entry point a real LAN IP. Then a pool with YOUR free IP.
helm repo add metallb https://metallb.github.io/metallb && helm repo update metallb
helm install metallb metallb/metallb -n metallb-system --create-namespace --wait
#   Edit metallb-pool-k0s.yaml -> set your free LAN IP (192.168.100.190/32), then:
kubectl apply -f metallb-pool-k0s.yaml
```

---

## 7. TLS certificate + install Omi

```bash
export KUBECONFIG=~/.kube/k0s.conf
LBIP=192.168.100.190          # your free LAN IP from step 6c
REG=192.168.100.122:5000      # your registry from step 4
LLM=http://192.168.100.122:11434/v1   # your external OpenAI-compatible endpoint

# 7a. A TLS cert whose SAN carries the entry-point IP (self-signed; bring your own for real prod)
kubectl create namespace omi --dry-run=client -o yaml | kubectl apply -f -
HOST_IP=$LBIP ./gen-certs.sh omi omi-tls $LBIP

# 7b. Install. Everything site-specific is passed here, so nothing secret/IP is committed in the values.
helm install omi ./omi-oss -n omi -f omi-oss/values-k0s.yaml \
  --set imageRegistry=$REG \
  --set ingress.loadBalancerIP=$LBIP \
  --set backend.encryptionSecret="$(openssl rand -hex 32)" \
  --set inference.openai.baseUrl=$LLM \
  --set inference.embeddings.baseUrl=$LLM \
  --set inference.embeddings.model=bge-m3
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

## 8. Verify

```bash
LBIP=192.168.100.190

# API health
curl -k https://$LBIP/v1/health                                  # {"status":"ok"}

# Login works (a real token is accepted, a bad one is rejected)
TOK=$(curl -k -s -X POST https://$LBIP/realms/omi/protocol/openid-connect/token \
  -d grant_type=password -d client_id=omi-test -d username=testuser -d password=testpass \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -k -o /dev/null -w 'valid  token -> %{http_code}\n' https://$LBIP/v1/users/people -H "Authorization: Bearer $TOK"     # 200
curl -k -o /dev/null -w 'bad    token -> %{http_code}\n' https://$LBIP/v1/users/people -H "Authorization: Bearer nope"     # 401

# Inference runs on the GPU inside the cluster:
kubectl -n omi exec deploy/backend -c backend -- \
  curl -fsS -X POST http://nllb:8080/v1/translate -H 'Content-Type: application/json' \
  -d '{"contents":["The on-prem cluster runs inference on the GPU."],"target_language_code":"it"}'
#   -> "Il cluster on-premise esegue inferenze sulla GPU."
kubectl -n omi get pods -l app.kubernetes.io/part-of=omi-oss | grep -E 'whisper|parakeet|diarizer|nllb'
```

---

## Notes & operations

- **What runs where.** In the cluster: the API, the datastore (MongoDB), cache (Valkey), vector store
  (Qdrant), object store (RustFS), push server (ntfy), login (Keycloak + Postgres), and the GPU inference
  servers (whisper + parakeet gateway, diarizer, nllb). Outside: only the chat LLM and the embeddings model.
- **One GPU, several models.** The device plugin advertises 4 GPU units (step 3c) so whisper, diarizer and
  nllb share the card. If you add engines or hit out-of-memory, raise VRAM / add a GPU, or lower the number
  of GPU services.
- **Turn an inference engine off** (e.g. keep only translation): `--set inference.inCluster.services.diarizer.enabled=false`.
- **Use external inference instead** (no in-cluster GPU): `--set inference.inCluster.enabled=false` and point
  `--set inference.openai.baseUrl=...` at your speech/translation endpoints.
- **Change something:** re-run the same `helm ... upgrade` (replace `install` with `upgrade`) with your flags.
- **Uninstall:** `helm uninstall omi -n omi`. Data volumes remain until you delete the PVCs / the cluster.
- **Production secrets.** The admin/database/S3 passwords above are throwaway dev values — set real ones (or
  supply a `backend-secret` Secret out-of-band and `--set secrets.create=false`) for a real deployment.
