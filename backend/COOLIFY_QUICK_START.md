# Quick Start: Deploy Omi Backend to Coolify

This guide helps you deploy the Omi backend to Coolify using Docker Compose (includes Redis, Typesense, Backend, and Pusher services).

## Prerequisites

- Coolify instance v4.0+
- Git repository connected to Coolify
- **GCP Project with Firestore and GCS** - See [Automated Setup](#automated-gcp-setup-recommended) below
- API keys and credentials ready

## Automated GCP Setup (Recommended)

**NEW:** We provide an automated setup script that creates everything you need in GCP!

```bash
cd backend/scripts
./setup_gcp_project.sh
```

This script automatically:
- ✅ Creates/configures GCP project
- ✅ Enables required APIs (Firestore, Storage, Firebase)
- ✅ Creates Firestore database
- ✅ Creates all 9 GCS buckets
- ✅ Sets up service account with proper IAM roles
- ✅ Deploys Firestore indexes
- ✅ Generates environment variables

**See [scripts/README_SETUP.md](scripts/README_SETUP.md) for detailed instructions.**

After running the script, you'll have:
- Service account JSON file
- `.env.YOUR_PROJECT_ID` file with all required variables
- All GCP infrastructure ready to go!

---

## Manual Setup (Alternative)

If you prefer manual setup or already have a GCP project configured, continue with the steps below.

## Step 1: Prepare Environment Variables

Create a list of your environment variables (you can copy from your `.env` file):

```bash
# Core
BASE_API_URL=https://your-coolify-domain.com
ADMIN_KEY=your-secure-admin-key

# OpenAI
OPENAI_API_KEY=sk-proj-...

# Typesense API Key (REQUIRED - must match docker-compose)
TYPESENSE_API_KEY=your-typesense-api-key

# Speech-to-Text (at least one)
DEEPGRAM_API_KEY=...
SONIOX_API_KEY=...

# Pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=omi-dev

# Google Cloud Buckets
BUCKET_SPEECH_PROFILES=gs://your-bucket
BUCKET_BACKUPS=gs://your-bucket
BUCKET_PLUGINS_LOGOS=gs://your-bucket

# Google Credentials (minified JSON)
SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}

# Optional
HUGGINGFACE_TOKEN=...
GITHUB_TOKEN=...
```

**Important:** Do NOT set `REDIS_DB_HOST`, `REDIS_DB_PORT`, `TYPESENSE_HOST`, or `TYPESENSE_HOST_PORT`. The docker-compose.yml handles these automatically.

## Step 2: Create Service in Coolify

1. Log in to Coolify
2. Select your project or create new one
3. Click **"New Resource"** -> **"Docker Compose"**
4. Connect your repository
5. Set **Base Directory** to `backend`
6. Coolify will detect the `docker-compose.yml` file

## Step 3: Configure in Coolify

### General Settings:
- **Name:** omi-backend (or your preference)
- **Environment:** production

### Domains:
- Add your domain (e.g., `api.yourdomain.com`)
- Coolify will provision SSL automatically

### Environment Variables:
- Click the **"Environment"** tab
- Add all variables from Step 1
- **Do not add Redis/Typesense host variables** (handled by docker-compose)

### Google Cloud Credentials:

Choose **ONE** of the following methods:

**Option A - Storage Volume (Recommended for security):**
1. In Coolify, go to your service's **"Storages"** tab
2. Click **"Add Storage"**
3. Select **"File Mount"**
4. Set source path: `/path/on/host/google-credentials.json` (upload your file to Coolify server first)
5. Set destination: `/app/google-credentials.json`
6. Save

**Option B - Environment Variable:**
1. Minify your `google-credentials.json`:
   ```bash
   cat google-credentials.json | jq -c
   ```
2. Add the output as `SERVICE_ACCOUNT_JSON` environment variable in Coolify
3. The backend will automatically create `/app/google-credentials.json` from this variable

## Step 4: Deploy

1. Click **"Deploy"** button
2. Monitor build logs
3. Wait for health check to pass

## Step 5: Verify

Test the health endpoint:
```bash
curl https://your-domain.com/v1/health
```

Expected response:
```json
{"status":"ok"}
```

## Architecture

Your deployment includes:

```
+---------------------------------------+
|         Coolify Deployment            |
+---------------------------------------+
|                                       |
|  +-----------+    +---------------+   |
|  |  Backend  |    |    Redis      |   |
|  |  (8080)   |----|    (6379)     |   |
|  +-----------+    +---------------+   |
|       |                               |
|       |           +---------------+   |
|       +-----------|  Typesense    |   |
|                   |    (8108)     |   |
|  +-----------+    +---------------+   |
|  |  Pusher   |                        |
|  |  (8080)   |                        |
|  +-----------+                        |
|       |                               |
+-------+-------------------------------+
        |
   +----v-----+
   | Traefik  | (Reverse Proxy)
   |  HTTPS   |
   +----------+
        |
   Your Domain
```

## Data Persistence

The following volumes are automatically created:
- `backend_omi-redis-data` - Redis data
- `backend_omi-typesense-data` - Typesense search index
- `backend_omi-temp` - Temporary files
- `backend_omi-samples` - Audio samples
- `backend_omi-segments` - Audio segments
- `backend_omi-speech-profiles` - Speech profiles

**Backups:** Set up Coolify's backup feature to backup these volumes.

## Updating

When you push to your repository:
1. Coolify detects the change
2. Rebuilds containers
3. Performs rolling update
4. Zero downtime (if configured)

Manual deployment:
1. Go to your service in Coolify
2. Click **"Deploy"**

## Troubleshooting

### Build Fails
- Check build logs in Coolify
- Ensure all required environment variables are set
- Verify base directory is `backend`

### Health Check Fails
- Check container logs
- Verify port 8080 is exposed
- Test manually: `curl http://localhost:8080/v1/health` (from inside container)

### Redis Connection Error
- Ensure you **did not** set `REDIS_DB_HOST` environment variable
- Check both containers are running
- View logs: `docker logs omi-redis`

### Typesense Connection Error
- Ensure `TYPESENSE_API_KEY` is set in environment variables
- Check typesense container is running: `docker logs omi-typesense`
- Ensure you **did not** set `TYPESENSE_HOST` environment variable

### Google Cloud Auth Errors
- Verify `SERVICE_ACCOUNT_JSON` is properly minified (one line, no spaces)
- Check service account has required permissions
- Test locally first with same credentials

## Security Checklist

- [ ] HTTPS enabled (Coolify handles this)
- [ ] Strong `ADMIN_KEY` set
- [ ] Strong `ENCRYPTION_SECRET` set (not default)
- [ ] Strong `TYPESENSE_API_KEY` set
- [ ] Environment variables in Coolify (not in code)
- [ ] Google credentials secured
- [ ] Firewall rules configured (if applicable)

## Next Steps

1. Configure your mobile app to use `https://your-domain.com`
2. Test WebSocket connections
3. Set up monitoring and alerts
4. Configure backup schedule
5. Review logs regularly
6. Initialize Typesense collections (if needed)

## Support

- [Coolify Docs](https://coolify.io/docs)
- [Typesense Docs](https://typesense.org/docs/)
- [Omi Documentation](https://docs.omi.me/)
