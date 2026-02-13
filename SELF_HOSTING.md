# Self-Hosting Omi Backend

Run the entire Omi backend locally with a single command using Docker Compose.

## Prerequisites

- **Docker Desktop** (with Docker Compose V2)
- **Python 3.9+** (for helper scripts)
- **OpenAI API key** (for LLM features)

## Quick Start

```bash
# 1. Create your local env file from the template
cp backend/.env.docker backend/.env.local

# 2. Add your OpenAI API key
#    Edit backend/.env.local and set OPENAI_API_KEY=sk-...

# 3. Run the one-click setup (auto-copies template if .env.local missing)
bash scripts/local_setup.sh

# Or manually:
docker compose up -d --build
python3 scripts/init_typesense.py
python3 scripts/seed_local.py
```

That's it. The backend will be available at `http://localhost:8080`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   docker compose                        │
│                                                         │
│  ┌──────────────┐  ┌───────┐  ┌───────────┐  ┌───────┐│
│  │   Firebase    │  │ Redis │  │ Typesense │  │Qdrant ││
│  │  Emulators    │  │       │  │           │  │       ││
│  │              │  │       │  │           │  │       ││
│  │ Firestore    │  │:6379  │  │  :8108    │  │:6333  ││
│  │ Auth         │  └───┬───┘  └─────┬─────┘  └───┬───┘│
│  │ Storage      │      │            │             │    │
│  │ UI :4000     │      │            │             │    │
│  └──────┬───────┘      │            │             │    │
│         │              │            │             │    │
│  ┌──────┴──────────────┴────────────┴─────────────┴──┐ │
│  │                  omi-backend                       │ │
│  │                  :8080                             │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | http://localhost:8080 | Main API |
| Firebase Emulator UI | http://localhost:4000 | Browse Firestore data, Auth users, Storage |
| Firestore | localhost:8081 | Database (mapped from internal 8080) |
| Firebase Auth | localhost:9099 | Authentication |
| Firebase Storage | localhost:9199 | File storage |
| Redis | localhost:6379 | Caching |
| Typesense | http://localhost:8108 | Full-text search |
| Qdrant | http://localhost:6333 | Vector search |
| Qdrant Dashboard | http://localhost:6334/dashboard | Qdrant web UI |

## Service Mapping

| Production Service | Local Replacement | Connection Method |
|---|---|---|
| Cloud Firestore | Firebase Emulator | `FIRESTORE_EMULATOR_HOST` env var — SDK auto-connects |
| Firebase Auth | Firebase Emulator | `FIREBASE_AUTH_EMULATOR_HOST` env var — SDK auto-connects |
| GCS Storage | Firebase Storage Emulator | `STORAGE_EMULATOR_HOST` env var — SDK auto-connects |
| Redis Cloud | `redis:7-alpine` container | Same protocol, drop-in replacement |
| Pinecone | `qdrant/qdrant` container | Adapter layer translates API calls |
| Typesense Cloud | `typesense/typesense:27.1` | Same API, HTTP instead of HTTPS |

## Environment Variables

All configuration is in `backend/.env.local` (copied from `backend/.env.docker`). Key variables:

### Required

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (for embeddings and LLM) |

### Pre-configured (no changes needed)

| Variable | Value | Description |
|----------|-------|-------------|
| `GOOGLE_CLOUD_PROJECT` | `demo-omi-local` | Firebase project (demo- prefix = offline mode) |
| `FIRESTORE_EMULATOR_HOST` | `firebase-emulator:8080` | Firestore emulator |
| `FIREBASE_AUTH_EMULATOR_HOST` | `firebase-emulator:9099` | Auth emulator |
| `STORAGE_EMULATOR_HOST` | `http://firebase-emulator:9199` | Storage emulator |
| `REDIS_DB_HOST` | `redis` | Redis container |
| `TYPESENSE_HOST` | `typesense` | Typesense container |
| `TYPESENSE_PROTOCOL` | `http` | HTTP for local (production uses HTTPS) |
| `QDRANT_HOST` | `qdrant` | Qdrant container |

### Optional (for additional features)

| Variable | Feature |
|----------|---------|
| `OPENROUTER_API_KEY` | Gemini models via OpenRouter |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `STRIPE_API_KEY` | Payments |
| `GITHUB_TOKEN` | GitHub integration |

## Testing

After setup, create a test user and make authenticated requests:

```bash
# Create test user (prints UID and token)
python3 scripts/seed_local.py

# Use the token from above
curl -H "Authorization: Bearer <token>" http://localhost:8080/v1/users/me
```

## Managing Services

```bash
# View logs
docker compose logs -f omi-backend
docker compose logs -f firebase-emulator

# Restart a service
docker compose restart omi-backend

# Stop everything
docker compose down

# Stop and remove all data
docker compose down -v

# Rebuild after code changes
docker compose up -d --build omi-backend
```

## Troubleshooting

### Backend won't start
- Check logs: `docker compose logs omi-backend`
- Ensure all dependencies are healthy: `docker compose ps`
- Verify `backend/.env.local` exists and has valid syntax

### Firebase emulator slow to start
- The emulator needs to download dependencies on first run. Give it 30-60 seconds.
- Check: `docker compose logs firebase-emulator`

### "OPENAI_API_KEY not set" warnings
- Edit `backend/.env.local` and add your OpenAI API key
- Rebuild: `docker compose up -d --build omi-backend`

### Port conflicts
- If port 8080 is in use, the backend maps to host port 8080. Stop any conflicting service or edit `docker-compose.yml` to change the port mapping.
- Firestore emulator is mapped to host port 8081 (internal 8080) to avoid conflicts with the backend.

### Typesense collection not found
- Run: `python3 scripts/init_typesense.py`

### Data persistence
- All data is stored in named Docker volumes (`firebase-data`, `redis-data`, `typesense-data`, `qdrant-data`)
- Data persists across `docker compose down` / `up` cycles
- To reset all data: `docker compose down -v`

## Limitations

- **Pusher (real-time transcription)**: Not included. Real-time streaming won't work locally. This is a planned Phase 2 addition.
- **Modal.com functions**: Modal decorators are no-ops when running via uvicorn directly. Modal-specific serverless functions won't execute.
- **Deepgram/Soniox STT**: Requires API keys from these services. Without them, speech-to-text won't work.
- **Google OAuth / Apple Sign-In**: Requires real OAuth credentials. The test user created by `seed_local.py` bypasses this for development.
