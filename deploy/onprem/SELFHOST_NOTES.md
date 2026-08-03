# SELFHOST_NOTES — WP0: containerized offline baseline

Runbook + deviations log to **boot and serve the Omi backend offline**, with no cloud
dependencies. It is the first brick of the full-on-prem initiative (ADR-0001) and the seed of the
self-host deployment (later WPs add services to the same compose).

> Project docs location: the ADRs and the architecture brief live under `/work/omi/docs/`
> (outside the `src/omi` source tree). This file instead lives in the source because it is the
> operational runbook for the compose stack.

## What the baseline contains (WP0)

Three services (`deploy/onprem/docker-compose.yml`), network **`internal: true`** (no egress):

| Service | Image / build | Role |
|---|---|---|
| `backend` | built from `backend/Dockerfile` (base image override, see below) | FastAPI `main:app`, uvicorn :8080 |
| `firestore-emulator` | built from `deploy/onprem/firestore-emulator/Dockerfile` | Firestore :8085 + Auth :9099 emulators |
| `valkey` | `valkey/valkey:8-alpine` | cache/queue (wire-compatible with `redis-py`) |

Out of WP0 scope (added in later WPs): Pusher, Typesense, Mongo/ArcadeDB, Qdrant,
RustFS/SeaweedFS, Keycloak, GPU inference.

## Prerequisites

Only **Docker** (with Compose v2) on the host. No java/node/redis/firebase-CLI to install:
everything is in the containers. The **build** needs internet access (see Deviations #2); the
**runtime** does not.

## Usage

```bash
cd deploy/onprem

# 1. create the env file with a real secret (backend.env is gitignored by *.env)
cp backend.env.example backend.env
sed -i "s/^ENCRYPTION_SECRET=.*/ENCRYPTION_SECRET=$(openssl rand -hex 32)/" backend.env

# 2. build + up (hermetic posture by default: no egress)
docker compose up -d --build
docker compose ps            # the 3 services must become 'healthy'

# logs / stop
docker compose logs -f backend
docker compose down          # add -v to wipe emulator/valkey data
```

## Verification (WP0 acceptance)

The network is `internal` -> no published port: test from **inside** the containers.

```bash
# 1) the backend responds (no auth)
docker compose exec -T backend curl -fsS http://localhost:8080/v1/health
#    expected: {"status":"ok"}

# 2) end-to-end auth + Firestore emulator round-trip (verified)
docker compose exec -T backend curl -sS -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/v3/memories -H 'Authorization: Bearer dev-token'
#    expected: 200 (LOCAL_DEVELOPMENT=true -> Bearer dev-token = uid 123; reads from the emulator)
docker compose exec -T backend curl -sS -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/v3/memories
#    expected: 401 (auth enforced)

# 3) HERMETICITY PROOF: no egress to the internet
docker compose exec -T backend sh -c 'curl -m3 https://api.openai.com/v1/models; echo "exit=$?"'
#    expected: FAILURE ("Could not resolve host", exit 6) -> zero external calls by construction
```

### Curl from the host (dev convenience, accepts egress)

The hermetic posture publishes no ports. To poke the endpoints from the host:

```bash
docker compose -f docker-compose.yml -f docker-compose.expose.override.yml up -d
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
`/v1/chat/completions` and `/v1/embeddings`, so a single URL covers chat and embeddings. Wire it
in `backend.env`:

```
# chat
OMI_LLM_GATEWAY_FEATURE_MODE=gateway
OMI_LLM_GATEWAY_URL=http://<ollama-host>:11434/v1
# embeddings (the one hard-cloud gap, now pointable)
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
  -v $PWD/../..:/repo -w /repo/backend omi-onprem-backend-test:v2 \
  python -m pytest tests/contract/test_embeddings_live_contract.py -q -p no:cacheprovider
# expected: 3 passed  (real vector, correct dim, deterministic, no OpenAI/Google egress)
```

Full on-prem semantic search round-trip (embeddings + vector store together — Qdrant on loopback):

```
docker run -d --name qdrant --network host qdrant/qdrant:latest    # 127.0.0.1:6333
docker run --rm --network host \
  -e OMI_EMBEDDINGS_BASE_URL=http://127.0.0.1:11434/v1 -e OMI_EMBEDDINGS_MODEL=bge-m3 \
  -e VECTOR_STORE_BACKEND=qdrant -e QDRANT_URL=http://127.0.0.1:6333 -e QDRANT_VECTOR_DIM=1024 \
  -v $PWD/../..:/repo -w /repo/backend omi-onprem-backend-test:v2 \
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
  -v $PWD/../..:/repo -w /repo/backend omi-onprem-backend-test:v2 \
  python -m pytest tests/contract/test_translation_nllb_live_contract.py -q -p no:cacheprovider
# expected: 4 passed  (en->it/fr/es real translations + en->it->en round-trip via TranslationService)
```

Live speaker embedding through the backend path against a running diarizer. The pyannote models are
gated: use an `HUGGINGFACE_TOKEN` whose account has accepted the licenses of `pyannote/embedding`,
`pyannote/wespeaker-voxceleb-resnet34-LM` and `pyannote/speaker-diarization-community-1` (visit each
model page once and click *Agree and access*). Then:

```
# Build the slim on-prem image (skips the redundant system CUDA — see "Diarizer image is slimmed" below):
docker build -f backend/diarizer/Dockerfile -t omi-diarizer:onprem-lean \
  --build-arg PYTHON_BASE_IMAGE=python:3.11-slim --build-arg INSTALL_SYSTEM_CUDA=0 .
docker run -d --name diarizer --network host --device nvidia.com/gpu=all \
  -e HUGGINGFACE_TOKEN=hf_xxx -e HF_HOME=/models/hf -v $MODELS:/models omi-diarizer:onprem-lean
docker run --rm --network host -e HOSTED_SPEAKER_EMBEDDING_API_URL=http://127.0.0.1:8080 \
  -v $PWD/../..:/repo -w /repo/backend omi-onprem-backend-test:v2 \
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
  -e WER_MAX_SAMPLES=10 -v $CACHE:/cache -v $PWD/../..:/repo -w /repo/backend omi-onprem-backend-test:v2 \
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

**On-prem multilingual live STT (REQUIRED — tracked as a debt):** replace Modulate with the
multilingual self-hosted model **`parakeet-1.1b-rnnt-multilingual`** (available via NVIDIA NIM;
`backend/parakeet/Dockerfile.nim` already targets `nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual`).
This needs a backend **policy update** in `config/stt_provider_policy.py`
(`PARAKEET_MODEL_BY_SURFACE[STREAMING]` + `PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL`) to register the
multilingual model and its languages. Deepgram-self-hosted is the other policy-enabled streaming option.

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
docker compose --profile inference up -d --build
```

Once the profile is up (and model weights are provisioned into the volume), run all three
backend live tests against the running compose services in one shot — the reproducible,
committed form of the per-service recipes below:

```
deploy/onprem/run-inference-live-tests.sh            # diarizer + nllb + parakeet
# expected: diarizer PASS · nllb PASS · parakeet PASS
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
- **Models are pre-provisioned, not downloaded at runtime.** The `omi` network is `internal: true`
  (no egress) — the proof of "zero external calls". Populate the `inference-models` volume before the
  first `--profile inference` run:
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
  `backend.env.example`). Verified 2026-08-03 on the RTX 5060 Ti: an Italian FLEURS clip →
  `parakeet` gateway → `whisper` → correct Italian transcription with auto-detected language, via
  `deploy/onprem/run-inference-live-tests.sh` (diarizer PASS · nllb PASS · whisper PASS).
- Point the backend at them in `backend.env`: `HOSTED_PARAKEET_API_URL=http://parakeet:8080`,
  `HOSTED_SPEAKER_EMBEDDING_API_URL=http://diarizer:8080`,
  `HOSTED_TRANSLATION_API_URL=http://nllb:8080` + `TRANSLATION_SERVICE_MODELS=nllb`.

## Testing the backend offline

The box has only Docker (no host venv). Suites run in a **test image** = the WP0 backend image plus
additive test-only tooling (`git`, `helm`, and test Python deps). The image is reproducible from the
committed [`Dockerfile.test`](Dockerfile.test):

```bash
cd deploy/onprem
docker compose build                                            # WP0 images (once)
docker build -t omi-onprem-backend-test -f Dockerfile.test .    # test image
```

### Mount the REPO ROOT, not just `backend/`

A large set of contract tests resolve repo-root paths via `Path(__file__).resolve().parents[N]` and
read `.github/`, `docs/`, `firestore.indexes.json`, `desktop/`, helm charts, etc. Mounting only
`backend/` at `/app` flattens the tree so those walks overshoot to `/` and raise `FileNotFoundError`.
Mount the **whole repo** so `backend/` sits at its real depth:

```
-v $(git rev-parse --show-toplevel):/repo -w /repo/backend
```

Do **not** set `OMI_ENV_STAGE=offline` for the unit sweep: that variable is for the runtime compose
posture, and forcing it makes a couple of tests assert the wrong environment/stage. `LOCAL_DEVELOPMENT=true`
is the signal the unit suite expects. (See the two known residuals at the end.)

### Run one suite — FILE-ISOLATED (mandatory)

The suite carries module-level state (`load_module_fresh`, monkeypatched clients, singletons), so
**more than one test file per `pytest` process cross-contaminates `sys.modules` -> false failures.**
Run **one process per file**:

```bash
docker run --rm -v $(git rev-parse --show-toplevel):/repo -w /repo/backend \
  -e ENCRYPTION_SECRET="$(openssl rand -hex 32)" -e OPENAI_API_KEY=test \
  -e PYTHONUTF8=1 -e OMP_NUM_THREADS=1 -e LOCAL_DEVELOPMENT=true \
  omi-onprem-backend-test /opt/venv/bin/python -m pytest -q -o addopts="" tests/unit/<file>.py
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
  omi-onprem-backend-test bash -c '
    ls tests/unit/test_*.py tests/unit/utils/test_*.py testing/e2e/test_*.py | \
    xargs -P 16 -I{} sh -c '\''out=$(/opt/venv/bin/python -m pytest -q -o addopts="" -p no:cacheprovider "{}" 2>&1 | tail -1);
      echo "$out" | grep -qiE "failed|error" && echo "FAIL | {} | $out" || echo "PASS | {} | $out"'\'' '
```

Include `testing/e2e/test_*.py` in the glob: port residuals (`db_client=`, changed signatures) survive
in E2E suites that a `tests/unit`-only sweep never runs — two such residuals shipped past earlier
audits before this was added (ADR-0040 rule 7).

**De-flake before trusting a FAIL.** Docker-per-file startup contention makes a high `-P` produce
false failures on a loaded box (observed: `-P 16` yielded ~90 false FAILs that all passed at `-P 3`).
Re-run the FAIL set at low parallelism (`-P 3`) and diff against a pre-change baseline worktree before
calling anything a regression.

With this harness the whole unit+e2e sweep is green except the known residuals below. To gate a
change, the FAIL set must equal that known-residual set; any other file failing is a regression to fix.

### Regression guard

```bash
python3 .github/scripts/check_firestore_persistence_boundary.py   # must exit 0 (0 violations)
```

Runs bare with stdlib `python3` (no venv). It enforces the WP1 boundary: only `database/` may touch
the raw Firestore client.

### Dual-backend contract test (adapter parity)

Proves the Firestore and Mongo adapters honor the same neutral contract against **real** services.
Mongo owns the network namespace; the emulator and the test container share it (`--network
container:`) so both services are on `localhost` and the hermetic loopback-only guard in
`tests/conftest.py` accepts them.

```bash
# 1. Mongo (single-node replica set)
docker run -d --name wp2-mongo mongo:latest --replSet rs0 --bind_ip_all
docker exec wp2-mongo mongosh --quiet --eval \
  "rs.initiate({_id:'rs0',members:[{_id:0,host:'127.0.0.1:27017'}]})"   # wait for isWritablePrimary
# 2. Firestore emulator in the same netns
docker run -d --name wp2-emu --network container:wp2-mongo omi-onprem-firestore-emulator:latest
# 3. Contract suite (same netns)
docker run --rm --network container:wp2-mongo -v $(git rev-parse --show-toplevel):/repo -w /repo/backend \
  -e FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 -e MONGO_URI="mongodb://127.0.0.1:27017/?replicaSet=rs0" \
  -e FIREBASE_PROJECT_ID=demo-omi-local -e GOOGLE_CLOUD_PROJECT=demo-omi-local \
  -e ENCRYPTION_SECRET="$(openssl rand -hex 32)" -e OPENAI_API_KEY=test \
  omi-onprem-backend-test /opt/venv/bin/python -m pytest -q -o addopts="" \
  tests/contract/test_document_store_contract.py
docker rm -f wp2-mongo wp2-emu    # cleanup
```

Note: gRPC (Firestore) bypasses the Python socket guard; pymongo uses Python sockets but on loopback,
which the guard permits.

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
  -e S3_ENDPOINT=http://127.0.0.1:9000 -e S3_ACCESS_KEY=testkey -e S3_SECRET_KEY=testsecret -e S3_REGION=us-east-1 \
  -e STORAGE_EMULATOR_HOST=http://127.0.0.1:4443 \
  omi-onprem-backend-test -m pytest -q tests/contract/test_object_store_contract.py
# expected: 33 passed, 1 skipped (presign_get[gcs]: fake-gcs-server has no signing key; GCS V4
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
  omi-onprem-backend-test -m pytest -q tests/contract/test_vector_store_contract.py
# expected: 24 passed, 12 skipped
docker rm -f vc-qdrant    # cleanup
```

### Auth contract test (adapter parity)

Proves the OIDC adapter validates a real provider's token to the same neutral Principal as the fake
(ADR-0034). The `fake` backend always runs; `oidc` runs against a real Keycloak on `--network host`
(loopback); `firebase` is skipped unless a firebase emulator is wired (the fake is the reference).

```bash
# 1. Keycloak + a realm/client/user (see the WP3 handoff for the full curl provisioning)
docker run -d --name kc-contract --network host \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.0 start-dev --http-port=8080     # wait: curl 127.0.0.1:8080/realms/master -> 200
# ... provision realm 'omi' + public direct-access client 'omi-test' + user 'testuser' via the Admin API ...
# 2. Contract suite (mints a token via the password grant, verifies via the adapter's JWKS)
docker run --rm --network host -v $(git rev-parse --show-toplevel)/backend:/app -w /app \
  -e OIDC_ISSUER=http://127.0.0.1:8080/realms/omi \
  -e OIDC_JWKS_URL=http://127.0.0.1:8080/realms/omi/protocol/openid-connect/certs \
  -e OIDC_TEST_TOKEN_URL=http://127.0.0.1:8080/realms/omi/protocol/openid-connect/token \
  -e OIDC_TEST_CLIENT_ID=omi-test -e OIDC_TEST_USERNAME=testuser -e OIDC_TEST_PASSWORD=testpass \
  omi-onprem-backend-test -m pytest -q tests/contract/test_auth_provider_contract.py
# expected: 5 passed, 4 skipped (firebase cases skipped — no emulator)
docker rm -f kc-contract    # cleanup
```

### Two known residual failures (not our code, not fixable via the harness)

With the harness above the offline unit sweep is green except two files, both pre-existing at the
branch-point and unrelated to the self-host work:

- `tests/unit/test_auto_dev_backend_scope.py` — one subtest extracts and executes the real
  `.github/workflows/gcp_backend_auto_dev.yml` scope step's bash against a temp git repo; the
  discrepancy is inside that CI workflow logic, not the backend.
- `tests/unit/test_ws_auth_handshake.py` — one subtest asserts WebSocket auth *enforcement* (empty
  bearer -> close 1008), which requires `LOCAL_DEVELOPMENT` unset. The unit sweep sets it because ~46
  other files rely on the dev-auth bypass; a single global env cannot satisfy both. The file passes
  in isolation with `LOCAL_DEVELOPMENT` unset.

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
docker compose --profile auth up -d --build     # keycloak(+kc-proxy https) + api-proxy(https) + backend + deps
```
`keycloak` runs http-only behind `kc-proxy` (TLS on `${KC_HTTPS_PORT}`, `--proxy-headers`); the API runs
behind `api-proxy` (TLS on `${API_HTTPS_PORT}`). The realm (`keycloak/omi-realm.example.json`) imports
`omi-app` (public PKCE, redirect `omiauth:/oidc-callback`) + `testuser`. **Issuer/JWKS split-horizon**
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
- `fcm` (default) — Firebase Cloud Messaging / APNs. Needs Firebase.
- `disabled` — no remote push at all. The backend runs fully and sends nothing; the app shows only
  its own local notifications. Nothing else to deploy.
- `unifiedpush` — self-hosted push via [ntfy](https://ntfy.sh), no Google. Bring the server up with
  the `push` profile.

```bash
cd deploy/onprem
# backend.env: PUSH_NOTIFICATION_BACKEND=unifiedpush + UNIFIEDPUSH_INTERNAL_BASE_URL=http://ntfy:80
docker compose --profile push up -d           # ntfy (internal) + ntfy-proxy (TLS on NTFY_HTTPS_PORT)
```

`ntfy` stays **internal** (on `omi` only); only the TLS reverse proxy `ntfy-proxy` is on `edge` with a
published https port — exactly the api-proxy/kc-proxy posture. The ntfy Android distributor refuses a
cleartext server, so it must point at the proxy's https URL (`https://<HOST_IP>:${NTFY_HTTPS_PORT}`,
cert from `gen-dev-certs.sh`, SAN=HOST_IP).

**Addressing (why UNIFIEDPUSH_INTERNAL_BASE_URL exists).** The phone's UnifiedPush distributor
registers with the server on its **host-facing** URL (`NTFY_BASE_URL = https://<HOST_IP>:${NTFY_HTTPS_PORT}`)
and hands the app an endpoint like `https://<HOST_IP>:${NTFY_HTTPS_PORT}/<topic>?up=1`, which the app
saves to the backend (`POST /v1/users/unifiedpush-endpoint`). The backend sits on the **internal**
`omi` network (no egress) and cannot reach that host address — so it keeps only the endpoint's *path*
and POSTs to `${UNIFIEDPUSH_INTERNAL_BASE_URL}${path}` = `http://ntfy:80/<topic>?up=1`, reaching the
same server by service name.

**Flow:** app registers → `onNewEndpoint` → saves endpoint to backend → backend POSTs the
notification JSON (`{notification?, data, tag, priority, is_background}`) to the endpoint → ntfy
delivers it to the distributor → the app decodes it and shows the notification (same dispatch it
runs for an FCM message). Dead endpoints (HTTP 404/410) are dropped from `unifiedpush_endpoints`.

**Debt:** the POST body is plaintext — WebPush (aes128gcm) payload encryption is not implemented; use
a UnifiedPush connector that delivers raw bytes. Message durability across distributor reconnects
uses ntfy's default in-memory cache (add `NTFY_CACHE_FILE` + a volume to harden).

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

## Git notes

Work happens on the `fullonprem` branch (ADR-0013). `backend.env` is ignored (`*.env`); the
committed files are `backend.env.example`, the compose files, the Dockerfiles and this file. Until
the remotes are reconciled to a fork, `git push` is unavailable: commits stay local.
