# One-Click Omi Backend Deployment

Deploy the Omi backend locally with Docker in under 5 minutes.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2
- A Google Cloud Project with Firebase and Firestore enabled
- API keys for OpenAI and Deepgram (for LLM and STT)

## Quick Start

```bash
cd backend
bash scripts/install.sh
```

The install script will:
1. Check for Docker and Docker Compose
2. Create a `.env` file from the template
3. Prompt you for required API keys
4. Build and start all services
5. Wait for health checks to pass
6. Print the API docs URL

## Manual Setup

If you prefer to set up manually:

```bash
cd backend

# 1. Create your environment file
cp .env.docker .env

# 2. Edit .env and fill in your credentials:
#    - SERVICE_ACCOUNT_JSON (GCP service account, single-line JSON)
#    - FIREBASE_API_KEY, FIREBASE_PROJECT_ID
#    - OPENAI_API_KEY
#    - DEEPGRAM_API_KEY

# 3. Start all services
docker compose up -d

# 4. Check status
docker compose ps

# 5. View logs
docker compose logs -f backend
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| backend | 8080 | Omi API server (FastAPI/Uvicorn) |
| redis | 6379 | Cache, rate limiting, pub/sub |
| typesense | 8108 | Full-text search for conversations |

## Architecture

```
┌─────────────────────────────────┐
│         docker compose          │
│                                 │
│  ┌─────────┐  ┌───────┐        │
│  │ backend │──│ redis │        │
│  │  :8080  │  │ :6379 │        │
│  └────┬────┘  └───────┘        │
│       │       ┌───────────┐    │
│       └───────│ typesense │    │
│               │   :8108   │    │
│               └───────────┘    │
└─────────────────────────────────┘
         │
         ▼
  ┌──────────────┐
  │   Firestore  │  (external — your GCP project)
  │   GCS        │
  └──────────────┘
```

## Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SERVICE_ACCOUNT_JSON` | Yes | GCP service account JSON (single line) |
| `FIREBASE_API_KEY` | Yes | Firebase Web API key |
| `FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM |
| `DEEPGRAM_API_KEY` | Yes | Deepgram API key for STT |
| `ADMIN_KEY` | Dev only | Admin auth bypass (set to any value) |
| `ENCRYPTION_SECRET` | Yes | 32+ char secret for data encryption |

Redis and Typesense credentials are automatically configured by Docker Compose — no manual setup needed.

## Troubleshooting

**Backend won't start:**
```bash
docker compose logs backend  # Check for missing env vars
```

**Firebase auth errors:**
- Ensure `Cloud Resource Manager API`, `Firebase Management API`, and `Cloud Firestore API` are enabled in your GCP console
- Verify `SERVICE_ACCOUNT_JSON` is valid JSON on a single line

**Redis connection errors:**
- Redis is provided by Docker Compose — if it's not connecting, run `docker compose restart redis`

**Typesense search not working:**
- Default API key is `omi_typesense_dev_key` — override via `TYPESENSE_API_KEY` in `.env`

## Stopping

```bash
docker compose down          # Stop and remove containers
docker compose down -v       # Also remove data volumes
```
