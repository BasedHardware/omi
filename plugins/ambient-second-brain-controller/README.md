# Ambient Second Brain Controller

FastAPI backend for Omi Advanced Ambient Capture policy control, telemetry, fallback transcript ingestion, task extraction, and accountability prompts.

This plugin does not record audio. The Android app owns capture, foreground service behavior, private mode, native spool/WAL, and local user overrides. This backend only issues signed, short-lived policies that the app pulls and verifies locally.

## Run Locally

```bash
cd plugins/ambient-second-brain-controller
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn python-dotenv requests cryptography pytest
cp .env.example .env
uvicorn main:app --reload --port 8000
```

On Windows PowerShell:

```powershell
cd plugins\ambient-second-brain-controller
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn python-dotenv requests cryptography pytest
Copy-Item .env.example .env
uvicorn main:app --reload --port 8000
```

## Free HTTPS Deployment

For personal testing with the companion app, deploy this plugin to Render Free. Render provides a real HTTPS URL with
minimal setup, which is enough for device registration, signed policy pulls, telemetry, fallback segments, and audio
spool upload testing.

See `DEPLOY_RENDER.md` for the exact Render setup, environment variables, verification URLs, and companion app test
steps.

## Environment

See `.env.example`.

For production, configure a real Ed25519 key pair:

```bash
python - <<'PY'
import security
print(security.generate_key_pair())
PY
```

## Endpoints

- `GET /healthz`
- `GET /readyz`
- `GET /.well-known/ambient-controller.json`
- `GET /.well-known/omi-app-registration.json`
- `GET /.well-known/omi-tools.json`
- `POST /device/register`
- `POST /device/revoke`
- `GET /capture/policy/current`
- `POST /capture/telemetry`
- `POST /capture/fallback-segments`
- `POST /capture/audio-spool`
- `POST /webhooks/omi/memory-created`
- `POST /webhooks/omi/transcript-processed`
- `POST /webhooks/omi/audio-bytes`
- `GET /settings`
- `POST /settings`
- `POST /tools/{tool_name}`

## Device Registration

`POST /device/register` returns:

- policy URL
- telemetry URL
- fallback segments URL
- audio spool URL
- plugin public key
- key id
- key fingerprint
- device token

The device token is used as `Authorization: Bearer <device_token>` for policy pulls, telemetry, fallback segments,
and audio spool uploads.

On first registration, the plugin creates per-user capture settings from the `AMBIENT_DEFAULT_*` environment variables.
For companion testing, the checked-in Render defaults enable normal capture, local STT fallback, caption fallback,
transcript upload, audio upload, and communication awareness. The Android app still owns local permissions, private
mode, and user-visible stop/pause controls.

## Audio Spool Import

`POST /capture/audio-spool` accepts the companion app's length-prefixed PCM16/16 kHz/mono `.bin` payload, validates
the frame format, stores it locally, and forwards it to Omi's existing `/v1/sync-local-files` pipeline when
`OMI_API_BASE_URL` plus `OMI_API_KEY` or `OMI_APP_SECRET` are configured. The plugin still does not capture audio
itself; it only receives explicitly uploaded local spools from the registered device.

## Baseline Safety Defaults

The Pydantic model defaults are conservative when no deployment defaults are supplied:

- Capture disabled.
- Accessibility disabled.
- Raw audio upload disabled.
- Telemetry text disabled.
- Communication mode is awareness-only by default.

The Render/test deployment intentionally sets `AMBIENT_DEFAULT_*` values to make a newly registered personal companion
device useful immediately. Do not use Render Free SQLite storage as the long-term production database for public users.

## Tests

```bash
cd plugins/ambient-second-brain-controller
pytest
```

Covered:

- policy signing and local verification fixture
- expired policy and replayed sequence rejection
- revoked device policy denial
- telemetry storage and unsafe field rejection
- fallback segment storage and dedupe
- audio spool storage and dedupe
- task extraction confidence levels
- chat tools manifest schema
- health, readiness, and controller registration manifests
- registration-time default settings
- settings persistence

## Omi App Registration

See `omi-app-registration.example.json`.

The app capability must include `ambient_capture_controller`. The public key and key id in Omi registration must match the key used by this service.

## Safety Notes

- The plugin never records audio.
- The plugin never attempts protected call recording.
- The plugin cannot override local private mode in the Android app.
- The plugin never issues policy for revoked devices.
- Fallback segments preserve source labels and degraded metadata.
