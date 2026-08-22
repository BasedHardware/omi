# SELFHOST_NOTES — WP0: containerized offline baseline

Runbook + deviations log to **boot and serve the Omi backend offline**, with no cloud
dependencies. It is the first brick of the full-on-prem initiative (ADR-0001) and the seed of the
self-host deployment (later WPs add services to the same compose).

> Project docs location: the ADRs and the architecture brief live under `/work/omi/docs/`
> (outside the `src/omi` source tree). This file instead lives in the source because it is the
> operational runbook for the compose stack.

## Environments & compose matrix (ADR-0043 / ADR-0046)

This section is the single source of truth for how the environments differ; everything else (env
`.example` files, `run-*.sh`, the ADRs) defers here. The stack is composed from **two fragments** +
**four runnable postures** — **no `docker-compose.yml`, no override**; always pass
`-f compose.<posture>.yaml` (ADR-0043).

### The two fragments (never run directly)

| Fragment | Holds | Why |
|---|---|---|
| `compose.base.yaml` | **only what every posture shares** — `valkey` + `backend` + `api-proxy` (the backend's TLS front) + the `omi`/`edge` networks | so a posture never carries a backend it does not use |
| `compose.selfhost.yaml` | **every self-hosted backend** — `mongo` (default store) · `keycloak`+`kc-proxy` (auth) · `qdrant` (vector) · `rustfs` (object) · `ntfy`+`ntfy-proxy` (push) · `llm_gateway` + `parakeet`/`diarizer`/`nllb`/`whisper` (inference) + their named volumes | the on-prem replacements for the managed cloud services (ADR-0046) |

A proxy lives where its upstream lives: `api-proxy` fronts the backend → **base**; `kc-proxy`/`ntfy-proxy`
front keycloak/ntfy → **selfhost**.

### Where the image references come from

No `image:` in the fragments is written inline. Every posture passes two committed files to its
`include:` (long form, `env_file:`), and the fragments interpolate from them:

| File | Holds | Decision |
|---|---|---|
| `omi.oss.release.env` | `OMI_OSS_RELEASE` — the release of this stack; tags the five images **we** build | ADR-0054 |
| `omi.oss.release.pins` | one `OMI_OSS_*_IMAGE` per third-party image (mongo, valkey, nginx, keycloak, ntfy, qdrant, rustfs, postgres, minio/mc) | ADR-0055 |

Consequences worth knowing before editing:

- **Both are source, not operator config.** Bumping a pin or the release is a commit, not a local tweak.
  Per-installation choices (registry prefix, ports, host IP) stay in the gitignored `.env`.
- Each variable holds the **whole reference**, so a pin may be a tag, `tag@digest` or a bare digest —
  tightening one is a one-line change with nothing else to touch.
- The variables reach the **included** fragments only. A service declared in an entry file
  (`compose.prod.yaml` and friends) would not see them; a guard enforces that.
- The **shell environment wins** over these files, so the names are namespaced `OMI_OSS_*`. Do not export
  them to override a pin — edit the file.
- A build tags each of our images with the release **and** with `:latest`. `:latest` is a **dev alias**
  (Kind loads it by name); never push or deploy it — a mutable tag makes a later upgrade leave the pod
  spec unchanged, so the node keeps serving the cached image.
- Optional but recommended when building: `OMI_OSS_REVISION=$(git rev-parse HEAD)` — it stamps the commit
  into each image next to `omi.oss.release`, so `docker inspect` identifies exactly what is running.

Both files are covered by `check_oss_release.py` and `check_oss_image_parity.py` (manifest ids
`oss-release`, `oss-image-pins`), which also keep the Helm chart's values and `appVersion` in step.

### The four postures (runnable)

| Posture | Entrypoint | Includes | `omi` network | Backends |
|---|---|---|---|---|
| **on-prem prod** | `compose.prod.yaml` | base + **selfhost** | **bridged** — egress-capable; data sovereignty by **configuration** (every port wired to a local endpoint), not network isolation (ADR-0048) | self-hosted (see port matrix) |
| **dev** | `compose.dev.yaml` | base + selfhost (+ Firestore emulator opt-in `--profile firestore`) | egress — backend reaches **host** inference; API on `:8000` | self-hosted; `LOCAL_DEVELOPMENT` dev-auth available |
| **seed** | `compose.seed.yaml` | base + selfhost | egress | dev + **real OIDC**, drives the MELD 5-user seed (D35) |
| **cloud prod** | `compose.prod.cloud.yaml` | **base only** (no selfhost) | egress — reaches the cloud | **managed** (Firestore/Pinecone/Firebase/GCS) |
| test-unit | **no compose** — file-isolated pytest (ADR-0026) | — | none | in-memory fakes (`FakeDocumentStore`/`FakeObjectStore`/`FakeVectorStore`/`FakeAuthProvider`) / `mongomock` |
| test-e2e | `compose.dev.yaml` + `testing/e2e/` | base + selfhost | egress | live services via profiles (`run-*.sh`, rule 12) |

### Backend selection per posture (the neutral-port matrix, ADR-0004)

On-prem uses the self-hosted side; cloud uses the managed side. **The on-prem default is the
self-hosted stack (ADR-0046)** — Mongo is the default store, no profile needed for it.

| Port | on-prem (default) | cloud |
|---|---|---|
| storage | **Mongo** — `STORAGE_BACKEND=mongo` (ADR-0002), always on in `selfhost` | **Firestore** — `=firestore`, a **real** Firestore (ADR-0003) |
| auth | **OIDC/Keycloak** — `AUTH_BACKEND=oidc`, `--profile auth` | **Firebase** — `=firebase` |
| vector | **Qdrant** — `VECTOR_STORE_BACKEND=qdrant`, `--profile chat` | **Pinecone** — `=pinecone` |
| object | **S3/RustFS** — `OBJECT_STORE_BACKEND=s3`, `--profile objstore` | **GCS** — `=gcs` |
| push | **ntfy/UnifiedPush** — `PUSH_NOTIFICATION_BACKEND=unifiedpush`, `--profile push` | **FCM** — `=fcm` |

- **Firestore stays first-class + the reference adapter** (ADR-0003). The Firestore **emulator** is a
  dev-only convenience (`compose.dev.yaml --profile firestore` + `FIRESTORE_EMULATOR_HOST`), **never**
  in base/prod; the cloud posture points at a **real** Firestore.
- Profiles (`auth/chat/objstore/push/inference/firestore`) are orthogonal feature toggles, added
  per-run. `mongo` is no longer a profile — Mongo is the default and always on in `selfhost`.
- **Mongo indexes are provisioned automatically at backend startup** (`STORAGE_BACKEND=mongo`): the
  boot hook mirrors `firestore.indexes.json` into Mongo compound indexes (idempotent, best-effort —
  a slow/unready Mongo logs and does not block boot) so scoped queries/counts hit an index instead of
  a collection scan. To (re)run it out of band: `docker compose -f compose.<env>.yaml exec backend
  python -m scripts.reconcile_mongo_indexes` (`--dry-run` prints the plan).
- Because `compose.prod.cloud.yaml` includes **base only**, none of the self-hosted services are even
  *defined* there — the cloud posture **cannot start one by accident**, even with `--profile`.

### Quick start — the two prod commands

```bash
cd deploy/onprem
# env files (gitignored) + a real secret (both postures share backend.env.base):
for e in base prod; do cp backend.env.$e.example backend.env.$e; done
sed -i "s/^ENCRYPTION_SECRET=.*/ENCRYPTION_SECRET=$(openssl rand -hex 32)/" backend.env.base

# ── PROD · on-prem self-hosted (bridged; data sovereignty by config, ADR-0048) ─
#   Mongo starts by default; profiles add TLS+OIDC (auth), vector (chat), object (objstore), push.
docker compose -f compose.prod.yaml --profile auth --profile chat --profile objstore --profile push up -d --build
docker compose -f compose.prod.yaml ps            # services must become 'healthy'

# ── PROD · cloud (managed Firestore/Pinecone/Firebase/GCS; needs egress + creds) ──
cp backend.env.prod.cloud.example backend.env.prod.cloud   # fill real creds; mount the GCP SA json
#   base only (backend + valkey + api-proxy TLS front); no self-hosted service is defined here.
docker compose -f compose.prod.cloud.yaml --profile auth up -d --build
```
The env `.example` templates are layered `backend.env.base` + `backend.env.<posture>`; copy the ones
for the posture you run (`dev`/`seed` too when needed). See the port matrix above for the backend
env each posture sets.

## What each posture contains

**`base`** — the three services every posture shares:

| Service | Image / build | Role |
|---|---|---|
| `backend` | built from `backend/Dockerfile` (base image override, see below) | FastAPI `main:app`, uvicorn :8080 |
| `valkey` | `valkey/valkey:8-alpine` | cache/queue (wire-compatible with `redis-py`) |
| `api-proxy` | `nginx:stable-alpine` (`--profile auth`) | TLS front for the backend API (device trusts the self-signed CA) |

**`selfhost`** (on-prem prod/dev, ADR-0046) adds the self-hosted backends, each behind its profile
except Mongo (default, always on): `mongo` · `keycloak`+`kc-proxy` (`auth`) · `qdrant` (`chat`) ·
`rustfs` (`objstore`) · `ntfy`+`ntfy-proxy` (`push`) · `llm_gateway`+`parakeet`/`diarizer`/`nllb`/`whisper`
(`chat`/`inference`).

**cloud** (`compose.prod.cloud.yaml`) adds **nothing** — `base` only, with the backend pointed at the
managed Firestore/Pinecone/Firebase/GCS via `backend.env.prod.cloud`.

The **Firestore emulator** is a **dev-only** service (`compose.dev.yaml --profile firestore`, Firestore
:8085 + Auth :9099) for exercising the reference adapter locally; it is never in base/prod (ADR-0046).

## Data durability (persistent volumes)

Every stateful backend that can hold on-prem data survives `docker compose down`/`up` on a **named
volume** (compose.selfhost.yaml `volumes:` block — they live with the self-hosted services, ADR-0046):
`mongo-data:/data/db` (ADR-0002 datastore),
`rustfs-data:/data` (ADR-0032 object store, `RUSTFS_VOLUMES=/data`), `qdrant-storage` (ADR-0033
vectors), `keycloak-data:/opt/keycloak/data`, `ntfy-cache:/var/cache/ntfy` (ADR-0011 push server —
`NTFY_CACHE_FILE=/var/cache/ntfy/cache.db` SQLite; without it ntfy caches messages in memory only and
a restart drops any notification a device has not yet fetched). A plain `down` keeps them; only `down -v` wipes them
(and would also drop the pre-provisioned `inference-models` weights, which have no egress to refetch
— avoid `-v` on this project).

Keycloak runs in **production mode** (`start`, not `start-dev`) with a persistent `dev-file` H2 DB on
`keycloak-data`, so realm state — including the imported `omi-backend-admin` service-account client —
lives across restarts. `--import-realm` seeds a **fresh** volume from `keycloak/omi-realm.json` — a **runtime file**,
gitignored, that you produce by copying the example for this environment (ADR-0082), exactly like the env
files:

```bash
cp keycloak/omi-realm.example.json      keycloak/omi-realm.json   # prod: no test principals
cp keycloak/omi-realm.dev.example.json  keycloak/omi-realm.json   # dev/seed: + omi-test client, testuser
```

**The same file feeds Helm** — copy it to `helm/omi-oss/files/omi-realm.json` before `helm install`. If it
is missing, both consumers refuse loudly: the chart `fail`s the render with this instruction, and compose
errors on the bind (`create_host_path: false`) instead of creating an empty directory that Keycloak
imports nothing from.

Why it is not committed: the chart used to carry its own copy — of the **dev** realm — so the install we
document as production came up with `omi-test`/`testuser`, and `testuser`/`testpass` returned a token on
the live release (BACKLOG L47). While the executed file lives in the repository, "which realm is live" is
a property of the repo instead of the installation. On an existing volume KC logs
"Realm 'omi' already exists. Import skipped" and keeps the persisted realm. **To re-import after
editing the realm JSON**, remove just that volume:
`docker compose stop keycloak && docker volume rm <project>_keycloak-data && docker compose up -d keycloak`
(the realm JSON description fields must stay ≤255 chars — the H2 `CLIENT.DESCRIPTION` column limit).

## Prerequisites

Only **Docker** (with Compose v2) on the host. No java/node/redis/firebase-CLI to install:
everything is in the containers. The **build** needs internet access (see Deviations #2); the
**runtime** does not.

## Usage

The two prod up-commands are in **Quick start** above (on-prem self-hosted / cloud). Day-to-day:

```bash
cd deploy/onprem
docker compose -f compose.prod.yaml ps            # services must become 'healthy'
docker compose -f compose.prod.yaml logs -f backend
docker compose -f compose.prod.yaml down          # keeps volumes; add -v to WIPE data (see durability)
```
Swap `compose.prod.yaml` for `compose.dev.yaml` / `compose.seed.yaml` / `compose.prod.cloud.yaml` for
the other postures. Always pass the same `--profile` flags you brought the stack up with.

## Verification (WP0 acceptance)

The `omi` network is **bridged** (egress-capable, ADR-0048), but the backend does not publish a host
port — only the edge proxies do — so test the backend from **inside** the containers.

```bash
# 1) the backend responds (no auth)
docker compose -f compose.prod.yaml exec -T backend curl -fsS http://localhost:8080/v1/health
#    expected: {"status":"ok"}

# 2) end-to-end auth + store round-trip (dev-auth path; needs LOCAL_DEVELOPMENT=true, i.e. dev/seed)
docker compose -f compose.dev.yaml exec -T backend curl -sS -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/v3/memories -H 'Authorization: Bearer dev-token'
#    expected: 200 (LOCAL_DEVELOPMENT=true -> Bearer dev-token = uid 123; reads from the store — Mongo
#    by default, ADR-0046). In real prod (LOCAL_DEVELOPMENT=false) auth is OIDC — use a real token.
docker compose -f compose.prod.yaml exec -T backend curl -sS -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/v3/memories
#    expected: 401 (auth enforced)

# 3) DATA SOVEREIGNTY (by configuration, not network isolation — ADR-0048): the omi network is BRIDGED, so
#    the backend CAN reach the internet; sovereignty holds because every port is wired to a LOCAL endpoint.
#    Verify no cloud endpoint/key is configured (STORAGE_BACKEND=mongo, OBJECT_STORE_BACKEND=s3,
#    VECTOR_STORE_BACKEND=qdrant, AUTH_BACKEND=oidc, *_BASE_URL/GATEWAY_URL -> local service names):
docker compose -f compose.prod.yaml exec -T backend sh -c 'env | grep -iE "STORAGE_BACKEND|OBJECT_STORE_BACKEND|VECTOR_STORE_BACKEND|AUTH_BACKEND|BASE_URL|GATEWAY_URL"'
#    expected: backends = mongo/s3/qdrant/oidc; URLs point at local service names (llm_gateway, keycloak, ...).
#    For a HARD air-gap, add `internal: true` to the omi network explicitly — ADR-0048 dropped it as the
#    default (bridged) but the operator can opt back in; models are then pre-provisioned (see Local inference).
```

### Curl from the host (dev convenience, accepts egress)

The prod posture publishes no backend port (only the edge proxies do). To poke the endpoints from the host:

```bash
docker compose -f compose.dev.yaml up -d
curl -fsS http://localhost:8000/v1/health
```

## Deviations from the happy path (log)

1. **Private base image -> public.** `backend/Dockerfile` uses
   `gcr.io/based-hardware-dev/python:3.11-slim-forky` (private GCR, not pullable). The compose
   overrides the build-arg `PYTHON_BASE_IMAGE=python:3.11-slim`. Risk: the "forky" image may carry
   patches/system-deps not replicated; the runtime stage installs `ffmpeg curl libjemalloc2`
   anyway. If build/boot surfaces missing deps, add them or authenticate to GCR.
2. **`liblc3` compiled from git at build-time.** The Dockerfile does a `git clone` of google/liblc3
   and builds it -> the `docker build` needs internet. Acceptable: WP0 hermeticity is at
   **runtime**, not at build-time.
3. **Firestore emulator.** No image exists in the repo: built here from `node:22-trixie` + JDK 21 +
   `firebase-tools`. The repo `firebase.json` pins the emulators to `127.0.0.1` (unreachable
   between containers) -> we use `firebase.compose.json` with host `0.0.0.0`. The emulator jar is
   **pre-fetched at build-time** (`firebase setup:emulators:firestore`) so runtime needs no egress.
   Emulator UI disabled (avoids extra downloads).
4. **Valkey instead of Redis.** On-prem choice (BSD/Linux Foundation); wire-compatible, no backend
   code change (`redis-py` speaks the same protocol). `REDIS_DB_HOST=valkey`.
5. **Pusher and Typesense excluded.** Not needed for `/v1/health` or for boot. **Known
   consequence:** without Pusher, conversations would stay `in_progress` (finalization pipeline) —
   out of WP0 scope, added in a later WP.
6. **Temp dirs.** `main.py` does not create `_temp/_samples/_segments/_speech_profiles`; the
   `backend` service creates them in its entrypoint (`command:`) before uvicorn.
7. **Health path.** The brief mentioned `/health`: it does not exist in the backend; the real
   no-auth endpoint is **`/v1/health`** (`backend/routers/other.py`).

## Local inference (WP5, ADR-0035)

Inference is **configured, not bundled**. The backend points at endpoints the operator runs —
often a dedicated GPU host — instead of shipping an LLM as a prod service. Two groups:

**LLM + embeddings — one OpenAI-compatible endpoint (external).** Ollama/vLLM/TEI serve both
`/v1/chat/completions` and `/v1/embeddings`, so a single server covers both — but they reach it
differently: **embeddings go direct** from the backend; **chat goes through the on-prem
`llm_gateway` service** (the backend speaks lane ids, not model names — see "Chat LLM (on-prem)"
below). Wire it in `backend.env`:

```
# chat — through the on-prem `llm_gateway` service (NOT the endpoint directly; see "Chat LLM
# (on-prem)" below). The endpoint URL itself goes in llm_gateway.env (OPENAI_BASE_URL).
OMI_LLM_GATEWAY_FEATURE_MODE=gateway
OMI_LLM_GATEWAY_URL=http://llm_gateway:9080
OMI_LLM_GATEWAY_SERVICE_TOKEN=<same value as llm_gateway.env>
OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE=true          # OMI_ENV_STAGE=selfhost is a real runtime
# embeddings — direct (they do NOT go through the gateway; the one hard-cloud gap, now pointable)
OMI_EMBEDDINGS_BASE_URL=http://<ollama-host>:11434/v1
OMI_EMBEDDINGS_MODEL=nomic-embed-text
QDRANT_VECTOR_DIM=768        # MUST equal the embedding model's dimension
```

The embedding dimension must match `QDRANT_VECTOR_DIM`: `nomic-embed-text`=768,
`mxbai-embed-large`/`bge-m3`=1024, OpenAI `text-embedding-3-large`=3072. Ollama does not serve a
3072-dim model — pick one and set the dim to match, on a **fresh** vector store (existing 3072-dim
vectors are incompatible). VAD needs nothing: Silero ONNX runs in-process, bundled in the backend image.

Verify the embeddings path against a real endpoint (loopback under `--network host`, allowed by the
hermetic guard; skips when the env is unset, so it is CI-safe):

```
docker run --rm --network host \
  -e OMI_EMBEDDINGS_BASE_URL=http://127.0.0.1:11434/v1 \
  -e OMI_EMBEDDINGS_MODEL=bge-m3 -e OMI_EMBEDDINGS_EXPECTED_DIM=1024 \
  -v $PWD/../..:/repo -w /repo/backend omi-oss-backend-test \
  python -m pytest tests/contract/test_embeddings_live_contract.py -q -p no:cacheprovider
# expected: 3 passed  (real vector, correct dim, deterministic, no OpenAI/Google egress)
```

### Chat LLM (on-prem) — via the `llm_gateway` service (D32)

The mobile "Ask Omi" chat (`POST /v2/messages`) does **not** call your Ollama/vLLM directly: the
backend sends an `omi:auto:*` **lane** id, and only the in-repo **`llm_gateway`** service resolves the
lane to a concrete model and forwards OpenAI-compatibly to your endpoint. So on-prem chat needs the
gateway running — pointing `OMI_LLM_GATEWAY_URL` straight at Ollama does **not** work (Ollama has no
model named `omi:auto:chat-agent`). The gateway is a compose service (`profile: chat`) that reuses the
backend image; the LLM itself stays operator-provided (ADR-0035, not bundled).

Setup:
```bash
cd deploy/onprem
cp llm_gateway.env.example llm_gateway.env      # set OPENAI_BASE_URL (your Ollama/vLLM /v1) + a token
TOK=$(openssl rand -hex 24)
sed -i "s|^OMI_LLM_GATEWAY_SERVICE_TOKEN=.*|OMI_LLM_GATEWAY_SERVICE_TOKEN=$TOK|" llm_gateway.env
# backend.env: same token + the gateway wiring (see backend.env.dev.example "chat LLM gateway"):
#   OMI_LLM_GATEWAY_FEATURE_MODE=gateway · OMI_LLM_GATEWAY_URL=http://llm_gateway:9080 ·
#   OMI_LLM_GATEWAY_SERVICE_TOKEN=$TOK · OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE=true
# Pin the chat model to one your endpoint serves (all features -> one local model):
#   deploy/onprem/helm/omi-oss/files/generated_route_overrides.yaml   (default: qwen2.5:14b)
docker compose -f compose.dev.yaml --profile chat up -d
```

Three on-prem requirements the gateway wiring encodes (each was a real failure the E2E caught):
1. **the `llm_gateway` service must run** — `OMI_LLM_GATEWAY_URL` points at it (`:9080`), not at Ollama;
2. **`OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE=true`** — gateway mode is blocked outside dev, and
   `OMI_ENV_STAGE=selfhost` is a real (non-dev) runtime — see ADR-0058 for why that value;
3. **tiktoken encodings are baked into the backend image** (build-time) so the chat token-budget step
   needs no runtime download (would hit `openaipublic.blob.core.windows.net` → fails no-egress).

Reproducible live E2E (declarative, no ad-hoc `docker run`) — brings the profile up, sends a real
chat message, and asserts a streamed answer from the local model:
```bash
deploy/onprem/run-chat-e2e.sh
# expected: PASS — real streamed answer from your local model (LLM served by llm_gateway, no cloud call).
# (Uses LOCAL_DEVELOPMENT=true dev-auth, Bearer dev -> uid 123, for a focused chat smoke test.)
```

Full on-prem semantic search round-trip (embeddings + vector store together — Qdrant on loopback):

```
docker run -d --name qdrant --network host qdrant/qdrant:latest    # 127.0.0.1:6333
docker run --rm --network host \
  -e OMI_EMBEDDINGS_BASE_URL=http://127.0.0.1:11434/v1 -e OMI_EMBEDDINGS_MODEL=bge-m3 \
  -e VECTOR_STORE_BACKEND=qdrant -e QDRANT_URL=http://127.0.0.1:6333 -e QDRANT_VECTOR_DIM=1024 \
  -v $PWD/../..:/repo -w /repo/backend omi-oss-backend-test \
  python -m pytest tests/contract/test_onprem_search_roundtrip.py -q -p no:cacheprovider
# expected: 5 passed  (embed -> upsert -> query ranks the right doc first; metadata round-trips)
```

Live translation through the backend path against a running NLLB server (CTranslate2). Provision the
model into the volume, run the server (CPU shown; drop `CT2_DEVICE` for GPU), then test:

```
# one-time: convert facebook/nllb-200-distilled-600M -> CT2 int8 into $MODELS/nllb-200-distilled-600M-ct2-int8
docker run -d --name nllb --network host -e CT2_DEVICE=cpu -e CT2_COMPUTE_TYPE=int8 \
  -e NLLB_MODEL_DIR=/models/nllb-200-distilled-600M-ct2-int8 -v $MODELS:/models omi-nllb:test
docker run --rm --network host \
  -e HOSTED_TRANSLATION_API_URL=http://127.0.0.1:8080 -e TRANSLATION_SERVICE_MODELS=nllb \
  -v $PWD/../..:/repo -w /repo/backend omi-oss-backend-test \
  python -m pytest tests/contract/test_translation_nllb_live_contract.py -q -p no:cacheprovider
# expected: 4 passed  (en->it/fr/es real translations + en->it->en round-trip via TranslationService)
```

Live speaker embedding through the backend path against a running diarizer. The pyannote models are
gated: use an `HUGGINGFACE_TOKEN` whose account has accepted the licenses of `pyannote/embedding`,
`pyannote/wespeaker-voxceleb-resnet34-LM` and `pyannote/speaker-diarization-community-1` (visit each
model page once and click *Agree and access*). Then:

```
# Build the slim on-prem image (skips the redundant system CUDA — see "Diarizer image is slimmed" below):
docker build -f backend/diarizer/Dockerfile -t omi-oss-diarizer:latest \
  --build-arg PYTHON_BASE_IMAGE=python:3.11-slim --build-arg INSTALL_SYSTEM_CUDA=0 .
docker run -d --name diarizer --network host --device nvidia.com/gpu=all \
  -e HUGGINGFACE_TOKEN=hf_xxx -e HF_HOME=/models/hf -v $MODELS:/models omi-oss-diarizer:latest
docker run --rm --network host -e HOSTED_SPEAKER_EMBEDDING_API_URL=http://127.0.0.1:8080 \
  -v $PWD/../..:/repo -w /repo/backend omi-oss-backend-test \
  python -m pytest tests/contract/test_speaker_embedding_live_contract.py -q -p no:cacheprovider
# expected: 2 passed  (real 256-dim wespeaker embedding, deterministic, discriminates two signals)
# verified 2026-08-03 on the slim image, RTX 5060 Ti (Blackwell sm_120): 2 passed.
```

Live STT (Parakeet / NeMo) — verified on an RTX 5060 Ti (Blackwell sm_120) with driver 610 + the
NeMo 26.02 base (CUDA 12.8). The server needs two required env vars (`PARAKEET_STREAM_CAPACITY`,
`PARAKEET_STREAM_ALLOCATION_PERCENT`) and loads a batch model (prerecorded) plus, if configured, a
streaming model (live `/v3/stream`):

```
docker run -d --name parakeet --network host --device nvidia.com/gpu=all \
  -e PARAKEET_MODEL=nvidia/parakeet-tdt-0.6b-v3 \
  -e PARAKEET_STREAM_MODEL=nvidia/parakeet-rnnt-1.1b \
  -e PARAKEET_STREAM_CAPACITY=4 -e PARAKEET_STREAM_ALLOCATION_PERCENT=100 \
  -e HF_HOME=/models/hf -v $MODELS:/models omi-parakeet:test
# batch tdt-0.6b (~2.5GB) + stream rnnt-1.1b (~4.5GB) load to GPU (~6.4GB total on 16GB — fits).
```

Official quality gates against the running server (WER on LibriSpeech, DER on synthetic 2-speaker):

```
# WER: pre-download the tarball outside the hermetic guard, then run (transcribes over loopback)
python3 -c "import urllib.request;urllib.request.urlretrieve('https://www.openslr.org/resources/12/test-clean.tar.gz','$CACHE/test-clean.tar.gz')"
docker run --rm --network host -e PARAKEET_URL=http://127.0.0.1:8080 -e LIBRISPEECH_CACHE=/cache \
  -e WER_MAX_SAMPLES=10 -v $CACHE:/cache -v $PWD/../..:/repo -w /repo/backend omi-oss-backend-test \
  python -m pytest tests/container/test_parakeet_wer_gate.py -q -p no:cacheprovider
# expected: 4 passed  (aggregate WER 13.0% <= 15% on 10 LibriSpeech samples, ~0.1s each)

# DER: runs inside the parakeet image (loads its own model — stop the server first to free the GPU)
docker run --rm --device nvidia.com/gpu=all -e PARAKEET_MODEL=nvidia/parakeet-tdt-0.6b-v3 \
  -e HF_HOME=/models/hf -e PARAKEET_STREAM_CAPACITY=4 -e PARAKEET_STREAM_ALLOCATION_PERCENT=100 \
  -v $MODELS:/models omi-parakeet:test python -m pytest tests/container/test_parakeet_der_gate.py -q
# expected: 2 passed  (DER 0.0% <= 12% on a 2-speaker mix)
```

### ⚠️ Live STT provider policy — the multilingual gap (WP5 finding)

The default **live** STT primary is **Modulate "Velma-2", a cloud SaaS** (multilingual, unlimited
concurrency); Parakeet is the bounded self-hosted secondary. Offline, Modulate is unreachable, so set
`STT_SERVICE_MODELS=parakeet` (+ `STT_PRERECORDED_MODEL=parakeet`) to force the self-hosted path.

**But the charts' streaming model `nvidia/parakeet-rnnt-1.1b` is English-only** (policy:
`PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[...] = {'en'}`). With Omi's default multilingual live mode, a
non-`multi`-incapable request resolves to `multi`, which the en-only Parakeet stream model cannot
serve → selection falls back to Modulate → `transcription_service_unavailable`. Today a pure-Parakeet
on-prem deployment serves live STT **only in single-language English** (user pref
`transcription_preferences.single_language_mode=true`, or `onboarding_mode`).

**On-prem streaming/PTT Parakeet is English-only today.** `config/stt_provider_policy.py` fixes the
model per serving surface (`PARAKEET_MODEL_BY_SURFACE`): **streaming** and **PTT** use
`nvidia/parakeet-rnnt-1.1b` (`PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL` = `{en}`), while **prerecorded**
uses `nvidia/parakeet-tdt-0.6b-v3` (25 languages). `parakeet_supports_language(surface, language)` reads
that fixed map — there is **no** `PARAKEET_STREAM_MODEL` env, no `APPROVED_STREAMING_PARAKEET_MODELS`,
and no per-deployment streaming-model override. So on-prem live streaming/PTT serves `en` only; a
non-English live session falls back to Deepgram-self-hosted (or the configured cloud STT) per the
policy, and prerecorded transcription is what serves the other 25 languages.

> Planned (NOT wired yet): the multilingual model `nvidia/parakeet-1-1b-rnnt-multilingual` is no longer
> referenced by any Dockerfile (the early NIM-sidecar sketch that named it was dropped in the slim
> consolidation — the on-prem posture forwards to whisper instead, ADR-0037). Making live streaming
> multilingual would require registering it in `stt_provider_policy.py` (a supported-languages entry + a
> deploy-time surface override) and the matching NIM deployment — neither exists at this revision.

### Full live pipeline E2E (all inference services + backend + pusher)

The pre-existing `tests/integration/test_speaker_id_real_embedding.py` exercises the whole live path:
real audio → WS `/v4/listen` → streaming STT (Parakeet) → diarization → speaker embedding → cosine
match → speaker suggestions. Bring up the stack on the host network (backend:10151, pusher:10152,
parakeet:8080 with a stream model, diarizer:18881, firestore-emulator, valkey), seed the dev user with
`transcription_preferences.single_language_mode=true` (until multilingual lands), provide a speech WAV
at `pretrained_models/snakers4_silero-vad_master/tests/data/test.wav`, then run with
`STT_SERVICE_MODELS=parakeet`. Verified: **11/11 passed** (6 embedding-API + 3 pipeline + 2 chaos).

**STT / diarization / translation — the in-repo GPU servers (optional `inference` profile).**
These build from `backend/{parakeet,diarizer,nllb_translation}/Dockerfile`:

```
docker compose -f compose.prod.yaml --profile inference up -d --build
```

Once the profile is up (and model weights are provisioned into the volume), run all three
backend live tests against the running compose services in one shot — the reproducible,
committed form of the per-service recipes below:

```
deploy/onprem/run-inference-live-tests.sh            # diarizer + nllb + whisper
# expected: diarizer PASS · nllb PASS · whisper PASS
```

Requirements and gotchas:
- **GPU passthrough is a container-runtime concern, not just a driver.** A working `nvidia-smi` on
  the host is NOT enough: Docker needs the **NVIDIA Container Toolkit** installed, or `--gpus all` /
  the compose `deploy.resources` reservation fail with *"failed to discover GPU vendor from CDI: no
  known GPU vendor found"*. The toolkit is required either way; two ways to wire it in:
  - **CDI (recommended, Docker ≥25 — no daemon restart):** `sudo apt-get install nvidia-container-toolkit`
    then `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`, and run containers with
    `--device nvidia.com/gpu=all` (compose: `devices: [nvidia.com/gpu=all]` under `deploy.resources`).
  - **Legacy runtime:** `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`,
    then `--gpus all`. The daemon restart stops running containers, so prefer CDI.
  Verified here on Ubuntu 24.04 + driver 610 + RTX 5060 Ti (Blackwell sm_120): NLLB (CTranslate2) and
  the diarizer (pyannote) both run on GPU via CDI. NeMo 26.02 ships CUDA 12.8, which supports sm_120.
- **CPU fallback for a smoke test:** NLLB and the diarizer both run CPU-only — set `CT2_DEVICE=cpu`
  (NLLB) or `CUDA_VISIBLE_DEVICES=""` (diarizer). Useful to validate wiring on a host without GPU
  passthrough; production STT/diarization/translation want the GPU.
- **Parakeet base is on NGC:** `docker login nvcr.io` (free NVIDIA NGC account) before building —
  base `nvcr.io/nvidia/nemo:26.02`. NLLB uses a public CUDA base; diarizer's private base is
  overridden to `python:3.11-slim` via the `PYTHON_BASE_IMAGE` build-arg (already set in compose).
- **Diarizer image is slimmed on-prem via `INSTALL_SYSTEM_CUDA=0`** (build-arg, already set in
  compose). Upstream's Dockerfile installs a ~3GB CUDA 13.2 local-installer .deb on top of the base,
  but `torch==2.8.0`'s wheels already bundle the CUDA **12.8** runtime libraries (the `nvidia-*-cu12`
  packages in `requirements.txt`); the only host-side dependency is the NVIDIA driver, injected at
  runtime via CDI. Skipping the system install halves the image (**~24.8GB → ~12.5GB**) with no loss
  of function. cu12.8 is exactly the version torch needs for Blackwell (sm_120), so no system CUDA
  13.2 is involved either way. `INSTALL_SYSTEM_CUDA=1` (the default) reproduces upstream's image
  byte-for-byte. Verified here: `torch 2.8.0+cu128`, `torch.cuda.is_available()` True on the RTX
  5060 Ti (capability (12,0)), and the speaker-embedding live contract below passes on the slim image.
- **Models are pre-provisioned, not downloaded at runtime.** This keeps the inference services offline-
  capable regardless of network posture (the `omi` network is bridged by default, ADR-0048; an operator
  wanting a hard air-gap sets `internal: true` explicitly, and pre-provisioning is what makes that work).
  Populate the `inference-models` volume before the first `--profile inference` run:
  - **NLLB:** convert `facebook/nllb-200-distilled-600M` to CTranslate2 int8 and place it at
    `nllb-200-distilled-600M-ct2-int8/` inside the volume (matches `NLLB_MODEL_DIR`). Serving then
    makes **zero** external calls.
  - **Parakeet / diarizer / whisper:** pre-populate the HuggingFace cache (`HF_HOME=/models/hf` in the
    volume) with the model weights, e.g. a one-time `docker run` with network before switching to the
    internal network. Otherwise first startup fails (cannot reach HuggingFace). Whisper pulls
    `Systran/faster-whisper-large-v3` (public, no gating) on first run.
- **STT engine (ADR-0037): the default `parakeet` service is a thin NIM gateway to `whisper`**
  (multilingual, 99 languages, commodity GPU incl. sm_120) — `PARAKEET_INFERENCE_MODE=nim` loads no
  NeMo model and needs no GPU. The high-performance datacenter path (Parakeet on NeMo) is the
  documented alternative on the `parakeet` service (see the header of that service in the compose and
  `backend.env.dev.example`). Verified 2026-08-03 on the RTX 5060 Ti: an Italian FLEURS clip →
  `parakeet` gateway → `whisper` → correct Italian transcription with auto-detected language, via
  `deploy/onprem/run-inference-live-tests.sh` (diarizer PASS · nllb PASS · whisper PASS).
- Point the backend at them in `backend.env`: `HOSTED_PARAKEET_API_URL=http://parakeet:8080`,
  `HOSTED_SPEAKER_EMBEDDING_API_URL=http://diarizer:8080`,
  `HOSTED_TRANSLATION_API_URL=http://nllb:8080` + `TRANSLATION_SERVICE_MODELS=nllb`.
- **Model provisioning is a STEP, never a runtime fetch** (ADR-0076). The services now declare
  `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` (and `TORCH_HOME=/models/torch` on parakeet), so a missing
  weight fails immediately and says so instead of waiting out a DNS timeout on the internal network. Two
  things fetched at runtime before this:
  - `diarizer/embedding.py` calls `Model.from_pretrained("pyannote/embedding")` at **module level**, so a
    missing cache is a container that never starts (loud, but only after a timeout);
  - `parakeet/stream_handler.py` fetches the Silero VAD with `torch.hub.load` — a **github clone** the first
    time a stream needs it — and swallowed the failure. A stream without the VAD treats **every chunk as
    speech**, so silence-based endpointing is off; `parakeet_vad_unavailable_total` counts it and the log
    now says what it costs.

  Seed the caches once, with network, into the `inference-models` volume (the k8s side already does this
  with the `inference-models-provision-job`). For the VAD specifically:

  ```bash
  docker compose -f compose.prod.yaml --profile inference run --rm --no-deps \
    -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 parakeet \
    python3 -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)"
  ```
  That writes into `TORCH_HOME=/models/torch` on the volume, so every later start finds it offline.

## LLM route coverage: an omission is a vendor route (ADR-0067)

`deploy/onprem/helm/omi-oss/files/generated_route_overrides.yaml` is mounted over the gateway's own copy and pins
each feature to the model your `OPENAI_BASE_URL` serves. **What an omission means there is the thing to
know:** the gateway synthesises a lane for *every* configured feature, and a feature with no entry keeps its
**cloud** model and provider from the QoS table. A missing line is not "unconfigured" — it is a live route
to a vendor through our own gateway, stopped only by the absence of that vendor's credentials.

Measured here on 2026-08-21: **8 of 45** features had no entry — `app_integration`, `followup`,
`onboarding`, `session_titles`, `translation`, `trends` (gemini), `wrapped_analysis` (openrouter),
`web_search` (perplexity). `translation` carries transcript text. The earlier reading, "37 of 37 covered",
compared our file against *upstream's* override file, which cannot show a lane neither file mentions.

**The list is declared ONCE, and that is recent** (ADR-0081). It used to be declared twice: the chart did
not mount this file, it regenerated its ConfigMap from a hand-kept `chat.llmGateway.features` in
`values.yaml`, next to a comment asking for the two to be kept in step. They were not — that pair drifted
from 44 to 4, and measured on the live k0s release **41 of 45 lanes did not serve** (33 x 400
`provider_invalid_request` from a CLOUD model name our endpoint does not serve, 8 x 503 `invalid_config`
from a vendor provider with no credentials). The four that worked were exactly the chat lanes, which is why
the chat E2E passed while memories, daily summaries, notifications and translation did not.

Now `templates/llm-gateway.yaml` renders the ConfigMap **from this file** with `.Files.Get`, which is why
the file lives inside the chart: `.Files.Get` cannot reach outside one, so compose reaches in instead. The
chart still decides the **model** (`chat.llmGateway.model` replaces whatever the file pins), so a k8s
operator serving something else does not have to edit a shared file; the lanes and their
`request_timeout_ms` come from the file. **To add or remove a lane, edit this one file.**

`check_oss_llm_gateway_route_coverage.py` ratchets all of it: coverage against the configured-feature set,
the `provider:` of every covered entry (a coverage count means nothing if an entry can name gemini), and
that the list stays declared once — it fails if `chat.llmGateway.features`/`requestTimeoutMsByFeature`
reappear in the values, or if the template stops reading the file (which would render an EMPTY ConfigMap
and put every feature back on its cloud model). `web_search` is the one written-off lane, with its reason
in the guard's baseline: it is a search product, and a local chat model would answer it with invented
results and a fabricated "Sources:" section.

Verified live on both targets after the unification (2026-08-22), with the lane probe below: **44 x 200 and
`web_search` alone at 503**, on k0s (`helm upgrade` -> 44 lanes in the ConfigMap, gateway pod rolled) and on
compose (`docker compose -f compose.prod.yaml up -d llm_gateway`, bind-mount repointed).

**Verify every lane against the live gateway** — the check the guard cannot do, because it needs the network.
Write the probe to a file and pipe it in (the caller header is required: 403 without it):

```bash
cat > /tmp/probe_lanes.py <<'PROBE'
import os, json, urllib.request
from utils.llm.model_config import get_all_configured_features
from utils.llm.clients import feature_auto_lane_id
base, tok = os.environ['OMI_LLM_GATEWAY_URL'], os.environ['OMI_LLM_GATEWAY_SERVICE_TOKEN']
for f in sorted(get_all_configured_features()):
    body = json.dumps({"model": feature_auto_lane_id(f),
                       "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}).encode()
    req = urllib.request.Request(f'{base}/v1/chat/completions', data=body, headers={
        'Content-Type': 'application/json', 'Authorization': f'Bearer {tok}',
        'x-omi-service-caller': 'backend'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            print(f'{r.status} {f}')
    except urllib.error.HTTPError as e:
        print(f'{e.code} {f}  <-- {e.read()[:100].decode()}')
PROBE
docker compose -f compose.prod.yaml exec -T backend /opt/venv/bin/python - < /tmp/probe_lanes.py
```

Expected today: **44 x 200**, and `503 invalid_config` for `web_search` alone. A 200 whose body carries
`"model": "omi:auto:<feature>"` and `fp_ollama` in `system_fingerprint` is proof the lane was served locally.

**Run it on the k8s target too** — this is the check that found the drift, and it needs the pod, not the
chart:

```bash
POD=$(kubectl -n omi get pods -l app.kubernetes.io/component=backend -o jsonpath='{.items[0].metadata.name}')
kubectl -n omi exec -i $POD -c backend -- /opt/venv/bin/python - < /tmp/probe_lanes.py
```

And remember the two halves of a k0s redeploy: `helm upgrade` picks up chart and values changes, but the pod
spec is unchanged when the image tag is, so a code change also needs the image pushed and
`kubectl -n omi rollout restart deployment/backend`. See `helm/MANUAL-prod-k0s.md` Step 4c.

## Object-store access: signed for the user's audio, public only for marketplace assets (ADR-0087)

Ten producers in `utils/other/storage.py` returned a `public_url`. Measured on the pinned RustFS, **all
ten were broken** — the per-object ACL is not honoured (an object uploaded `public-read` answers **403**
to an anonymous GET, on `1.0.0-beta.12` and `1.0.0-rc.3` alike) and the buckets carried no policy.

The fix was not "make them work". Five of the ten returned an unauthenticated link for **the user's own
audio** — their enrolled voice, their conversation recordings, the file being synced — and those links
DO work on GCS, where the buckets are public by project policy. Making them work here would have created
the exposure instead of closing it.

| group | producers | how the URL is minted now |
|---|---|---|
| user audio | speech profile, post-processing, sd-card, conversation recording, syncing temporal | **signed, 60 min** (`presign_get`) |
| marketplace assets | app logo, app thumbnail | **public**, via a bucket policy on `plugins-logos` and `app-thumbnails` |
| chat attachments | chat files (image thumbnails) | the object **key** is stored, the signed URL is minted at read time |

A signed URL expires, so every consumer was checked before the change: none of the five audio URLs is
persisted. Two have no caller, one has its return value discarded, one is fetched immediately by the STT
provider, one goes straight back to the client in the upload response.

**The chat thumbnail is the exception, and it is why the third row looks different.** That URL *is*
persisted — it goes into the chat message document and is re-served on every later read — so a signed
one would become a deferred 403 the day it expired. The object key is stored instead and the URL is
minted where the record leaves the database (`get_messages`, `get_chat_files`, `get_chat_files_desc`) and
in the upload response. Messages written before this hold a full URL and pass through untouched; without
that branch the change would have turned every image already in a user's history into a broken link.

**Applying the asset policy.** On k0s the buckets Job does it (`mc anonymous set download`, on those two
buckets only). Compose creates buckets out-of-band, so do the same by hand once:

```bash
docker run --rm --network omi-oss_omi --entrypoint sh minio/mc:latest -c '
  mc alias set r http://rustfs:9000 "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
  mc anonymous set download r/plugins-logos r/app-thumbnails'
```

Verify the split — this is the check that matters, and all three were run on the live stack:

```bash
# asset bucket, anonymous  -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://rustfs:9000/plugins-logos/<key>
# audio bucket, anonymous  -> 403   (no policy, and the ACL is ignored)
curl -s -o /dev/null -w '%{http_code}\n' http://rustfs:9000/memories-recordings/<uid>/<id>.wav
# the SAME audio object with a signed URL -> 200
curl -s -o /dev/null -w '%{http_code}\n' "$(python - <<'EOF'
from utils.object_store import get_object_store
print(get_object_store().presign_get('memories-recordings', '<uid>/<id>.wav', expires_seconds=3600))
EOF
)"
```

**`S3_PUBLIC_ACL` stays, and is not dead code**: MinIO honours the ACL, and on AWS buckets with Object
Ownership = *bucket owner enforced* sending `public-read` makes the upload **fail**, so `S3_PUBLIC_ACL=''`
is the right value there. On RustFS it is accepted and ignored.

## Vendor egress: `OMI_VENDOR_EGRESS` (ADR-0057)

One explicit switch for "may data leave for a third party", declared `deny` in `backend.env.base` and in
the chart's `backend.env`. The code default is **`allow`** so upstream behaviour is unchanged for anyone
who never heard of the variable — which is exactly why a self-hosted stack must declare it: silence would
be consent. An **unknown value fails closed** and says so (`OMI_VENDOR_EGRESS='allowed' is not 'allow' or
'deny'; failing closed`), because a typo in a sovereignty gate must not open it.

It governs **three** surfaces — the ones that either send data to a vendor or do not exist at all — and all
three **degrade**, recording `component=vendor_egress` on `omi_fallback_total`:

| surface | what leaves | at `deny` |
|---|---|---|
| Hume prosody (`utils/other/hume.py`) | a URL to the conversation audio → `api.hume.ai` | no emotion enrichment; the conversation is intact, and no orphan `PROCESSING` task row is written |
| LangSmith (`utils/observability/langsmith*.py`) | the prompts themselves + `uid`/`app_id` → SaaS | no tracer, no Prompt Hub pull (the local prompt is used) |
| GitHub (`utils/github_releases.py`, `utils/app_integrations.py`) | that this deployment exists → `api.github.com` | update endpoints answer "no release"; the product tool answers without the docs corpus |
| **STT provider selection** (`config/stt_provider_policy.py`, ADR-0066) | the conversation **audio** → Modulate / Deepgram cloud | a vendor provider is not selectable: `TranscriptionFailure(CONFIG_ERROR, retryable=False)` for batch, `(None, None, None)` for streaming. **Raises, does not degrade** |

Both GitHub gates sit **after** the cache read: what is governed is the request, not the feature, and
serving a value already on this box sends nothing anywhere.

**STT is the one that raises**, per ADR-0057's own criterion: an empty transcript is a wrong artefact the
user sees, so failing must be loud. It also carries a lesson worth repeating — the STT preferences
(`STT_SERVICE_MODELS`, `STT_PRERECORDED_MODEL`) used to live only in a **comment** in `backend.env.base`,
and measured on the running stack that meant even English selected **modulate**: the only thing keeping the
audio in was the absence of `MODULATE_API_KEY`. They are declared now, in the env-file and in the chart.
Consequence to know: **`compose.prod.yaml` without `--profile inference` has no STT at all** — there is no
local provider to select — and it now says so instead of quietly picking a vendor.

What it does **not** govern, because these are not vendors or not a posture: the operator's own inference
endpoint (ADR-0035 — that IS the on-prem design), image and model-weight provisioning (ADR-0048), push
notifications (ADR-0011, its own flag), and fallbacks that reach a vendor despite local configuration —
those are defects, tracked one by one.

Proven live on `compose.prod.yaml`, same container, one variable apart:

```bash
# deny (the declared posture): the product path answers without leaving the box
docker compose -f compose.prod.yaml exec backend \
  curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8080/v2/desktop/download/latest?platform=macos'
# -> 404, and: omi_fallback_event component=vendor_egress from=github_releases to=skipped reason=policy

# allow: the same call reaches api.github.com (100 releases) — so the gate is what stopped it,
# not a missing network path
docker compose -f compose.prod.yaml exec -e OMI_VENDOR_EGRESS=allow backend /opt/venv/bin/python -c \
  "import asyncio; from utils.github_releases import get_omi_github_releases; \
   print(len(asyncio.run(get_omi_github_releases('probe'))))"
```

> **Reading the counter** (ADR-0068). `record_fallback` writes a log line **and** increments
> `omi_fallback_total`. The second one needs `METRICS_SECRET`, which is declared in `backend.env.base` and
> in `llm_gateway.env` (the gateway has its own `/metrics` with the same check) — without it the endpoint
> answers **401 to everyone**, which is how every fallback this fork records lived in the log alone until
> 2026-08-21.
>
> ```bash
> docker compose -f compose.prod.yaml exec backend sh -c \
>   'curl -s -H "Authorization: Bearer $METRICS_SECRET" http://localhost:8080/metrics | grep vendor_egress'
> # omi_fallback_total{component="vendor_egress",from_mode="github_releases",reason="policy",...} 1.0
> ```
>
> On k8s the token comes from `backend.metricsSecret` (Secret key `METRICS_SECRET`, also passed to the
> gateway). **A Secret-only change now rolls the pods** — it did not before, and `helm upgrade` reported
> `deployed` while the process kept the old value, because `envFrom` is bound at pod start. Nobody scrapes
> this yet: there is no Prometheus in the compose or the chart, so today it is manual inspection (BACKLOG
> L43, second half).

## Configuration that only LOOKS set (ADR-0083) — and the MCP identity it hid

Two checks now run before the backend serves anything, and one declaration exists because of what they
found.

**The boot gate.** `config/placeholder_values.py` refuses a value that was meant to be replaced, and the
process stops with the variable named. Two tiers, deliberately:

| pattern | scope | why |
|---|---|---|
| `CHANGE_ME` / `changeme` / `change-me` | **every** variable | no real value looks like that, and the examples ship it on FIVE secrets (`ENCRYPTION_SECRET`, `OMI_LLM_GATEWAY_SERVICE_TOKEN`, `METRICS_SECRET`, `MEMORY_V3_CURSOR_SECRET`, `TYPESENSE_API_KEY`). Miss one and you are not running with a weak secret, you are running with a **published** one |
| `<...>`, `your-`, `example.com`, `TODO` | the site-specific list in `MUST_BE_SUBSTITUTED` | these CAN occur inside a legitimate value; applying them everywhere would make the gate cry wolf, and a gate that cries wolf gets an escape hatch |

Also refused: `ADMIN_KEY` declared **empty**. Unset is fail-closed (every admin route requires the header
and no string equals `None`); empty is not — the routes comparing `secret_key != os.getenv('ADMIN_KEY')`
then accept an empty header. Leave the line out.

The gateway runs the same gate: it is a separate process with its own env file, and gating only the
backend would leave half the stack on a published token. The message names the **pattern**, never the
value.

What it does not do: reachability. A syntactically plausible issuer that no Keycloak serves passes.

**`MCP_RESOURCE_URL`** is declared by both targets because of what the gate exposed on the way. Unset, the
code default is upstream's own endpoint (`https://api.omi.me/v1/mcp/sse`), so a self-host served this:

```json
{"resource": "https://api.omi.me/v1/mcp/sse",
 "authorization_servers": ["https://<your-issuer>/realms/omi"]}
```

— our authorization server, upstream's resource. An MCP client following it asks our Keycloak for a token
audienced to Omi's cloud. Note that the *other half* of the same document already refuses to mislead:
`authorization_servers` returns **501** when `OIDC_ISSUER` is missing under `AUTH_BACKEND=oidc`.

Compose declares it in `backend.env.prod`; the chart derives it from `omi-oss.apiHostname`
(`api.hostname`, or the pinned LoadBalancer IP), **outside** the auth profile — a firebase-backed
self-host advertises upstream's URL just the same. Verify it on either target:

```bash
# compose
docker compose -f compose.prod.yaml exec -T backend \
  curl -s http://localhost:8080/.well-known/oauth-protected-resource | python3 -m json.tool
# k0s
POD=$(kubectl -n omi get pods -l app.kubernetes.io/component=backend -o jsonpath='{.items[0].metadata.name}')
kubectl -n omi exec $POD -c backend -- curl -s http://localhost:8080/.well-known/oauth-protected-resource
```

`resource` and `authorization_servers` must both name **your** deployment.

## Scheduled work: ONE compose service, several cadences (ADR-0062/0065)

`--profile jobs` brings up a single `scheduled_jobs` container. Which jobs it ticks, and how often, is
**configuration** — `OMI_SCHEDULED_JOBS` in the deploy/onprem `.env`:

```
OMI_SCHEDULED_JOBS=notifications=hourly,memory-maintenance=hourly,conversation-search-index=300
```

Unset, it runs `notifications=hourly` alone. The other two **fail by design** without their prerequisites
(`MEMORY_ENABLED` + `MEMORY_CANONICAL_MAINTENANCE_ENABLED` for the first, Typesense for the second), and a
job that fails every tick is worse than one not running — so they are opt-in alongside what they need.

One process, one task per job, each isolated: a failing tick is logged and only that job's loop continues.
**Kubernetes keeps a native CronJob per job instead** (`scheduledJobs.*` in values) — there a scheduler
exists, and per-job history and retry are worth having.

Run one job now, whatever the schedule says (the `kubectl create job --from=cronjob` equivalent):

```bash
docker compose -f compose.prod.yaml --profile jobs run --rm --no-deps scheduled_jobs \
  python -m jobs.onprem_scheduled --job notifications
```

A bad entry is a startup failure with the offending text, not a job that silently never runs — the parser
rejects an unknown name or a cadence that is neither `hourly` nor a positive number of seconds.

## Keyword search & the memory feature (ADR-0063)

`--profile search` brings up **Typesense**, and it is a prerequisite of memory intake — not an optional
extra. What the code actually does, verified live rather than read off:

**Two consumers, not symmetric.**
- **memory atoms** — the backend CREATES the collection and UPSERTS documents itself
  (`utils/memory/atom_keyword_index.py:204`/`:238`). Self-contained, so Typesense makes this work.
- **conversations** — READ ONLY. The only reference to that collection in the whole repo is a
  `search()`; upstream feeds it from a Firestore -> Typesense pipeline that is **not in the codebase**.
  So enabling this profile does **not** restore conversation search: `/v1/conversations/search` (the
  app's search bar AND its date-range browse) would query an empty index. That needs an indexer of ours.

**Why memory needs it.** The canonical memory outbox's `projection_sync` event *is* this index:
`projection_upsert = sync_atom_keyword_index_for_item`. With `MEMORY_ENABLED=on` and no Typesense every
`projection_sync` stays `retryable_failure` **forever** — one permanently stuck event per memory.

**The full prerequisite chain**, in the order a memory travels it:

| step | needs | if missing |
|---|---|---|
| write | Mongo | — |
| `vector_sync` | a vector store (`--profile chat` -> Qdrant) | `delete_canonical_memory_vectors` returns False when `is_vector_available()` is false, so delete events stay `retryable_failure` forever |
| promotion short-term -> long-term | an **LLM endpoint** (consolidation "dreaming", lane `memory_conflict`) | `consolidation_failed`, the atom stays short-term — and only **long-term** atoms are indexable (`is_indexable_long_term_atom`), so the index stays empty |
| `projection_sync` | Typesense | stuck forever (above) |
| keyword hit | all of the above | vector-only retrieval; the keyword half is what catches names embeddings miss |

So the runnable posture for memory is `--profile search --profile chat --profile jobs` plus
`MEMORY_ENABLED=on`, `MEMORY_CANONICAL_MAINTENANCE_ENABLED=true`, `MEMORY_V3_CURSOR_SECRET`, and
`memory-maintenance=hourly` in `OMI_SCHEDULED_JOBS`.

**End-to-end check** (this is the one that proves it; the queue draining alone does not):

```bash
cd deploy/onprem
docker compose -f compose.prod.yaml --profile search --profile chat --profile jobs --profile jobs-memory up -d
# write a memory, then force one maintenance tick (the CronJob equivalent):
docker compose -f compose.prod.yaml --profile search --profile chat --profile jobs-memory \
  run --rm --no-deps scheduled_jobs python -m jobs.onprem_scheduled --job memory-maintenance
# expect: promoted_total=1, outbox_delivered>0, errors=0, exit 0
# then the index must actually contain it:
K=$(grep -oE '^TYPESENSE_API_KEY=.*' .env | cut -d= -f2)
docker compose -f compose.prod.yaml exec -T typesense bash -c \
  "exec 3<>/dev/tcp/localhost/8108; printf 'GET /collections HTTP/1.0\r\nX-TYPESENSE-API-KEY: $K\r\n\r\n' >&3; cat <&3 | tail -1"
# expect: canonical_memory_atoms with num_documents >= 1
```

`--loop` is only for the long-running compose services; a forced tick runs once and its exit code is the
verdict. Note that `docker compose run` needs the **profiles** on the command line too: the runner
`depends_on: typesense`, and a dependency in an inactive profile is "no such service".

**Secret hygiene.** The API key goes through the environment, never `--api-key` on the command line: an
argv flag shows the secret in `docker inspect` and in every in-container process listing. Verified that
Typesense reads `TYPESENSE_API_KEY` from the environment and enforces it (wrong key -> 401).

**`TYPESENSE_PROTOCOL=http` is not optional.** The client defaults to **https**
(`utils/conversations/search.py:155`), so a service reached by name over plain HTTP must say so.

### Conversation search: we write the index (ADR-0064)

The `scheduled_jobs` runner ticks it **every 5 minutes** (not hourly: search freshness is user-visible)
when `conversation-search-index=300` is in `OMI_SCHEDULED_JOBS`. It is the writer upstream does not ship — their `conversations`
collection is filled by a Firestore -> Typesense pipeline outside the codebase, so without this the index
stays empty and the app's search bar and date browse find nothing.

One bounded **full** reconcile per run, not an incremental sweep: the store's `updated_at` is document
metadata, not a queryable field, so a "changed since" watermark would index new conversations and
silently miss every edit. The pass costs one read per conversation and is correct including deletions.
Two rules it obeys: a truncated run **says so**, and a truncated run **does not prune** (pruning is
"delete what the scan did not see", so pruning a partial scan would delete live conversations).
Raise the cap with `CONVERSATION_SEARCH_INDEX_MAX_DOCUMENTS`.

Force one pass and check what it did:

```bash
docker compose -f compose.prod.yaml --profile search --profile jobs \
  run --rm --no-deps scheduled_jobs \
  python -m jobs.onprem_scheduled --job conversation-search-index
# -> scanned=N indexed=N skipped_incomplete=0 pruned=M truncated=False errors=0
```

### The admin dashboard's conversation count

`web/admin` reads `num_documents` off the `conversations` collection **directly**, not through the
backend (`app/api/omi/stats/conversation-count/route.ts`). With the indexer running that number equals
the store — verified: 2 in Typesense, 2 in Mongo. Two traps when wiring it:

- **`TYPESENSE_HOST` must carry the scheme.** That route prepends `https://` when the value has none
  (`route.ts:26-28`), and our Typesense speaks plain HTTP. Use `TYPESENSE_HOST=http://<host>:8108`.
- **Do not give it the master key.** `search.apiKey` can read *and write* every collection, including the
  memory atoms. Mint a key that can do exactly one thing, and verify it is refused elsewhere:

```bash
curl -X POST http://<typesense>:8108/keys -H "X-TYPESENSE-API-KEY: $MASTER" \
  -d '{"description":"admin stats: conversation count","actions":["collections:get"],"collections":["conversations"]}'
# the response `value` is the only time the key is shown. Then check the blast radius:
curl -s -o /dev/null -w '%{http_code}\n' http://<typesense>:8108/collections/conversations         -H "X-TYPESENSE-API-KEY: $SCOPED"  # 200
curl -s -o /dev/null -w '%{http_code}\n' http://<typesense>:8108/collections/canonical_memory_atoms -H "X-TYPESENSE-API-KEY: $SCOPED"  # 401
```

Verified against the pinned image: the scoped key reads `conversations` and is **Forbidden** on the
memory collection.

## Testing the backend offline

The box has only Docker (no host venv). Suites run in a **test image** = the WP0 backend image plus
additive test-only tooling (`git`, `helm`, and test Python deps). The image is reproducible from the
committed [`Dockerfile.test`](Dockerfile.test):

```bash
cd deploy/onprem
docker compose -f compose.prod.yaml build                                            # WP0 images (once)
docker build -t omi-oss-backend-test -f Dockerfile.test .    # test image
```

### Mount the REPO ROOT, not just `backend/`

A large set of contract tests resolve repo-root paths via `Path(__file__).resolve().parents[N]` and
read `.github/`, `docs/`, `firestore.indexes.json`, `desktop/`, helm charts, etc. Mounting only
`backend/` at `/app` flattens the tree so those walks overshoot to `/` and raise `FileNotFoundError`.
Mount the **whole repo** so `backend/` sits at its real depth:

```
-v $(git rev-parse --show-toplevel):/repo -w /repo/backend
```

Do **not** set `OMI_ENV_STAGE=selfhost` for the unit sweep: that variable is for the runtime compose
posture, and forcing it makes a couple of tests assert the wrong environment/stage. `LOCAL_DEVELOPMENT=true`
is the signal the unit suite expects. (See the known residual failures at the end.)

### Run one suite — FILE-ISOLATED (mandatory)

The suite carries module-level state (`load_module_fresh`, monkeypatched clients, singletons), so
**more than one test file per `pytest` process cross-contaminates `sys.modules` -> false failures.**
Run **one process per file**:

```bash
docker run --rm -v $(git rev-parse --show-toplevel):/repo -w /repo/backend \
  -e ENCRYPTION_SECRET="$(openssl rand -hex 32)" -e OPENAI_API_KEY=test \
  -e PYTHONUTF8=1 -e OMP_NUM_THREADS=1 -e LOCAL_DEVELOPMENT=true \
  omi-oss-backend-test /opt/venv/bin/python -m pytest -q -o addopts="" tests/unit/<file>.py
```

Use `/opt/venv/bin/python` (not `bash -l`, which resets PATH and loses the venv).

### Full sweep — parallelize the OUTER loop, not pytest

File isolation is a correctness requirement, but the outer loop parallelizes across cores: N
concurrent `pytest <one-file>` invocations, **each still its own process** — identical isolation,
identical verdicts, ~7.5x faster (measured full unit sweep ~17 min -> ~2 min on 20 cores). Do
**not** use `pytest-xdist -n … --dist loadfile`: xdist workers reuse a process across files, which
brings the contamination back. Self-contained runner:

```bash
docker run --rm -v $(git rev-parse --show-toplevel):/repo -w /repo/backend \
  -e ENCRYPTION_SECRET="$(openssl rand -hex 32)" -e OPENAI_API_KEY=test -e PYTHONUTF8=1 \
  -e OMP_NUM_THREADS=1 -e LOCAL_DEVELOPMENT=true \
  omi-oss-backend-test bash -c '
    ls tests/unit/test_*.py tests/unit/utils/test_*.py testing/e2e/test_*.py | \
    xargs -P 16 -I{} sh -c '\''out=$(/opt/venv/bin/python -m pytest -q -o addopts="" -p no:cacheprovider "{}" 2>&1 | tail -1);
      echo "$out" | grep -qiE "failed|error" && echo "FAIL | {} | $out" || echo "PASS | {} | $out"'\'' '
```

Include `testing/e2e/test_*.py` in the glob: port residuals (`db_client=`, changed signatures) survive
in E2E suites that a `tests/unit`-only sweep never runs — two such residuals shipped past earlier
audits before this was added (ADR-0040 rule 7).

**Always run the sweep under `time`.** It is the only reason the 14 GB below was ever found: the sweep
had been getting slower for weeks and nothing said so, because a duration nobody records is a regression
nobody can see. A wall-clock figure in the same place as the FAIL set makes "it got slower" a fact you
notice on the next run instead of a feeling.

```bash
time docker run --rm -v $(git rev-parse --show-toplevel):/repo ...   # the sweep below
```

Reference on 20 cores, after the cleanup: **~3 min** for the full unit sweep, **~2m40s** with the
one-container runner. Twice that means something changed — look at `_temp` first.

**Second, empty `backend/_temp/`.** It is gitignored scratch that the speech-profile and audio suites
write into, it is never cleaned, and `test_runtime_image_contracts` copies the whole backend tree **once
per image contract** — so whatever has piled up there gets copied several times, over a bind mount, on
every sweep.

Measured on 2026-08-22, when that directory had reached **14 GB in 896 WAV files** (the rest of
`backend/` is 100 MB):

| | with 14 GB in `_temp` | after emptying it |
|---|---|---|
| `test_runtime_image_contracts.py` alone | **4 min 12 s** | **7 s** |
| full unit sweep | **7 min 22 s** | **3 min 11 s** |

Same verdicts in both cases — it is pure I/O. The files are written by root inside the containers, so a
plain `rm -rf` fails with *Permission denied* and the directory keeps growing unnoticed:

```bash
sudo rm -rf backend/_temp && mkdir -p backend/_temp
```

**De-flake before trusting a FAIL** — and know what the flakiness actually is. An earlier note here
blamed "docker-per-file startup contention" for `-P 16` yielding ~90 false FAILs that passed at `-P 3`.
Measured, that was mostly the `_temp` copy above saturating disk I/O: one file was stalling all sixteen
lanes, and unrelated suites showed identical ~84 s timings that are **1.3 s** when run alone. Empty
`_temp` first; if a FAIL set still looks suspicious, re-run it at low parallelism (`-P 3`) and diff
against a pre-change baseline worktree before calling anything a regression.

To gate a change, **diff the FAIL set against a baseline worktree at the commit you started from** —
not against the residual list below, which drifts (it said three files while the sweep failed eight).
Same file names AND same counts on both sides = no regression.

### Regression guard

```bash
python3 .github/scripts/check_oss_firestore_persistence_boundary.py   # must exit 0 (0 violations)
```

Runs bare with stdlib `python3` (no venv). It enforces the WP1 boundary: only `database/` may touch
the raw Firestore client.

### Dual-backend contract test (adapter parity)

Proves the Firestore and Mongo adapters honor the same neutral contract against **real** services.
Mongo owns the network namespace; the emulator and the test container share it (`--network
container:`) so both services are on `localhost` and the hermetic loopback-only guard in
`tests/conftest.py` accepts them.

Both services need a readiness wait, and **both waits must be bounded**: an unbounded `until` does not
fail when something is wrong, it hangs — and a hung suite is indistinguishable from a slow one until
somebody looks. (Improvised waits have burned us twice: one unbounded loop stayed up for 28 hours, and
one probed with `curl` from the mongo container, which has no `curl`.)

```bash
# 1. Mongo (single-node replica set) — wait for the primary, give up loudly
#    Same image the stack deploys (deploy/onprem/omi.oss.release.pins) — a contract proven on a
#    different major than the one we ship proves the wrong thing.
docker run -d --name wp2-mongo mongo:7 --replSet rs0 --bind_ip_all
docker exec wp2-mongo mongosh --quiet --eval \
  "rs.initiate({_id:'rs0',members:[{_id:0,host:'127.0.0.1:27017'}]})"
for i in $(seq 30); do
  docker exec wp2-mongo mongosh --quiet --eval 'db.hello().isWritablePrimary' 2>/dev/null | grep -q true && break
  [ "$i" = 30 ] && { echo "mongo never became primary"; docker logs --tail 20 wp2-mongo; exit 1; }
  sleep 2
done
# 2. Firestore emulator in the same netns — wait on ITS OWN readiness line, not on a network probe
#    (no dependency on a tool the container may not ship)
docker run -d --name wp2-emu --network container:wp2-mongo omi-oss-firestore-emulator:latest
for i in $(seq 30); do
  docker logs wp2-emu 2>&1 | grep -q "Firestore Emulator was started" && break
  [ "$i" = 30 ] && { echo "emulator never started"; docker logs --tail 20 wp2-emu; exit 1; }
  sleep 2
done
# 3. Contract suites (same netns) — ONE PROCESS PER FILE, for the same reason as the unit sweep:
#    each suite installs its own client into the module-level accessor.
docker run --rm --network container:wp2-mongo -v $(git rev-parse --show-toplevel):/repo -w /repo/backend \
  -e FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 -e MONGO_URI="mongodb://127.0.0.1:27017/?replicaSet=rs0" \
  -e FIREBASE_PROJECT_ID=demo-omi-local -e GOOGLE_CLOUD_PROJECT=demo-omi-local \
  -e ENCRYPTION_SECRET="$(openssl rand -hex 32)" -e OPENAI_API_KEY=test \
  omi-oss-backend-test bash -c '
    for f in tests/contract/test_document_store_contract.py \
             tests/contract/test_users_people_contract.py \
             tests/contract/test_conversations_contract.py \
             tests/contract/test_apps_contract.py \
             tests/contract/test_chat_contract.py \
             tests/contract/test_action_items_contract.py \
             tests/contract/test_finalization_jobs_contract.py \
             tests/contract/test_llm_usage_contract.py \
             tests/contract/test_user_usage_contract.py \
             tests/contract/test_staged_tasks_contract.py \
             tests/contract/test_action_item_dedup_contract.py \
             tests/contract/test_notifications_contract.py; do
      /opt/venv/bin/python -m pytest -q -o addopts="" -p no:cacheprovider "$f" | tail -1 | sed "s|^|$f: |"
    done'
docker rm -f wp2-mongo wp2-emu    # cleanup
```

Every test must run **twice** (the `bind_store` fixture is parametrized `firestore`/`mongo`). A
per-backend `SKIPPED` means that service's env var never reached the container — the suite then proves
half of what its name claims, which is how two of these suites sat dead for months. Check the counts.

**What the transaction contract does and does not promise** (ADR-0070), because the two backends differ and
the suite only asserts the intersection. Measured on this rig:

| | Mongo | Firestore emulator |
|---|---|---|
| a query in the transaction sees the transaction's own writes | yes | **no** — the SDK raises `ReadAfterWriteError` |
| a concurrent write to a row the transaction only READ blocks the commit | **no** — it commits with the stale read | yes — the transaction holds a lock, the writer gets `409 Aborted` |
| write-write on the same document | aborts (`TransientTransactionError`) | aborts |

So `tx.query` means "the read runs in the transaction's own view of committed state" and nothing more. Code
that needs read-set conflict detection (the `idempotency_key` de-dup in `database/action_items.py`) is NOT
protected on Mongo by the transaction alone — BACKLOG L46.

**A batch, on the other hand, IS all-or-nothing on both backends** (ADR-0072). The Mongo commit used to
group by collection and apply one group at a time with no rollback, which two callers explicitly rely on
not happening (`chat.py::delete_messages`, `staged_tasks.py`); measured, a failing precondition on the
second group left the first applied — the chat message deleted and its counter never decremented. The
commit now runs inside a transaction, so **the batch path needs the replica set too**, not just
`run_transaction`. A standalone mongod keeps the old behaviour and records
`component=document_store to=batch_per_collection reason=capability_mismatch`; neither of our targets is
standalone.

Note: gRPC (Firestore) bypasses the Python socket guard; pymongo uses Python sockets but on loopback,
which the guard permits.

**Which modules still have no dual-backend cover** (ADR-0060). The contract suites are the only lane
that reaches an adapter, so "covered" means "some contract suite drives this module". A guard keeps the
inventory honest and ratchets it — a `database/` module that gains a shape the facade must *translate*
(composite filter, cursor, projection, aggregation, transaction, batch, atomic field op, collection
group) while still uncovered fails CI:

```bash
python3 .github/scripts/check_oss_store_contract_coverage.py            # the ratchet (exit 0 = at baseline)
python3 .github/scripts/check_oss_store_contract_coverage.py --report   # ranked worklist: module -> shapes
```

It is a static inventory, not behavioral coverage: it cannot tell whether a suite asserts the right
thing. It exists because `database/apps.py` made every marketplace read 500 under our own
`STORAGE_BACKEND=mongo` default from the day the facade landed, with the whole suite green.

### Object-store contract test (adapter parity)

Proves the GCS and S3 adapters honor the same neutral object-store contract (ADR-0032) against **real**
services: `fsouza/fake-gcs-server` (GCS) and `rustfs/rustfs` (S3). Both run on `--network host` so they
are reachable on `127.0.0.1`, which the loopback-only hermetic guard accepts. The `fake` backend always
runs (hermetic); `gcs`/`s3` are skipped when their env is absent.

```bash
# 1. RustFS (S3) + fake-gcs-server (GCS) on the host network (loopback)
docker run -d --name oc-rustfs --network host \
  -e RUSTFS_ACCESS_KEY=testkey -e RUSTFS_SECRET_KEY=testsecret rustfs/rustfs:latest
docker run -d --name oc-gcs --network host \
  fsouza/fake-gcs-server:latest -scheme http -host 0.0.0.0 -port 4443 -public-host 127.0.0.1:4443
# wait: curl 127.0.0.1:9000 -> 403 (S3 serving); curl 127.0.0.1:4443/storage/v1/b -> 200
# 2. Contract suite (same host netns)
docker run --rm --network host -v $(git rev-parse --show-toplevel)/backend:/app -w /app \
  -e S3_ENDPOINT=http://127.0.0.1:9000 -e S3_PUBLIC_ENDPOINT=http://127.0.0.1:9000 \
  -e S3_ACCESS_KEY=testkey -e S3_SECRET_KEY=testsecret -e S3_REGION=us-east-1 \
  -e STORAGE_EMULATOR_HOST=http://127.0.0.1:4443 \
  omi-oss-backend-test -m pytest -q tests/contract/test_object_store_contract.py
# expected: 39 passed, 1 skipped (presign_get[gcs]: fake-gcs-server has no signing key; GCS V4
# signing is covered by the hermetic delegation unit test in the same file)
docker rm -f oc-rustfs oc-gcs    # cleanup
```

### Vector-store contract test (adapter parity)

Proves the Pinecone and Qdrant adapters honor the same neutral vector-store contract (ADR-0033),
including the neutral `$`-DSL filter (`$exists:false` legacy barrier, `$and`/`$or`, ranges, `$in`).
The `fake` backend always runs (hermetic); `qdrant` runs against a real Qdrant on `--network host`
(loopback); `pinecone` is skipped unless configured (no offline emulator — the fake is the reference).

```bash
docker run -d --name vc-qdrant --network host qdrant/qdrant:latest   # wait: curl 127.0.0.1:6333/readyz -> 200
docker run --rm --network host -v $(git rev-parse --show-toplevel)/backend:/app -w /app \
  -e QDRANT_URL=http://127.0.0.1:6333 -e QDRANT_VECTOR_DIM=8 \
  omi-oss-backend-test -m pytest -q tests/contract/test_vector_store_contract.py
# expected: 30 passed, 15 skipped   (the skips are the `pinecone` parametrization: no offline emulator)
docker rm -f vc-qdrant    # cleanup
```

### Auth contract test (adapter parity)

Proves the OIDC adapter validates a real provider's token to the same neutral Principal as the fake
(ADR-0034). The `fake` backend always runs; `oidc` runs against a real Keycloak on `--network host`
(loopback); `firebase` is skipped unless a firebase emulator is wired (the fake is the reference).

```bash
# 1. Keycloak importing the DEV realm — provisions realm 'omi' + client 'omi-test' (direct access) +
#    user 'testuser/testpass' + the `omi-backend` Audience protocol mapper on omi-app/omi-test. Use
#    the .dev variant: the prod realm (omi-realm.example.json) omits the test client/user (review #5).
docker run -d --name kc-contract --network host \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  -v $(git rev-parse --show-toplevel)/deploy/onprem/keycloak/omi-realm.dev.example.json:/opt/keycloak/data/import/omi-realm.json:ro \
  quay.io/keycloak/keycloak:26.0 start-dev --http-port=8080 --import-realm   # wait: curl 127.0.0.1:8080/realms/omi -> 200
# 2. Contract suite (mints a token via the password grant, verifies via the adapter's JWKS). The token
#    carries aud=omi-backend from the realm's Audience mapper; OIDC_AUDIENCE must match (fail-closed).
docker run --rm --network host -v $(git rev-parse --show-toplevel)/backend:/app -w /app \
  -e OIDC_ISSUER=http://127.0.0.1:8080/realms/omi \
  -e OIDC_JWKS_URL=http://127.0.0.1:8080/realms/omi/protocol/openid-connect/certs \
  -e OIDC_TEST_TOKEN_URL=http://127.0.0.1:8080/realms/omi/protocol/openid-connect/token \
  -e OIDC_TEST_CLIENT_ID=omi-test -e OIDC_TEST_USERNAME=testuser -e OIDC_TEST_PASSWORD=testpass \
  -e OIDC_AUDIENCE=omi-backend \
  omi-oss-backend-test -m pytest -q tests/contract/test_auth_provider_contract.py
# expected: 5 passed, 4 skipped (firebase cases skipped — no emulator)
docker rm -f kc-contract    # cleanup
```

### Known residual failures — and why the list is not the gate

**Do not gate a change on this list. Gate it on a diff against a baseline worktree** at the commit you
started from:

```bash
git worktree add -f /tmp/base <sha-you-started-from>
# run the same sweep in both trees, then compare file-by-file AND count-by-count
```

**Two suites flake under the parallel sweep, and only there** (measured 2026-08-21, `-P 16`):
`testing/e2e/test_sync_lifecycle.py` and `testing/e2e/test_boundary_contract_compatibility.py` each failed
once in a sweep and then passed 3/3 and 5/5 in isolation. Both are E2E with a websocket or a lifecycle
fixture, neither touches what was being changed at the time. So a single new FAIL in one of those two is
worth re-running alone before treating it as a regression — and a FAIL in anything else is not.

The list below drifts: it said *three files* while the measured sweep failed *eight*, and only one
name overlapped — two of the three documented residuals had since started passing. A stale list is
worse than no list, because "the FAIL set equals the known residuals" then reads as green. The
baseline diff cannot drift, and it is what caught a regression this list would have absorbed
(`test_city_prompt_context.py`, ours, fixed in `1a8a6edb01`).

**Measured 2026-08-21, all eight diagnosed.** 960 files swept; the eight that failed at `e88aeb2d90`
also failed at `bb14216e52`, which proved only that they were *older* — not that they were upstream's.
Three of them were ours. The test that settles it is cheap and worth repeating for any new entry:
**run the file in a worktree at the upstream side of the last merge** (`git log -1 --format=%P <merge>`
→ second parent) and see whether it fails there too.

| file | failing tests | verdict |
|---|---|---|
| `tests/unit/test_app_client_ts_generator.py` | 1 (generated schema types) | ✅ **ours** — fixed `ec3a195376` |
| `tests/unit/test_app_client_swift_generator.py` | 2 (generated DTO, CLI `--check`) | ✅ **ours** — fixed `ec3a195376` |
| `tests/unit/test_city_prompt_context.py` | 1 | ✅ **ours** — fixed `1a8a6edb01` |
| `testing/e2e/test_crud.py` | 5 (`TestMemoryCRUD`) | upstream harness, see below |
| `testing/e2e/test_failure_modes.py` | 2 (`fake_redis`, `unicode_roundtrip`) | upstream harness, see below |
| `testing/e2e/test_mobile_lifecycle_compatibility.py` | 2 (bootstrap, mutation compat) | upstream harness, see below |
| `testing/e2e/test_retrieval_search.py` | 1 (reindex/delete removes result) | upstream harness, see below |
| `tests/unit/test_sys_modules_hermeticity.py` | 1 (single-process safe subset) | upstream env leak, see below |

The three "ours" were invisible because the previous version of this list called them known residuals.
The two generator ones came from adding `POST /v1/users/unifiedpush-endpoint` without regenerating the
committed TS/Swift clients; both suites pass on the upstream tree, which is how they were caught.

**The four E2E groups: memory intake is fenced off, and the fence is a 503.** All four fail identically
on the upstream tree. Cause, traced by spying on the service call rather than guessed:

    routers/memories.py POST /v3/memories -> MemoryService.create_external_memory
      -> _canonical_write -> ensure_canonical_mutation_ready
      -> HTTPException(503, "Memory writes are globally paused")   [memory_service.py:1378]

`rollout_mode_env_value()` (`config/memory_rollout.py:114`) defaults to `off` when **neither**
`MEMORY_ENABLED` nor `MEMORY_MODE` is set, and the router rewrites the 503 into the generic "Service
temporarily unavailable". Upstream's E2E harness never sets either, so every memory write in it is
fenced; the retrieval and mobile-lifecycle failures are downstream of the same fence.

**This applies to a real deployment too, not only to the harness:** nothing under `deploy/onprem/`
sets any `MEMORY_*` variable, so on this stack `/v3/memories` writes answer 503 with an opaque message
and the on-prem live E2E never calls them, so nothing says so. Whether the on-prem posture should
enable intake is a product decision, tracked in `docs/BACKLOG.md`.

Previously documented and **now passing** (kept because the reasoning explains what the harness does
to them, and they can come back):

- `tests/unit/test_auto_dev_backend_scope.py` — one subtest extracts and executes the real
  `.github/workflows/gcp_backend_auto_dev.yml` scope step's bash against a temp git repo; the
  discrepancy is inside that CI workflow logic, not the backend.
- `tests/unit/test_ws_auth_handshake.py` — one subtest asserts WebSocket auth *enforcement* (empty
  bearer -> close 1008), which requires `LOCAL_DEVELOPMENT` unset. The unit sweep sets it because ~46
  other files rely on the dev-auth bypass; a single global env cannot satisfy both. The file passes
  in isolation with `LOCAL_DEVELOPMENT` unset.

Still failing, diagnosed:
- `tests/unit/test_sys_modules_hermeticity.py` — the single-process-safe-subset guard fails because
  several upstream STT test files (`test_parakeet_diarization/nim/prerecorded/stream_session.py`,
  `test_sync_transcription_prefs.py`) write `DEEPGRAM_API_KEY` at module/fixture scope without
  cleanup, and two upstream STT tests (`test_modulate_stt.py::TestLanguageRouting`,
  `test_streaming_deepgram_backoff.py::TestGetSttServiceForLanguage`) assert the "retired deepgram
  config -> non-deepgram default" path, which only holds when `DEEPGRAM_API_KEY` is unset. The victim
  tests are latently order-dependent upstream (they never establish that precondition); left as-is by
  decision — not introduced by the self-host work. Each file passes in isolation.

## Testing the Flutter app offline

Same principle as the backend harness (ADR-0026): a **committed, pinned image** and a **repo-root
mount**, not ad-hoc `docker run` on a stray Flutter image. The image is
[`Dockerfile.appbuild`](Dockerfile.appbuild) (JDK 21 + Android SDK 36 + NDK + cmake/ninja for the
`webcrypto` native asset + `jq` for the analyzer ratchet). Pin Flutter to the **CI version** so
`pubspec.lock` and `gen-l10n` output don't drift (app CI = `subosito/flutter-action` `flutter-version: 3.44.5`):

```bash
cd deploy/onprem
docker build -t omi-oss-flutter-appbuild:cached --build-arg FLUTTER_VERSION=3.44.5 -f Dockerfile.appbuild ../..
```

Mount the repo root, use persistent gradle/pub caches (first run compiles the webcrypto native asset
— a few minutes; later runs reuse it):

```bash
docker run --rm -v "$(git rev-parse --show-toplevel)":/repo -w /repo/app \
  -v omi-oss-flutter-appbuild-gradle:/root/.gradle -v omi-oss-flutter-appbuild-pub:/root/.pub-cache \
  omi-oss-flutter-appbuild:cached bash -lc '
    git config --global --add safe.directory /repo
    flutter pub get
    bash scripts/analyze_ratchet.sh                 # analyzer gate: ERROR=0, WARNING/INFO ratcheted vs analysis_baseline.json
    flutter gen-l10n                                # must be a NO-OP: `git status app/lib/l10n` stays clean (zero untranslated)
    bash test.sh test/unit test/widgets             # hermetic suite; test.sh bootstraps gitignored firebase/env files if absent
  '
```

Notes:
- **Pin `FLUTTER_VERSION` to the CI version.** A different Flutter (e.g. an older stray image)
  downgrades transitive packages in `pubspec.lock` and can shift `gen-l10n` output — false diffs.
- **`gen-l10n` is part of the gate:** after editing `lib/l10n/*.arb` it must leave the generated
  `app_localizations_*.dart` unchanged; `git status app/lib/l10n` clean == zero untranslated warnings.
- The suite is **hermetic** (no live services); `bash test.sh` is the full-suite entry (bootstraps
  the gitignored `firebase_options_*.dart` / `.dev.env`). Run specific files with `flutter test <path>`.

## OIDC client (Flutter app) — end-to-end (ADR-0038)

The app can authenticate against the same on-prem Keycloak the backend validates (ADR-0034), with
**zero Firebase**. It is **additive**: the default (`AUTH_BACKEND=firebase`) is byte-identical to
upstream; the OIDC path is a compile-time flavor.

**App build config** (Envied compile-time, in `app/.dev.env` / `.prod.env`):
```
AUTH_BACKEND=oidc
OIDC_ISSUER=https://<host>/realms/omi   # HTTPS required; must be reachable from the DEVICE
OIDC_CLIENT_ID=omi-app
OIDC_REDIRECT_SCHEME=omiauth
API_BASE_URL=https://<host>/
```
**TLS is mandatory for the deployed issuer.** A login flow carries the code, access token, and the
long-lived `offline_access` refresh token; `OidcAuthService` **refuses any non-loopback `http://`
issuer** (fail-closed) and passes `allowInsecureConnections: true` ONLY for
`http://localhost`/`127.0.0.1`/`::1` in a **debug** build (local dev). **Put on-prem Keycloak behind
an HTTPS reverse proxy** (or a self-signed cert trusted by the device). This is the intentional
posture (option 1, 2026-08-02) — no cleartext escape hatch for LAN issuers.

**Backend audience validation (fail-closed).** The OIDC adapter refuses to start without `OIDC_AUDIENCE`
(set in `backend.env.prod`), and verifies every token's `aud` against it. Keycloak's default `aud` is
`account` for every client — useless for cross-client isolation — so the committed realm adds an
**Audience protocol mapper** (`oidc-audience-mapper`, `included.custom.audience=omi-backend`) to
`omi-app` and `omi-test`, minting a dedicated `aud=omi-backend`. `OIDC_AUDIENCE=omi-backend` must match
that mapper; a token whose `aud` differs is rejected (verified live: aud=omi-backend accepted,
aud≠OIDC_AUDIENCE rejected).

**Native redirect config** (must match `OIDC_REDIRECT_SCHEME`): Android
`app/android/app/build.gradle` → `manifestPlaceholders += [appAuthRedirectScheme: 'omiauth']`; iOS
`Info.plist` → `CFBundleURLTypes` with the same scheme. The client is `flutter_appauth` (Auth Code +
PKCE via the system browser).

**Keycloak client for the mobile flow** (distinct from the direct-access contract client above — this
one is **public + standard flow + PKCE**):
```bash
# realm 'omi' + public client 'omi-app' with the app's custom-scheme redirect
curl -X POST "$KC/admin/realms/omi/clients" -H "$AUTH" -H "Content-Type: application/json" -d '{
  "clientId":"omi-app","publicClient":true,"standardFlowEnabled":true,
  "redirectUris":["omiauth:/oidc-callback","omiauth:/*"],
  "attributes":{"pkce.code.challenge.method":"S256"}}'
# a user with email + first/last name so the token carries email/given_name claims
```

**Backend for the app test** — `AUTH_BACKEND=oidc` + `OIDC_ISSUER`/`OIDC_JWKS_URL` pointing at the same
LAN issuer, and **`LOCAL_DEVELOPMENT=false`** (otherwise the dev-bypass uid `123` accepts anything and
never exercises JWKS). Two gotchas proved live:
- **Issuer consistency:** the token `iss` equals the URL the device used; it must equal the backend's
  `OIDC_ISSUER`. Use the same LAN IP on both sides (a token minted via `127.0.0.1` is rejected).
- **Cleartext:** see `allowInsecureConnections` above.

**Proven E2E (emulator, 2026-08-01):** app → `Sign in with SSO` → Keycloak login page in a Chrome
Custom Tab → redirect `omiauth:/oidc-callback?code=…` → token stored → authenticated calls reach the
backend with the Keycloak Bearer, validated via JWKS: `GET /v3/speech-profile 200`,
`PATCH /v1/users/language 200` (from the device IP, not loopback).

**Session persistence** (proved: force-stop + relaunch keeps the session): all Firebase-auth behavior is
gated under `Env.useOidc` — the `idTokenChanges`/session-expired listeners are not attached, and
`refreshIdToken()` refreshes via the OIDC provider (returning a transient failure, never `MissingUser`,
so the 401-recovery paths never call `expireSession()` and wipe the token). See `docs/BACKLOG.md` D20.

### Reproducible dev stack (compose) + full-E2E recipe (proven 2026-08-02)

The whole OIDC stack is declarative — bring it down and back up deterministically:
```bash
cd deploy/onprem
cp .env.dev.example .env                 # edit HOST_IP = the address the DEVICE reaches (not 127.0.0.1)
HOST_IP=<your-ip> ./gen-dev-certs.sh     # self-signed CA + server cert (SAN=HOST_IP); gitignored
# backend.env: AUTH_BACKEND=oidc + OIDC_ISSUER=${KC_HOSTNAME}/realms/omi
#              + OIDC_JWKS_URL=http://keycloak:8090/realms/omi/protocol/openid-connect/certs + LOCAL_DEVELOPMENT=false
docker compose -f compose.prod.yaml --profile auth up -d --build     # keycloak(+kc-proxy https) + api-proxy(https) + backend + deps
```
`keycloak` runs http-only behind `kc-proxy` (TLS on `${KC_HTTPS_PORT}`, `--proxy-headers`); the API runs
behind `api-proxy` (TLS on `${API_HTTPS_PORT}`). The prod realm (`keycloak/omi-realm.example.json`)
imports `omi-app` (public PKCE, redirect `omiauth:/oidc-callback`) only — no test principals (review
#5); `testuser` lives in the dev realm (`omi-realm.dev.example.json`). **Issuer/JWKS split-horizon**
(proven): the token `iss` = the public `KC_HOSTNAME`, so `OIDC_ISSUER` must equal that; the backend
fetches keys over the **internal http** backchannel, so it needs no CA.

**Backchannel endpoints must use the public issuer port** (`--hostname-backchannel-dynamic=false`).
Keycloak's discovery doc splits *frontend* URLs (authorization, logout — from `KC_HOSTNAME`) from
*backchannel* URLs (token, userinfo, jwks). With `-backchannel-dynamic=true` the backchannel URLs are
derived from the proxy's `X-Forwarded-Port` (kc-proxy's internal `8443`), so a **mobile** OIDC client
(which does the token exchange itself, following discovery) POSTs to `https://<HOST_IP>:8443/...token`
— the wrong port (and, if another service occupies it, an untrusted cert → `Trust anchor not found`).
Setting it `false` makes token/userinfo/jwks use `KC_HOSTNAME` too. The backend is unaffected (it
validates with the explicit internal `OIDC_JWKS_URL`, not the discovery doc).

App build (Envied is compile-time) — gotchas proven live:
- **Env comes from the process environment, not `.env`** for this container build; pass values via `-e`
  AND run `dart run build_runner clean` first, else stale generated `*_env.g.dart` keeps `firebase`:
  `-e AUTH_BACKEND=oidc -e OIDC_ISSUER=https://<ip>:8443/realms/omi -e OIDC_CLIENT_ID=omi-app -e OIDC_REDIRECT_SCHEME=omiauth -e API_BASE_URL=https://<ip>:8444/`
- Firebase config is gitignored but **required even under OIDC** (`Firebase.initializeApp` runs
  unconditionally): provide `app/lib/firebase_options_{dev,prod}.dart` + `app/android/app/src/{dev,prod}/google-services.json`.
- Build image: `deploy/onprem/Dockerfile.appbuild` (self-contained: JDK 21 + Android SDK 36 + NDK); emulator:
  `deploy/onprem/Dockerfile.emulator` (budtmo). Build APK: `flutter build apk --debug --flavor dev`.
- Device trust: install `certs/ca.crt` as a **user** CA (real devices rarely allow a system CA); the
  debug `network_security_config.xml` trusts user CAs so both Chrome (authorize) and AppAuth (token) validate.
- After changing the compiled env, **uninstall + reinstall** (`adb install -r` alone can keep the old build).

Full E2E proven (2026-08-02, emulator): `Sign in with SSO` → Keycloak login (https, self-signed CA trusted)
→ redirect → token exchange → **refresh token in Keychain/Keystore, not prefs** → force-stop/relaunch keeps
the session → backend `saveToken {"status":"Ok"}`, `GET /v1/users/me/subscription 200`, `POST /v1/users/fcm-token 200`.

## Push notifications (UnifiedPush/ntfy) — ADR-0011

Remote push is the one allowed cloud dependency, behind `PUSH_NOTIFICATION_BACKEND`:
- `fcm` (**the code's default**) — Firebase Cloud Messaging / APNs. Needs Firebase.
- `disabled` — no remote push at all. The backend runs fully and sends nothing; the app shows only
  its own local notifications. Nothing else to deploy. **This is what `backend.env.base` declares**, because
  the ntfy server is opt-in — and because the flag being *undeclared* meant the flag was effectively set to
  the cloud value (measured: `resolve_push_backend()` answered `fcm` on this stack, ADR-0071).
- `unifiedpush` — self-hosted push via [ntfy](https://ntfy.sh), no Google. Bring the server up with
  the `push` profile.

**The two UnifiedPush variables are a PAIR.** `UNIFIEDPUSH_INTERNAL_BASE_URL` is required by the transport:
the stored endpoint is user-registered, so POSTing to it verbatim would be an SSRF primitive, and
`_target_url` refuses. Setting the backend without the base URL used to give a deployment that reported
`unifiedpush`, passed readiness, and lost **100% of notifications** with one ERROR log per endpoint. It now
resolves to `disabled` with `omi_fallback_total{component="push",reason="config_incomplete"}` and an explicit
line at boot:

```
STARTUP: PUSH_NOTIFICATION_BACKEND=unifiedpush but UNIFIEDPUSH_INTERNAL_BASE_URL is not set — no push
notification will be delivered ...
```

**Payload size: hex-armor doubles the body** (ADR-0073). The ciphertext is hex-encoded because ntfy is
text-only, so a payload sized for FCM's 4 KB is ~8 KB on the wire — measured, the 100-id bulk action-item
delete is 3850 B of plaintext and **7906 B posted**. ntfy's own `message-size-limit` defaults to **4096** and
treats an over-limit body as an attachment, so it answers `400 invalid request: attachments not allowed` and
the notification is gone. `NTFY_MESSAGE_SIZE_LIMIT=16384` is therefore declared on both targets (compose
service + Helm StatefulSet), and a static test requires the declared value to be ≥ 7906 on each.

Verify it on the running stack:

```bash
docker compose -f compose.prod.yaml exec ntfy sh -c 'echo $NTFY_MESSAGE_SIZE_LIMIT'   # -> 16384
docker compose -f compose.prod.yaml exec backend /opt/venv/bin/python -c "
import urllib.request, urllib.error
for n in (7906, 15684, 16385):
    req = urllib.request.Request('http://ntfy:80/probe', data=b'a'*n, headers={'Content-Type':'text/plain'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: print(n, '->', r.status)
    except urllib.error.HTTPError as e: print(n, '->', e.code)"
# expected: 7906 -> 200 · 15684 -> 200 · 16385 -> 400
```

A 4xx that is not 404/410 is now recorded as `component=push to=dropped reason=capability_mismatch
outcome=exhausted` instead of being filed as transient — which matters because the Apple-Reminders sync
payload is **not chunked at all** and exceeds even FCM's 4 KB at ~30 items: upstream's bound on both
transports, so beyond ~50 items the only thing we can offer is the signal.

```bash
cd deploy/onprem
# backend.env: PUSH_NOTIFICATION_BACKEND=unifiedpush + UNIFIEDPUSH_INTERNAL_BASE_URL=http://ntfy:80
docker compose -f compose.prod.yaml --profile push up -d           # ntfy (internal) + ntfy-proxy (TLS on NTFY_HTTPS_PORT)
```

`ntfy` stays **internal** (on `omi` only); only the TLS reverse proxy `ntfy-proxy` is on `edge` with a
published https port — exactly the api-proxy/kc-proxy posture. The ntfy Android distributor refuses a
cleartext server, so it must point at the proxy's https URL (`https://<HOST_IP>:${NTFY_HTTPS_PORT}`,
cert from `gen-dev-certs.sh`, SAN=HOST_IP).

**Addressing (why UNIFIEDPUSH_INTERNAL_BASE_URL exists).** The phone's UnifiedPush distributor
registers with the server on its **host-facing** URL (`NTFY_BASE_URL = https://<HOST_IP>:${NTFY_HTTPS_PORT}`)
and hands the app an endpoint like `https://<HOST_IP>:${NTFY_HTTPS_PORT}/<topic>?up=1`, which the app
saves to the backend (`POST /v1/users/unifiedpush-endpoint`). That stored URL is the **phone-facing**
`<HOST_IP>:${NTFY_HTTPS_PORT}` address (split-horizon); the backend reaches the same ntfy by its internal
service name, so it keeps only the endpoint's *path* and POSTs to `${UNIFIEDPUSH_INTERNAL_BASE_URL}${path}`
= `http://ntfy:80/<topic>?up=1`, reaching the same server by service name. **`UNIFIEDPUSH_INTERNAL_BASE_URL` is REQUIRED and fail-closed** (cubic
review PR 10887): the registered endpoint is user-controlled, so POSTing to it verbatim would be an
SSRF primitive — with the base unset the backend refuses to send that endpoint rather than fetching a
user-supplied URL.

**Flow:** app registers → `onNewEndpoint` → the app generates a WebPush key set, saves the endpoint
**plus its `p256dh`/`auth`** to the backend → backend builds the notification JSON
(`{notification?, data, tag, priority, is_background}`), **encrypts it for that key set (WebPush
RFC 8291, aes128gcm) and hex-encodes the ciphertext**, then POSTs the hex text to the endpoint → ntfy
delivers it to the distributor → the app **hex-decodes and decrypts** it and shows the notification
(same dispatch it runs for an FCM message). Dead endpoints (HTTP 404/410) are dropped from
`unifiedpush_endpoints`. An endpoint that registered no keys (legacy client) gets a plaintext JSON POST.

**Why hex, not raw binary.** ntfy is a text transport: it turns any non-UTF8 body into an *attachment*
(rejected unless attachment storage is enabled, and then delivered as a download URL, not bytes). So
the backend armors the aes128gcm ciphertext as a lowercase-hex UTF-8 string; the app reverses it. The
UnifiedPush connector's own native decryption can't apply here (it needs raw aes128gcm and hides the
private key), so the app owns the key set and decrypts via the `webpush_encryption` package — the same
reference impl the connector uses internally. Backend uses `http-ece`.

**Debt:** message durability across distributor reconnects uses ntfy's default in-memory cache (add
`NTFY_CACHE_FILE` + a volume to harden).

### Full app E2E (emulator + ntfy distributor) — proven 2026-08-03

The whole flow runs on the compose dev stack, same posture as the OIDC E2E: the app reaches the
backend ONLY through `api-proxy` https, ntfy through `ntfy-proxy` https, self-signed CA trusted on
the device. Prereqs:
- App built with `NOTIFICATIONS_BACKEND=unifiedpush` + `API_BASE_URL=https://<HOST_IP>:${API_HTTPS_PORT}/`.
- ntfy Android app installed as the distributor, its **Default server** set to
  `https://<HOST_IP>:${NTFY_HTTPS_PORT}` (Settings → Default server; persisted as `DefaultBaseURL`).
- The self-signed CA installed on the device **via Settings** (Encryption & credentials → Install a
  CA certificate). A raw `adb push` into `cacerts-added` is trusted by Chrome but NOT by AppAuth's
  token exchange — the KeyChain registration the Settings flow does is what `<certificates src="user"/>`
  needs. (Needs a screen-lock PIN.)
- Keycloak must advertise the **token endpoint on the public issuer port** — see the backchannel note
  in the OIDC section. Otherwise the mobile token exchange goes to the internal proxy port and fails.

Proven flow (logs verbatim):
1. Launch → `UnifiedPush notification service initialized` (no FCM background handler).
2. Sign in with SSO (testuser) → token exchange succeeds; `registerApp` → the ntfy distributor issues
   `onNewEndpoint: https://<HOST_IP>:${NTFY_HTTPS_PORT}/<topic>?up=1` → `saveUnifiedPushEndpoint:
   {"status":"Ok"}` (`POST /v1/users/unifiedpush-endpoint` 200).
3. Backend send for that uid → POSTs to `http://ntfy:80/<topic>` (rewritten from the stored host-facing
   endpoint) → ntfy delivers to the distributor → `UnifiedPushReceiver: OnMessage` → the app decodes
   the JSON and **shows the notification** (same dispatch as FCM). Payload received matches the sent
   `{notification:{title,body}, data, tag, priority, is_background}`.

## Data seed (5 users, MELD/Friends, via the backend REST API)

Populate a realistic multi-user dataset by driving the **backend HTTP API as real app users would**
(OIDC-authenticated, on-device-transcription path) — no raw DB writes. Every conversation goes through
`POST /v1/conversations/from-segments`, so the full product pipeline runs (structured summary + action
items + memories + knowledge graph + Qdrant vectors). Seeder: `deploy/onprem/seed/seed_meld_users.py`.

Why MELD (Friends): multi-party dialogue with NAMED, recurring speakers (Ross, Rachel, Monica, …), which
maps 1:1 onto Omi's identified-person model (segment `person_id` → `Person(name)`). MELD is **not
committed** (TV-derived, research-use only) — the seeder's header shows how to download `train_sent_emo.csv`.

Dedicated declarative config (per ADR-0043, layered over the common base):
- `compose.seed.yaml` — dev-posture (backend reaches HOST inference via `host.docker.internal`) **plus**
  real OIDC auth (`AUTH_BACKEND=oidc`, `LOCAL_DEVELOPMENT=false`) so multiple Keycloak users drive the API.
- `backend.env.seed(.example)` — OIDC issuer/JWKS + admin-API client (user-name resolution) +
  `STORAGE_BACKEND=mongo` (real on-prem store, no Google) + Qdrant + host embeddings (`bge-m3`).

Prerequisites:
- Keycloak realm `omi` up: the seed posture mounts the DEV realm `keycloak/omi-realm.dev.example.json`
  (auto-imported via `--import-realm`), which ships the public direct-access client (`omi-test`) **and**
  the confidential service-account client (`omi-backend-admin`, realm-management `view-users` role) for
  `OIDC_ADMIN_*` (resolves the user's display name used in memory attribution). The prod realm
  (`omi-realm.example.json`) omits `omi-test`/`testuser` (review #5). The client's DEV secret is in the
  realm JSON and in `backend.env.seed(.example)` — they must match; regenerate a strong secret for production.
- Backend reachable at `--api-url`, validating the same issuer's JWKS. Mongo (`STORAGE_BACKEND=mongo`).
- Operator LLM (chat, e.g. `qwen2.5:14b` via the gateway) + a 1024-dim embeddings model (`bge-m3`).
- **`OLLAMA_NUM_PARALLEL=1`** is NOT required, but on a single small GPU concurrent chat + embeddings
  can `cudaMalloc`-OOM; the seeder paces one conversation at a time (`api_wait_enriched`) to stay serial.

Run (bring up auth + chat + mongo, then seed):
```
./gen-dev-certs.sh                                                     # once: TLS for the proxies
docker compose -f compose.seed.yaml --profile auth --profile chat up -d
deploy/onprem/seed/seed_meld_users.py --meld-csv train_sent_emo.csv \
    --api-url http://localhost:8000 --kc-url https://<LAN_IP>:<KC_HTTPS_PORT> --per-user 20
```
Each user gets a fact-rich "profile" conversation first (explicit personal facts → real memories; MELD
banter alone yields almost none), then their MELD dialogues (other named speakers become identified People).

Produces (validated live on real Mongo, `--per-user 4`): conversations + memories (all users) + action
items + People + knowledge graph + Qdrant vectors (`omi_ns1` conv, `omi_ns2` memory, `omi_ns4` action).
Memories are encrypted at rest. RAG payoff verified end-to-end (`/v2/messages` retrieves a seeded memory
via `search_memories_tool` and answers from it).

Gotcha — **never wipe Qdrant with `curl -X DELETE` while the backend is running**: the adapter caches
which collections exist (`utils/vector/adapters/qdrant.py::_ensured`, per-process, not invalidated on an
external delete), so subsequent upserts hit a 404 and are swallowed by the fire-and-forget postprocess →
vectors silently missing. To reset cleanly: `docker compose -f compose.seed.yaml down` (or restart the
backend container) so the cache is empty, then re-seed.

## Git notes

Work happens on the `fullonprem` branch (ADR-0013). `backend.env` is ignored (`*.env`); the
committed files are the `backend.env.*.example`, the `compose.{base,prod,dev,seed}.yaml`, the Dockerfiles and this file.
Remotes are reconciled (fork-based): `git push` targets `origin` (fork `abunet/omi`); `upstream`
(`BasedHardware/omi`) is integrated inbound only. Push only after explicit sign-off.
