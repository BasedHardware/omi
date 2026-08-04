# Personas

Personas is an open-source Next.js and Firebase chat experience for interacting
with AI personalities built from public social profiles.

## LLM routing and authentication

The browser never selects a provider model or receives an LLM credential. It
sends an optional Firebase ID token to the same-origin `/api/chat` route. The
server verifies that token and chooses one of two fixed Omi gateway lanes:

- signed-out or anonymous Firebase session: `omi:auto:persona-chat`
  (`gpt-5.4-nano`);
- verified, non-anonymous Firebase session: `omi:auto:persona-chat-premium`
  (`gpt-5.6-luna`).

Both lanes are resolved inside the authenticated Omi LLM gateway. A caller
supplied model value is ignored, and a gateway failure returns an unavailable
response without a direct-provider fallback.

## Local setup

Install Node.js 18 or later, then:

```bash
cd web/personas-open-source
npm ci
```

Create `.env.local` with the Firebase public configuration used by the browser,
plus the server-only gateway settings:

```dotenv
NEXT_PUBLIC_FIREBASE_API_KEY=your_firebase_api_key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_firebase_auth_domain
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_firebase_project_id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_firebase_storage_bucket
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_firebase_messaging_sender_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_firebase_app_id
NEXT_PUBLIC_FIREBASE_VAPID_KEY=your_firebase_vapid_key

OMI_LLM_GATEWAY_URL=http://127.0.0.1:9080
OMI_LLM_GATEWAY_SERVICE_TOKEN=local_gateway_service_token

RAPIDAPI_KEY=your_rapidapi_key
RAPIDAPI_HOST=your_rapidapi_host
LINKEDIN_RAPIDAPI_HOST=linkedin-api8.p.rapidapi.com
LINKEDIN_API_KEY=your_rapidapi_linkedin_key
NEXT_PUBLIC_MIXPANEL_TOKEN=your_mixpanel_token
REDIS_DB_HOST=your_redis_host
REDIS_DB_PORT=your_redis_port
REDIS_DB_PASSWORD=your_redis_password
```

The LinkedIn integration uses the
[RockAPI LinkedIn endpoint](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-api8).

Start the app with `npm run dev`, then open <http://localhost:3000>.

## Checks

```bash
npm test
npm run lint
npm run build
```

The repository guard `.github/scripts/check_web_llm_gateway_only.py` rejects
direct LLM provider SDKs, URLs, credentials, and package dependencies in
production web code.
