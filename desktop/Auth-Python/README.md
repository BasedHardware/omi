# Desktop Auth Service (Auth-Python)

**Origin:** Reverse-engineered from the production `omi-desktop-auth` Cloud Run container image. The original source was never committed to the repo — it was deployed manually, which caused friction when setting up local dev environments (no way to run auth locally). This extraction is a temporary measure to unblock local development. Will be removed once auth is properly integrated into the main codebase.

## What it does

OAuth broker for the desktop macOS app. Handles Google and Apple Sign-In:

1. App opens `GET /v1/auth/authorize?provider=google&redirect_uri=...&state=...`
2. Service redirects browser to Google/Apple OAuth
3. OAuth provider redirects back to `/v1/auth/callback/google` (or `/apple`)
4. Service generates a Firebase custom token via `firebase_admin.auth.create_custom_token()`
5. Browser redirects to the app via custom URL scheme (`omi-computer-dev://auth/callback`)

## Running locally

Started automatically by `desktop/run.sh` on the auth port (default: 10200).

To run standalone:

```bash
cd desktop/Auth-Python
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Source env vars (shares config with Rust backend)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/google-credentials.json
export BASE_API_URL=http://localhost:10200
export GOOGLE_CLIENT_ID=<from GCP console>
export GOOGLE_CLIENT_SECRET=<from GCP console>
export FIREBASE_API_KEY=<firebase web api key>

.venv/bin/uvicorn main:app --host 0.0.0.0 --port 10200
```

## Required env vars

See `.env.example` for the full list. Key ones:

- `GOOGLE_APPLICATION_CREDENTIALS` — GCP service account JSON (needs Firebase Auth admin)
- `BASE_API_URL` — callback URL base (must match Google OAuth redirect URI)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from GCP OAuth client
- `FIREBASE_API_KEY` — Firebase Web API key

## Port allocation

Pick any free port (never 8080 — conflicts with Tailscale). Default: 10200.

Google OAuth redirect URIs must be registered for your port in the GCP Console.
