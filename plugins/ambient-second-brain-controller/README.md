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

## Audio Spool Import

`POST /capture/audio-spool` accepts the companion app's length-prefixed PCM16/16 kHz/mono `.bin` payload, validates
the frame format, stores it locally, and forwards it to Omi's existing `/v1/sync-local-files` pipeline when
`OMI_API_BASE_URL` plus `OMI_API_KEY` or `OMI_APP_SECRET` are configured. The plugin still does not capture audio
itself; it only receives explicitly uploaded local spools from the registered device.

## Conservative Defaults

- Capture disabled.
- Accessibility disabled.
- Raw audio upload disabled.
- Telemetry text disabled.
- Communication mode is awareness-only by default.

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
