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

## Git notes

Work happens on the `fullonprem` branch (ADR-0013). `backend.env` is ignored (`*.env`); the
committed files are `backend.env.example`, the compose files, the Dockerfiles and this file. Until
the remotes are reconciled to a fork, `git push` is unavailable: commits stay local.
