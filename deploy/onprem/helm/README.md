# omi-oss — Helm chart (Kubernetes on-prem target)

The Helm mirror of the compose stack. Same images, same configuration philosophy — a deployment target
**in addition to** compose, not a replacement. One chart runs on **Kind** (local dev) and **k0s**
(production); only the `values-<env>.yaml` differ.

## Install — follow a manual (step-by-step, all prerequisites included)

- **[`MANUAL-dev-kind.md`](MANUAL-dev-kind.md)** — local development on your laptop (Kind). Full prod
  topology; inference (speech/translation) is external.
- **[`MANUAL-prod-k0s.md`](MANUAL-prod-k0s.md)** — production on a real GPU server (k0s). **Speech-to-text,
  diarization and translation run on the GPU inside the cluster**; only the chat LLM and embeddings are
  external. This is the on-prem default.

Both manuals start from a bare machine (install Kind/k0s, the GPU stack, the registry, everything) and end
with a working, verified stack.

## What runs where

Always in the cluster: the API (`backend`), datastore (`mongo`, a replica set), cache (`valkey`). Optional
profiles add the rest; the on-prem default (prod) turns them all on:

| Profile | Brings up | Notes |
|---|---|---|
| `chat` | Qdrant vector store | vector dim defaults to 1024 (= `bge-m3`); set `chat.vectorDim` for another model |
| `objstore` | RustFS (S3) + bucket-init | on-prem object storage |
| `push` | ntfy (UnifiedPush) | on-prem push |
| `ingress` | Envoy Gateway (Gateway API) | HTTPS entry point; a LoadBalancer IP (MetalLB) in prod |
| `auth` | Keycloak (+ Postgres) | OIDC login; issuer + TLS pinned to the entry-point IP |
| `inference` | wires an **external** OpenAI-compatible LLM + embeddings | operator-provided endpoint |
| `inference.inCluster` | STT (whisper + parakeet gateway), diarization, translation (nllb) as **GPU pods** | the on-prem default (prod); needs the NVIDIA device plugin |

Only the LLM and embeddings are external in the on-prem default; everything else — including STT,
diarization and translation — runs on your hardware.

## Key parameters (passed at install, never committed)

| `--set` | What |
|---|---|
| `imageRegistry=<host:port>` | registry the node pulls our images from (empty on Kind, which uses `kind load`) |
| `ingress.loadBalancerIP=<free LAN IP>` | the entry-point IP (MetalLB); the OIDC issuer + TLS SAN derive from it |
| `backend.encryptionSecret=<32-byte hex>` | `openssl rand -hex 32` |
| `inference.openai.baseUrl` / `inference.embeddings.baseUrl` / `.model` | your external LLM + embeddings |
| `inference.inCluster.modelsHostPath` | where the GPU model weights live on the node (has a sensible default) |

## Files

- `omi-oss/` — the chart. `values.yaml` (defaults) + `values-dev.yaml` (Kind) / `values-prod.yaml` (generic
  prod template) / `values-k0s.yaml` (concrete k0s prod).
- `kind-cluster.yaml` — declarative Kind cluster. `metallb-pool.yaml` (Kind) / `metallb-pool-k0s.yaml` (LAN).
- `nvidia-device-plugin-k0s.yaml` — GPU device plugin with time-slicing (share one GPU across inference pods).
- `gen-certs.sh` — self-signed TLS Secret for the HTTPS entry point.

## Notes

- **Mongo replica-set**: StatefulSet + PVC + an idempotent init Job (named per release revision so
  `helm upgrade` re-runs a fresh Job instead of patching an immutable one).
- **One GPU, several models**: the device plugin advertises multiple GPU units (time-slicing) so whisper,
  diarizer and nllb share one card. Tune the replica count in `nvidia-device-plugin-k0s.yaml`.
- **Storage**: the chart is provisioner-agnostic — every PVC sets only `storageClassName` + a size. Install a
  provisioner (the manuals use OpenEBS) and point `storageClassName` at it.
- **Turn inference engines on/off**: `--set inference.inCluster.services.<name>.enabled=false`, or switch the
  whole posture to external with `--set inference.inCluster.enabled=false`.
