# Omi Backend — One-Click Deployment

Self-host the omi backend with a single command using Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20.10+
- Docker Compose v2 (plugin) or v1 (standalone)
- API credentials listed below

## Required API Keys

| Service | Purpose | Sign up |
|---------|---------|---------|
| Firebase / GCP | Auth, Firestore DB, Storage | [console.firebase.google.com](https://console.firebase.google.com) |
| OpenAI | AI chat and processing | [platform.openai.com](https://platform.openai.com) |
| Deepgram | Audio transcription | [console.deepgram.com](https://console.deepgram.com) |
| Pinecone | Vector memory search | [app.pinecone.io](https://app.pinecone.io) |

**Redis** and **Typesense** run locally inside Docker — no external accounts needed.

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/BasedHardware/omi.git
cd omi/backend

# 2. Configure your API keys
cp .env.docker .env.docker
# Edit .env.docker — fill in SERVICE_ACCOUNT_JSON, OPENAI_API_KEY,
# DEEPGRAM_API_KEY, PINECONE_API_KEY, and GCP bucket names

# 3. Deploy
bash scripts/install.sh
```

## Manual Start

```bash
cd omi/backend
docker compose -f docker-compose.yaml up -d --build

# Verify
curl http://localhost:8080/v1/health
# Expected: {"status":"ok"}
```

## Services

| Service | Port | Notes |
|---------|------|-------|
| Backend API | 8080 | FastAPI application |
| Redis | 6379 | Persistent session cache |
| Typesense | 8108 | Full-text search index |

## Architecture

```
docker compose up (run from omi/backend/)
      │
      ├── backend:8080   ← FastAPI
      │     ├── build context = repo root (../), dockerfile = backend/Dockerfile
      │     ├── env loaded from .env.docker
      │     ├── REDIS_DB_HOST=redis, REDIS_DB_PORT=6379
      │     └── TYPESENSE_HOST=typesense, TYPESENSE_HOST_PORT=8108
      ├── redis:6379      ← Persistent (appendonly yes)
      └── typesense:8108  ← Search (local_typesense_key)
```

## Common Commands

```bash
# View backend logs
docker compose -f docker-compose.yaml logs -f backend

# Stop all services
docker compose -f docker-compose.yaml down

# Full reset (removes volumes)
docker compose -f docker-compose.yaml down -v

# Rebuild after code changes
docker compose -f docker-compose.yaml up -d --build
```

## Troubleshooting

**Health check:** The correct endpoint is `/v1/health` (not `/health`):
```bash
curl http://localhost:8080/v1/health
# → {"status":"ok"}
```

**Build fails:** Run `docker compose` from inside `omi/backend/` — the build context
is set to `..` (repo root) which is required by `backend/Dockerfile`.

**Backend exits on startup:** Check logs with `docker compose -f docker-compose.yaml logs backend`.
Usually a missing env var. Confirm `SERVICE_ACCOUNT_JSON` and `OPENAI_API_KEY` are set in `.env.docker`.

**Redis not connecting:** Ensure `.env.docker` has `REDIS_DB_HOST=redis` and `REDIS_DB_PORT=6379`
(not `REDIS_URL` — that variable is not read by the omi backend).
