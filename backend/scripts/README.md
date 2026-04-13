# Omi Backend — One-Click Deployment

Self-host the omi backend on your own hardware with a single command.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/install/) v2 (plugin) or v1 (standalone)
- The following API credentials (see table below)

## Required API Keys

| Service | Used for | Get it at |
|---------|----------|-----------|
| Firebase / GCP | Auth, Firestore, Storage | [console.firebase.google.com](https://console.firebase.google.com) |
| OpenAI | AI features, chat | [platform.openai.com](https://platform.openai.com) |
| Deepgram | Audio transcription | [console.deepgram.com](https://console.deepgram.com) |
| Pinecone | Vector memory search | [app.pinecone.io](https://app.pinecone.io) |

Redis and Typesense run locally in Docker — no external accounts needed.

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/BasedHardware/omi.git
cd omi/backend

# 2. Fill in your API keys
cp .env.docker .env.docker.local
# Edit .env.docker.local — at minimum set:
#   SERVICE_ACCOUNT_JSON, OPENAI_API_KEY, DEEPGRAM_API_KEY, PINECONE_API_KEY

# 3. Run
bash scripts/install.sh
```

## Manual Start (without install script)

```bash
cd omi/backend
cp .env.docker .env.docker.local
# Edit .env.docker.local with your keys

docker compose -f docker-compose.yaml up -d --build

# Verify it's running
curl http://localhost:8080/v1/health
# Expected: {"status":"ok"}
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Backend API | 8080 | FastAPI application |
| Redis | 6379 | Session cache (persistent) |
| Typesense | 8108 | Full-text search |

## Architecture

```
docker compose up
      │
      ├── backend:8080    ← FastAPI (built from repo root Dockerfile)
      │     ├── reads .env.docker for all credentials
      │     ├── connects to redis:6379 (REDIS_DB_HOST/PORT/PASSWORD)
      │     └── connects to typesense:8108
      ├── redis:6379       ← Persistent (appendonly)
      └── typesense:8108   ← Search index
```

## Common Commands

```bash
# View logs
docker compose -f docker-compose.yaml logs -f backend

# Stop all services
docker compose -f docker-compose.yaml down

# Stop and remove volumes (full reset)
docker compose -f docker-compose.yaml down -v

# Rebuild after code changes
docker compose -f docker-compose.yaml up -d --build
```

## Troubleshooting

**Build fails with "COPY backend/ ." error**  
Make sure you're running `docker compose` from inside the `backend/` directory. The build context is set to the repo root (`..`).

**Backend exits immediately**  
Check logs: `docker compose -f docker-compose.yaml logs backend`  
Usually means a required env var is missing. Verify `.env.docker` has `SERVICE_ACCOUNT_JSON` and `OPENAI_API_KEY` set.

**Health check fails**  
The correct endpoint is `/v1/health` (not `/health`):
```bash
curl http://localhost:8080/v1/health
```

**Redis connection refused**  
Confirm `REDIS_DB_HOST=redis` and `REDIS_DB_PORT=6379` in `.env.docker` (not `REDIS_URL`).
