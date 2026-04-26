# nooto-jira-app

Jira Cloud integration for Nooto. Implements the Omi external-integration plugin contract:

- OAuth 2.0 (3LO) connect flow
- 7 chat tools (create / list / search / get / update status / comment / list projects)
- Proactive transcript detection (live `/webhook`)
- Post-conversation suggestions (`/memory_created`)
- User settings + suggestion confirm flow

## Layout

```
main.py                 FastAPI app, mounts routers, /health
db.py                   Redis token store + HMAC state + refresh loop
jira_client.py          Atlassian REST helpers (issues, search, transitions, ADF)
intent_detector.py      gpt-4o JSON-mode intent extraction (live + post-memory)
models.py               Pydantic schemas shared across routes
routes/
  auth.py               /auth/jira, /auth/jira/callback, /setup/jira
  tools.py              7 /tools/* chat-tool endpoints
  manifest.py           /.well-known/omi-tools.json
  proactive.py          /webhook, /memory_created, /tools/confirm_suggestion
  settings.py           /settings, /settings/default-site
templates/setup.html    OAuth landing + post-auth confirmation + site picker
scripts/register_jira_app.py  POST/PATCH /v1/apps to register with Nooto backend
```

## Local dev

```bash
cp .env.template .env
# Fill JIRA_CLIENT_ID/SECRET from a staging Atlassian dev-console app whose
# callback URL points at your ngrok tunnel + /auth/jira/callback.
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Expose via ngrok (`td.ngrok.app`) for the OAuth round-trip to work.

## Deploy

Coolify project **Nooto Apps** at `https://coolify.motorbrain.net`. Two apps —
staging (`nooto-jira-staging.togodynamics.com`) and prod (`nooto-jira.togodynamics.com`)
— each pointing at its own Atlassian OAuth client.

Env vars are catalogued in [`.env.template`](./.env.template). Set them via
`mcp__coolify-nooto__set_env_variable`.

After deploy, register the app in the Nooto backend:

```bash
NOOTO_ADMIN_TOKEN=... python scripts/register_jira_app.py --env staging
NOOTO_ADMIN_TOKEN=... python scripts/register_jira_app.py --env prod
```

## Atlassian dev console

https://developer.atlassian.com/console → My apps → Create → OAuth 2.0 integration.

- Permissions → Jira API → grant `read:jira-work`, `write:jira-work`, `read:jira-user`, `offline_access`.
- Authorization → Callback URL = `https://nooto-jira{,-staging}.togodynamics.com/auth/jira/callback`.
- Distribution → *Sharing* with privacy + ToS URLs.

Use **two separate apps** (one per env) for clean isolation.
