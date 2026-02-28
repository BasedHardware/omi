---
name: cloud
description: Manage Cloud Run backend deployment, logs, and configuration. Use when deploying backend, checking logs, troubleshooting 500 errors, updating environment variables, or managing GCP resources.
allowed-tools: Bash, Read
---

# Cloud Run Backend Management

Manage the OMI Desktop Rust backend deployed on Google Cloud Run.

## Configuration

| Setting | Value |
|---------|-------|
| **Project** | `based-hardware` |
| **Service** | `desktop-backend` |
| **Region** | `us-central1` |
| **Image** | `gcr.io/based-hardware/desktop-backend` |

### Service URLs

Both URLs point to the same service:
- `https://desktop-backend-hhibjajaja-uc.a.run.app`
- `https://desktop-backend-208440318997.us-central1.run.app`

## Quick Commands

### Check Health
```bash
curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/health
```

### View Logs
```bash
# Using the logs script (in scripts/ folder, not tracked)
scripts/logs.sh              # Last 30 logs
scripts/logs.sh 50           # Last 50 logs
scripts/logs.sh 20 error     # Last 20 logs containing "error"
scripts/logs.sh 100 conversation  # Logs about conversations

# Direct gcloud command
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=desktop-backend" \
    --project=based-hardware \
    --limit=30 \
    --format="table(timestamp.date('%H:%M:%S'),textPayload)"
```

### Check Environment Variables
```bash
gcloud run services describe desktop-backend \
    --project=based-hardware \
    --region=us-central1 \
    --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n'
```

## Deployment

### Full Redeploy (build + push + deploy)

**IMPORTANT**: Use `release.sh` for production deployments - it handles all env vars correctly.

For manual deploys, you MUST preserve env vars:
```bash
# Build for linux/amd64 (required for Cloud Run)
docker build --platform linux/amd64 -t gcr.io/based-hardware/desktop-backend:latest Backend-Rust/

# Push to GCR
docker push gcr.io/based-hardware/desktop-backend:latest

# Deploy to Cloud Run (preserves existing env vars with --no-traffic then migrate)
# WARNING: Using --set-env-vars will REPLACE all env vars. Always use release.sh instead.
gcloud run deploy desktop-backend \
    --image gcr.io/based-hardware/desktop-backend:latest \
    --project based-hardware \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated \
    --quiet
# NOTE: This command does NOT set env vars - they must already exist or be added separately
```

### Update Environment Variables Only
```bash
gcloud run services update desktop-backend \
    --project=based-hardware \
    --region=us-central1 \
    --update-env-vars="KEY=value" \
    --quiet
```

## Required Environment Variables

The backend requires these environment variables in Cloud Run:

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENAI_API_KEY` | LLM processing (conversations) | Yes* |
| `GEMINI_API_KEY` | Alternative LLM | Yes* |
| `FIREBASE_PROJECT_ID` | Firestore project | Yes |
| `FIREBASE_API_KEY` | Firebase identity toolkit | Yes |
| `APPLE_CLIENT_ID` | Apple Sign-In OAuth | For auth |
| `APPLE_TEAM_ID` | Apple Sign-In | For auth |
| `APPLE_KEY_ID` | Apple Sign-In | For auth |
| `APPLE_PRIVATE_KEY` | Apple Sign-In (PEM) | For auth |
| `GOOGLE_CLIENT_ID` | Google OAuth | For auth |
| `GOOGLE_CLIENT_SECRET` | Google OAuth | For auth |
| `RUST_LOG` | Log level (info) | No |
| `RELEASE_SECRET` | Release API auth | No |

*At least one LLM API key required

### Local Environment Reference

Local development uses `Backend-Rust/.env` which contains all secrets. Use this as reference when configuring Cloud Run.

## Troubleshooting

### 500 Error on Conversation Save

**Symptom**: App logs show `Failed to save conversation: HTTP error: 500`

**Check logs for**:
```bash
scripts/logs.sh 20 error
scripts/logs.sh 20 "500"
```

**Common causes**:
1. **Missing LLM API key** - Check `OPENAI_API_KEY` or `GEMINI_API_KEY` is set
2. **Firestore access** - Check service account permissions
3. **Invalid request** - Check backend logs for parsing errors

### Conversation Discarded (Not an Error)

If logs show `Conversation discarded by LLM` or `Discarding: word count X < 5`, this is expected behavior - short transcripts are filtered out.

### Check if Backend is Running
```bash
curl -s https://desktop-backend-hhibjajaja-uc.a.run.app/health
# Should return: {"status":"healthy","service":"omi-desktop-backend","version":"0.1.0"}
```

## Architecture Notes

### Desktop App vs Backend

| Component | Config File | Purpose |
|-----------|-------------|---------|
| Desktop App | `.env.app` | Client secrets (Deepgram, Mixpanel, backend URL) |
| Cloud Run | Environment vars | Server secrets (LLM keys, OAuth, Firebase) |
| Local Dev | `Backend-Rust/.env` | All secrets for local backend |

### URL Configuration

- **Production builds** (`release.sh`): Use URL from `.env.app`
- **Development builds** (`run.sh`): Override with local tunnel (see `scripts/test-accounts.md` for URL)

## Release Integration

Backend deployment is Step 1 of `release.sh`. When running a release:
1. Docker builds for `linux/amd64`
2. Pushes to GCR with version tag
3. Deploys to Cloud Run
4. Then continues with app build, sign, notarize, etc.
