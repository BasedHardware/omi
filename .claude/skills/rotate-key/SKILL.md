---
name: rotate-key
description: "Rotate an API key or secret across all locations — local .env files, macOS Keychain, GCP Secret Manager, Kubernetes deployments, and Codemagic CI. Use when: 'rotate key', 'update key', 'key leaked', 'replace secret', 'new API key', 'update GEMINI key', 'rotate secret'."
allowed-tools: Bash, Read, Grep, Glob, Edit, mcp__playwright-extension__browser_navigate, mcp__playwright-extension__browser_snapshot, mcp__playwright-extension__browser_click, mcp__playwright-extension__browser_type, mcp__playwright-extension__browser_wait_for
---

# Rotate API Key / Secret

Rotate a secret or API key across all locations in the OMI project.

## Usage

```
/rotate-key <KEY_NAME> <NEW_VALUE>
```

Examples:
- `/rotate-key GEMINI_API_KEY AIzaSyNewKeyHere123`
- `/rotate-key OPENAI_API_KEY sk-new-key-here`

If no new value is provided, ask the user for it.

## Rotation Checklist

For every key rotation, work through ALL of the following locations. Skip any that don't apply to the specific key.

### 1. Discovery — Find All Occurrences

```bash
# Search the entire repo for the key name (env var references)
grep -r "<KEY_NAME>" --include="*.env*" --include="*.yaml" --include="*.yml" --include="*.py" --include="*.swift" --include="*.rs" --include="*.mjs" --include="*.dart" .

# Search for the old value if known (hardcoded instances)
grep -r "<OLD_VALUE>" .
```

### 2. macOS Keychain

Check if the key is stored in the macOS Keychain and update it:

```bash
# Check for existing entry (try common service name patterns)
security find-generic-password -s "<key-name-lowercase>" -w 2>/dev/null

# Update: delete old, add new
security delete-generic-password -s "<key-name-lowercase>" 2>/dev/null
security add-generic-password -s "<key-name-lowercase>" -a "<key-name-lowercase>" -w "<NEW_VALUE>"
```

### 3. Local .env Files

Common locations (check all that contain the key):

| Location | Purpose |
|----------|---------|
| `desktop/.env` | Desktop app runtime |
| `desktop/.env.app` | Desktop app bundled env |
| `desktop/.env.app.dev` | Desktop app dev env |
| `desktop/Backend-Rust/.env` | Rust backend local |
| `desktop/build/Omi Dev.app/Contents/Resources/.env` | Dev build artifact |
| `desktop/build/Omi Beta.app/Contents/Resources/.env` | Beta build artifact |
| `backend/.env` | Python backend local |
| `app/.env` | Flutter app |
| `app/.dev.env` | Flutter app dev |

```bash
# Update each file that contains the key
sed -i '' "s/<KEY_NAME>=.*/<KEY_NAME>=<NEW_VALUE>/" <file>
```

### 4. GCP Secret Manager

The backend and desktop-backend pull secrets via Kubernetes ExternalSecrets from GCP Secret Manager.

```bash
# Prod (based-hardware)
echo -n "<NEW_VALUE>" | gcloud secrets versions add <KEY_NAME> --data-file=- --project=based-hardware

# Dev (based-hardware-dev) — may need dev service account
echo -n "<NEW_VALUE>" | gcloud secrets versions add <KEY_NAME> --data-file=- --project=based-hardware-dev \
  --account=local-development-joan@based-hardware-dev.iam.gserviceaccount.com

# Disable old versions to prevent use of leaked key
gcloud secrets versions list <KEY_NAME> --project=based-hardware --format="table(name,state)"
gcloud secrets versions disable <OLD_VERSION> --secret=<KEY_NAME> --project=based-hardware
gcloud secrets versions disable <OLD_VERSION> --secret=<KEY_NAME> --project=based-hardware-dev \
  --account=local-development-joan@based-hardware-dev.iam.gserviceaccount.com
```

### 5. Cloud Run Services (Direct Env Vars)

Some services run on Cloud Run with env vars set directly (not via K8s secrets). Check and update these:

```bash
# Check current value
gcloud run services describe <SERVICE_NAME> --project=based-hardware --region=us-central1 --format=json | \
  python3 -c "import json,sys; [print(f\"{e['name']}: ...{e.get('value','')[-4:]}\") for e in json.load(sys.stdin)['spec']['template']['spec']['containers'][0].get('env',[]) if '<KEY_NAME>' in e.get('name','')]"

# Update — IMPORTANT: must specify --image with a valid tag, check available tags first
gcloud container images list-tags gcr.io/based-hardware/<SERVICE_NAME> --limit=5 --sort-by=~timestamp --format="table(tags,timestamp.datetime)"
gcloud run services update <SERVICE_NAME> --region=us-central1 --project=based-hardware \
  --image=gcr.io/based-hardware/<SERVICE_NAME>:<VALID_TAG> \
  --update-env-vars "<KEY_NAME>=<NEW_VALUE>"
```

**Known Cloud Run services with direct env vars:**

| Service | Region | Key(s) |
|---------|--------|--------|
| `desktop-backend` | us-central1 | `GEMINI_API_KEY`, `AGENT_GEMINI_API_KEY` |

### 6. Restart Kubernetes Deployments

After updating GCP secrets, restart deployments so pods pick up the new values:

```bash
# Check which deployments use the key
kubectl get deployments -n prod-omi-backend

# Restart relevant deployments (common ones that use env secrets)
kubectl rollout restart deployment/prod-omi-backend-listen -n prod-omi-backend
kubectl rollout restart deployment/desktop-backend -n prod-omi-backend
kubectl rollout restart deployment/prod-omi-pusher -n prod-omi-backend
# Add others as needed based on which services use the key
```

### 7. Codemagic CI Environment Variables

Codemagic stores env vars used during mobile and desktop builds. Update via the dashboard:

**App ID:** `66c95e6ec76853c447b8bcbb`

**API approach (list vars):**
```bash
export CODEMAGIC_API_TOKEN="$(grep CODEMAGIC_API_TOKEN ~/.zshrc | cut -d'"' -f2)"
curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" \
  "https://api.codemagic.io/apps/66c95e6ec76853c447b8bcbb" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)['application']
for v in data.get('appEnvironmentVariables',{}).get('variables',[]):
    if v.get('key') == '<KEY_NAME>':
        print(f'Found: group={v[\"group\"]}, id={v[\"id\"]}, secure={v.get(\"secure\",False)}')
"
```

**Dashboard approach (if API update isn't supported):**
1. Navigate to `https://codemagic.io/app/66c95e6ec76853c447b8bcbb/settings`
2. Click "Environment variables" tab
3. Find the variable, click the delete (trash) button, confirm deletion
4. Add new variable: enter name, value, select the correct group (usually `app_env`), check "Secret", click "Add"

### 8. Codemagic `OMI_DESKTOP_APP_ENV` (Bundled Desktop .env)

The `OMI_DESKTOP_APP_ENV` Codemagic secret (group: `desktop_secrets`) is a **base64-encoded copy of `desktop/.env.app`** that gets decoded into the `.app` bundle at build time. If any key inside `.env.app` changes, this secret must also be updated.

```bash
# 1. Verify desktop/.env.app has the new key value
grep "<KEY_NAME>" desktop/.env.app

# 2. Re-encode
base64 -i desktop/.env.app | tr -d '\n' > /tmp/omi_desktop_app_env_b64.txt

# 3. Update in Codemagic dashboard:
#    - Environment variables tab
#    - Delete old OMI_DESKTOP_APP_ENV (desktop_secrets group)
#    - Add new: name=OMI_DESKTOP_APP_ENV, value=<contents of /tmp/omi_desktop_app_env_b64.txt>,
#      group=desktop_secrets, Secret=checked
```

**Keys bundled in `desktop/.env.app`:** `OMI_API_URL`, `DEEPGRAM_API_KEY`, `GEMINI_API_KEY`, `MIXPANEL_PROJECT_TOKEN`, `ANTHROPIC_API_KEY`

### 9. Verification

After rotation, verify:

```bash
# Keychain
security find-generic-password -s "<key-name-lowercase>" -w

# All .env files
grep "<KEY_NAME>" desktop/.env desktop/.env.app desktop/.env.app.dev desktop/Backend-Rust/.env backend/.env 2>/dev/null

# GCP Secret Manager
gcloud secrets versions list <KEY_NAME> --project=based-hardware --format="table(name,state)"

# Kubernetes rollout status
kubectl rollout status deployment/prod-omi-backend-listen -n prod-omi-backend --timeout=120s
```

### 9. Remind User

After completing rotation, remind the user to:
- **Revoke the old key** in the provider's console (Google Cloud API Credentials, OpenAI dashboard, etc.)
- **Check for unauthorized usage** in the provider's usage/billing dashboard during the leak window

## Key-Specific Notes

### GEMINI_API_KEY
- Used by: backend (Python), desktop app (Swift via env), desktop Rust backend, Codemagic (mobile builds + desktop deploy)
- Codemagic groups: `app_env` (direct var) **AND** `desktop_secrets` (inside `OMI_DESKTOP_APP_ENV` base64 bundle)
- Keychain service: `gemini-api-key`
- GCP projects: `based-hardware` (prod), `based-hardware-dev` (dev)
- Cloud Run: `desktop-backend` (us-central1, direct env var — NOT via K8s secrets)
- K8s deployments: `prod-omi-backend-listen` (via ExternalSecrets)
- Helm values reference it via `secretKeyRef` (no hardcoded values in helm charts)
- **IMPORTANT**: Also update `OMI_DESKTOP_APP_ENV` in Codemagic (step 8) — it contains this key inside the base64-encoded `.env.app`
- **WARNING**: Never hardcode this key in any tracked file. It has been leaked twice via committed helm values.

### OPENAI_API_KEY
- Used by: backend (Python), Codemagic (mobile builds)
- Codemagic group: `app_env`

### GOOGLE_CLIENT_SECRET
- Used by: backend OAuth, Codemagic
- Codemagic group: `app_env`
