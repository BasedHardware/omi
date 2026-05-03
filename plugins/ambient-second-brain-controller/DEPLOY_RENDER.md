# Free HTTPS Deployment On Render

Render Free is the fastest low-setup way to test the Ambient Second Brain Controller with a real HTTPS URL. It gives you a valid TLS endpoint such as `https://ambient-second-brain-controller.onrender.com`, which the companion app can call directly.

Important limitation: Render Free services can sleep when idle and the local SQLite file is not a durable production database. This is fine for personal testing and handshake debugging. For a public release, move storage to durable Postgres/Supabase/Cloudflare D1 and object storage.

## 1. Generate Policy Keys

From this repo:

```powershell
cd C:\Users\G\Documents\omi\plugins\ambient-second-brain-controller
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import json, security; print(json.dumps(security.generate_key_pair(), indent=2))"
```

Save both values:

- `AMBIENT_POLICY_PRIVATE_KEY`
- `AMBIENT_POLICY_PUBLIC_KEY`

Keep the private key secret. The companion pins the public key returned by `/device/register`, and policy verification must use that pinned key.

## 2. Create The Render Service

1. Go to [Render](https://render.com/) and create a free account.
2. Click **New +** → **Web Service**.
3. Connect the GitHub repo that contains this branch.
4. Use these settings:
   - **Name:** `ambient-second-brain-controller`
   - **Root Directory:** `plugins/ambient-second-brain-controller`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
   - **Health Check Path:** `/healthz`

If Render offers to use `render.yaml`, that is also fine. The checked-in `render.yaml` contains the same service shape.

## 3. Configure Environment Variables

Set these in Render:

```text
AMBIENT_PLUGIN_ID=ambient_second_brain_controller
AMBIENT_POLICY_KEY_ID=ambient-controller-key-1
AMBIENT_POLICY_PRIVATE_KEY=<the generated private key>
AMBIENT_POLICY_PUBLIC_KEY=<the generated public key>
WEBHOOK_BASE_URL=https://<your-render-service>.onrender.com
DATABASE_URL=sqlite:///./ambient_second_brain.sqlite3
OMI_API_BASE_URL=https://api.omi.me
```

Optional, only if you have official Omi API credentials:

```text
OMI_API_KEY=<your key>
OMI_APP_SECRET=<your secret>
```

For personal testing, these defaults make a newly registered companion device immediately useful:

```text
AMBIENT_DEFAULT_CAPTURE_ENABLED=true
AMBIENT_DEFAULT_CAPTURE_MODE=normal
AMBIENT_DEFAULT_SENSITIVITY=medium
AMBIENT_DEFAULT_ACCESSIBILITY_MODE=true
AMBIENT_DEFAULT_LOCAL_STT_FALLBACK=true
AMBIENT_DEFAULT_CAPTION_FALLBACK=true
AMBIENT_DEFAULT_AUDIO_UPLOAD=true
AMBIENT_DEFAULT_TRANSCRIPT_UPLOAD=true
AMBIENT_DEFAULT_RAW_AUDIO_RETENTION=until_synced
AMBIENT_DEFAULT_COMMUNICATION_MODE=detect_and_caption_fallback
AMBIENT_DEFAULT_NOTIFICATION_AGGRESSIVENESS=normal
AMBIENT_DEFAULT_AUDIT_LEVEL=basic
```

## 4. Verify The Controller

Open these URLs after Render deploys:

```text
https://<your-render-service>.onrender.com/healthz
https://<your-render-service>.onrender.com/readyz
https://<your-render-service>.onrender.com/.well-known/ambient-controller.json
https://<your-render-service>.onrender.com/.well-known/omi-app-registration.json
```

Expected:

- `/healthz` returns `{"status":"ok", ...}`.
- `/readyz` returns `status: ready`, the public key fingerprint, and whether Omi import credentials are configured.
- `ambient-controller.json` exposes the policy, telemetry, fallback segment, and audio spool URLs.
- `omi-app-registration.json` is the JSON to use when registering the plugin with Omi.

## 5. Configure The Existing Companion App

In the installed **Omi Ambient Companion** debug app:

1. Open the app.
2. Set the plugin/controller base URL to `https://<your-render-service>.onrender.com`.
3. Enter your Omi user id.
4. Tap **Register Device**.
5. Confirm the app shows a key fingerprint and device token/policy status.
6. Run the in-app preflight/checklist.
7. Grant microphone, notifications, accessibility, notification listener, and battery exemption when prompted.
8. Tap **Start**.
9. Speak for 30-60 seconds.
10. Tap sync/upload if the app exposes it, or wait for the worker.

The controller should receive:

- `POST /device/register`
- repeated `GET /capture/policy/current`
- `POST /capture/telemetry`
- `POST /capture/fallback-segments` when captions/local STT are active
- `POST /capture/audio-spool` when audio spools are uploaded

## 6. Debug Checklist

If capture does not show up in Omi yet, check this order:

1. Companion diagnostics: policy accepted, key id matches, sequence increases.
2. Render logs: device registration and policy requests return 200.
3. Render logs: `/capture/audio-spool` returns 200 and `inserted: true`.
4. `/readyz`: `omi_import_configured` is true only when Omi credentials are set.
5. If `omi_import_configured` is false, the plugin still stores uploads locally, but cannot forward them into the official Omi import pipeline.
6. If Render has slept, the first policy request can be slow; retry once from the companion.

## 7. What To Capture For Bug Reports

Send:

- Render service URL.
- `/readyz` JSON with secrets removed.
- Companion diagnostics export.
- A short Render log window covering register → start → speak → upload.
- Whether `/capture/audio-spool` was called and what it returned.
