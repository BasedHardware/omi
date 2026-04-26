# Nooto Jira Plugin — Deploy Runbook

Operator-facing deploy guide. Run staging first; promote to prod once smoke
passes.

## 1. Overview

| Layer | What | Where |
|---|---|---|
| Plugin service | FastAPI (this repo) | Coolify project **Nooto Apps** (`as00k84k4c40swows0w0kc0c`) |
| OAuth provider | Atlassian OAuth 2.0 (3LO) | https://developer.atlassian.com/console |
| Token store | Redis | shared Coolify Redis (same instance other plugins use) |
| App registry | Nooto backend `/v1/apps` | `nooto-dev` (staging) / `nooto-e2d27` (prod) Firestore |
| Public URLs | `nooto-jira-staging.togodynamics.com` / `nooto-jira.togodynamics.com` | Coolify FQDNs |

Branch convention: staging deploys from `feat/nooto-jira-app`, prod from `main`.

## 2. Atlassian Developer Console (per env)

Create **two separate** OAuth 2.0 (3LO) integrations — one per env — for clean
isolation of client IDs and callback URLs.

1. https://developer.atlassian.com/console → **My apps** → **Create** →
   **OAuth 2.0 integration**.
   - Name: `Nooto Jira (staging)` or `Nooto Jira (prod)`.
2. **Permissions** → **Add** → **Jira API** → grant scopes:
   - `read:jira-work`
   - `write:jira-work`
   - `read:jira-user`
   - `offline_access`
3. **Authorization** → **Configure** OAuth 2.0 (3LO):
   - Callback URL (staging): `https://nooto-jira-staging.togodynamics.com/auth/jira/callback`
   - Callback URL (prod): `https://nooto-jira.togodynamics.com/auth/jira/callback`
4. **Distribution** → **Sharing** → set Privacy policy + ToS URLs (Nooto's
   public ones).
5. **Settings** → copy **Client ID** and **Secret** → keep handy for the
   Coolify env-var step below.

## 3. Coolify Deploy — Staging

Coolify MCP does **not** expose application creation, so the first app must be
created via the dashboard. Subsequent operations use the MCP.

1. List projects to confirm UUID:
   ```
   mcp__coolify-nooto__list_projects
   ```
   Expect `Nooto Apps` → `as00k84k4c40swows0w0kc0c`.

2. **Dashboard** → project **Nooto Apps** → **+ New** → **Public Repository**:
   - Repo: `https://github.com/togodynamicslab/omi`
   - Branch: `feat/nooto-jira-app`
   - Build pack: **Dockerfile**
   - Base directory: `/plugins/nooto-jira-app`
   - Port: `8080`
   - FQDN: `https://nooto-jira-staging.togodynamics.com`
   - Save → capture the new application UUID (call it `STAGING_UUID`).

3. Set env vars (run once per row; `is_build_time=false`, `is_preview=false`):

   | Key | Value (staging) |
   |---|---|
   | `PORT` | `8080` |
   | `ENVIRONMENT` | `staging` |
   | `LOG_LEVEL` | `INFO` |
   | `BASE_URL` | `https://nooto-jira-staging.togodynamics.com` |
   | `PUBLIC_BASE_URL` | `https://nooto-jira-staging.togodynamics.com` |
   | `JIRA_CLIENT_ID` | from Atlassian console (staging app) |
   | `JIRA_CLIENT_SECRET` | from Atlassian console (staging app) |
   | `JIRA_REDIRECT_URI` | `https://nooto-jira-staging.togodynamics.com/auth/jira/callback` |
   | `JIRA_SCOPES` | `read:jira-work write:jira-work read:jira-user offline_access` |
   | `JIRA_OAUTH_STATE_SECRET` | `python3 -c 'import secrets; print(secrets.token_hex(32))'` |
   | `SESSION_SECRET` | `python3 -c 'import secrets; print(secrets.token_hex(32))'` |
   | `OMI_BACKEND_URL` | `https://nooto-dev.togodynamics.com` |
   | `OMI_API_BASE_URL` | `https://nooto-dev.togodynamics.com` |
   | `OMI_APP_ID` | `nooto-jira` |
   | `OMI_APP_SECRET` | (filled after step 5 below) |
   | `REDIS_URL` | reuse existing plugin Redis — confirm in Coolify dashboard |
   | `OPENAI_API_KEY` | shared Nooto staging key |
   | `JIRA_AUTOFILE_CONFIDENCE_THRESHOLD` | `0.85` |
   | `JIRA_SUGGEST_CONFIDENCE_THRESHOLD` | `0.6` |
   | `JIRA_LLM_DAILY_CAP` | `200` |

   ```
   mcp__coolify-nooto__set_env_variable
     application_uuid=<STAGING_UUID>
     key=PORT value=8080 is_build_time=false is_preview=false
   # ...repeat per row
   ```

4. Deploy and watch logs:
   ```
   mcp__coolify-nooto__deploy_application application_uuid=<STAGING_UUID>
   mcp__coolify-nooto__get_deployments    application_uuid=<STAGING_UUID>
   mcp__coolify-nooto__get_deployment_log application_uuid=<STAGING_UUID> deployment_uuid=<DEPLOY_UUID>
   ```

   Confirm the FQDN serves `GET /.well-known/omi-tools.json` (200) before
   moving on.

## 4. Coolify Deploy — Prod

Clone the staging app via the dashboard:

1. Dashboard → staging app → **Clone**.
2. Edit the clone:
   - Branch: `main`
   - FQDN: `https://nooto-jira.togodynamics.com`
3. Update env vars to prod values:
   - `ENVIRONMENT=production`
   - `BASE_URL` / `PUBLIC_BASE_URL` → `https://nooto-jira.togodynamics.com`
   - `JIRA_REDIRECT_URI` → `https://nooto-jira.togodynamics.com/auth/jira/callback`
   - `JIRA_CLIENT_ID` / `JIRA_CLIENT_SECRET` → prod Atlassian app
   - `OMI_BACKEND_URL` / `OMI_API_BASE_URL` → `https://nooto.togodynamics.com`
   - `JIRA_OAUTH_STATE_SECRET` / `SESSION_SECRET` → fresh 32-byte hex (do not
     reuse staging secrets)
   - `OPENAI_API_KEY` → prod Nooto key
4. `deploy_application` and verify logs as in §3.4.

## 5. Register the App With the Nooto Backend

Idempotent registration script: probes for the existing entry, then POSTs or
PATCHes accordingly.

```bash
# Mint a Firebase ID token for an admin user (Nooto staging or prod project)
# and export it. The /v1/apps endpoints authenticate via Firebase Bearer.
export NOOTO_ADMIN_TOKEN='<firebase-id-token>'

# Staging
python3 scripts/register_jira_app.py --env staging

# Prod
python3 scripts/register_jira_app.py --env prod
```

The script:
- Probes `GET /v1/apps/nooto-jira` to decide POST vs PATCH.
- Sends `multipart/form-data` with `app_data` (JSON) + `file` (PNG).
- Reads logo from `plugins/logos/nooto-jira.png`.
- Exits non-zero on a non-2xx response.

After a successful POST, copy the returned `app_id` and any app secret returned
by the backend into the Coolify env var `OMI_APP_SECRET`, then redeploy.

> **Caveat:** `POST /v1/apps` overwrites the supplied `id` with a fresh ULID
> (see `backend/routers/apps.py:486`). For a stable `nooto-jira` doc id, after
> the first POST manually rename the Firestore document under
> `plugins_data/<ulid>` to `plugins_data/nooto-jira` (or accept the ULID and
> reference it everywhere). Subsequent runs PATCH by id and stay idempotent.

## 6. Smoke Test

```bash
# Manifest reachable
curl -sf https://nooto-jira-staging.togodynamics.com/.well-known/omi-tools.json | jq '.tools | length'

# OAuth start (browser)
open "https://nooto-jira-staging.togodynamics.com/auth/jira?uid=test_uid"
# → consent → /setup/jira?uid=test_uid → expect "is_setup_completed": true

# Tool call
curl -X POST https://nooto-jira-staging.togodynamics.com/tools/list_projects \
  -H 'Content-Type: application/json' \
  -d '{"uid":"test_uid"}'

# Memory webhook (post-conversation flow)
curl -X POST https://nooto-jira-staging.togodynamics.com/memory_created \
  -H 'Content-Type: application/json' \
  -d '{"uid":"test_uid","memory":{"transcript":"create a Jira ticket in NTO to fix the login bug"}}'
```

Then in the Nooto desktop client (dev flavor) → **Apps** → search **Jira** →
**Connect** → complete OAuth → **Enable** → chat: `create a Jira ticket in
project NTO titled "deploy smoke test"` → confirm the issue appears in Jira.

## 7. Rollback

Pick whichever is least disruptive:

- **Hide from store, keep service running** (preferred for soft rollback):
  PATCH the registration with `approved=false, status="archived"` via the
  registration script (modify payload) or directly with curl.
- **Delete registration** (hard):
  ```bash
  curl -X DELETE https://nooto-dev.togodynamics.com/v1/apps/nooto-jira \
    -H "Authorization: Bearer $NOOTO_ADMIN_TOKEN"
  ```
  Verify the route exists; if it 404s, fall back to the soft rollback above.
- **Stop the Coolify service**:
  ```
  mcp__coolify-nooto__stop_application application_uuid=<UUID>
  ```
- **Atlassian**: rotate (or revoke) the client secret in the developer console;
  user refresh tokens stop working on next refresh.
- **Firestore last resort**: delete `plugins_data/nooto-jira` directly via
  `gcloud firestore documents delete` against the relevant Nooto project.
