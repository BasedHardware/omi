# Deployment Notes

## Current Setup: Local Development

Following [SELF_HOSTING_GUIDE.md](SELF_HOSTING_GUIDE.md) for local development:
- Backend runs locally on Windows with ngrok
- Uses cloud services: Firebase, Upstash Redis, Deepgram, OpenAI, Pinecone
- Limitless pendant connects via BLE → App → ngrok → local backend

## Future: GCP Production Deployment

When ready to deploy to production (Phase 4 "Scale up"):

### Prerequisites
- Google Cloud Platform account
- GCP project created
- Billing enabled
- Required APIs enabled

### Workflow Configuration

The GitHub Actions workflows in `.github/workflows/` are templates from BasedHardware.

**To configure for your GCP project:**

1. **Set up GCP secrets in GitHub**:
   - `GCP_CREDENTIALS` - Service account JSON
   - `GCP_SERVICE_ACCOUNT` - Base64 encoded service account
   
2. **Set up GCP variables in GitHub**:
   - `GCP_PROJECT_ID` - Your GCP project ID
   - `GKE_CLUSTER` - Your GKE cluster name (if using)
   - `ENV` - Environment name (dev/prod)

3. **Update workflow triggers**:
   - Change from `workflow_dispatch` to `push` on main branch
   - Or keep manual for controlled deployments

4. **Services to deploy**:
   - Backend API (Cloud Run)
   - Backend sync service (Cloud Run)
   - Backend listen service (GKE)
   - Backend integration service (Cloud Run)
   - Frontend (Cloud Run)
   - Apps JS (Cloud Run)
   - Models service (Cloud Run)
   - Notifications job (Cloud Run)
   - Personas (Cloud Run)
   - Plugins (Cloud Run)

### Alternative: Deploy to Other Platforms

If deploying to AWS/Azure instead:
- Use workflows as reference for build steps
- Create new workflows for your platform
- See Docker configurations in each service directory

### Resources
- [GCP Cloud Run Docs](https://cloud.google.com/run/docs)
- [GitHub Actions GCP Auth](https://github.com/google-github-actions/auth)
- [Omi Backend Docs](https://docs.omi.me/doc/developer/backend/Backend_Setup)

