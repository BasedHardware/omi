# OMI WhatsApp AI-Clone plugin

Lets Omi reply to people on the user's behalf in WhatsApp, using the user's persona.

Self-hosted FastAPI service. Receives WhatsApp Cloud API webhook updates, calls the Omi persona API, and replies via the Cloud API. Mirrors `plugins/omi-telegram-app/` in shape (FastAPI + JSON file storage + shared persona client), but uses the Meta WhatsApp Business Cloud API (`graph.facebook.com/v22.0`) instead of the Telegram Bot API.

## Setup (Meta Business)

1. Create a Meta Business app at [developers.facebook.com](https://developers.facebook.com) and add the **WhatsApp** product.
2. From the WhatsApp product page, copy:
   - **Phone number ID** (e.g. `123456789012345`)
   - **Permanent system user access token** (or a temporary token for testing; tokens expire in 24h)
3. Deploy this service to a public URL (e.g. via the desktop app launcher, or a public tunnel).
4. In the Meta App dashboard, under **WhatsApp → Configuration → Webhook**:
   - **Callback URL**: `https://your-public-url/webhook`
   - **Verify token**: a string of your choosing (e.g. `omi_clone_abc123`) — save this; you'll send it to `/setup`
   - Subscribe to **messages** webhook field
5. From the Omi desktop, click **AI Clone → WhatsApp → Connect**. Paste:
   - The access token
   - The phone number ID
   - Your chosen verify token (must match what you entered in Meta dashboard)
   - Your Omi UID + persona ID + `omi_dev_...` API key
   - Your public base URL
6. Click the deep link WhatsApp opens. Send the pre-filled message (which starts with `/start`). The plugin binds your phone to your Omi user.
7. Toggle **Auto-reply** in the Omi desktop (or call `POST /toggle` directly). Subsequent WhatsApp messages will be answered by your persona.

## Environment

- `WHATSAPP_APP_SECRET` (**required in production**) — your Meta App's App Secret. Used to verify `X-Hub-Signature-256` HMAC on every webhook delivery. **Must be set in production** — if unset, signature verification is skipped (dev only).
- `OMI_BASE_URL` (default: `https://api.omi.me`) — backend to call for persona chats.
- `NUDGE_COOLDOWN_SECONDS` (default: `14400` = 4h) — how often to re-send the "auto-reply disabled" message to a user who has the toggle off.
- `STORAGE_DIR` (default: `/app/data`) — where JSON files persist. Falls back to the plugin dir in dev.

## Endpoints

- `GET /health` — liveness.
- `GET /webhook` — Meta webhook verification handshake (`hub.mode=subscribe`).
- `POST /webhook` — receives WhatsApp webhook deliveries. Verifies `X-Hub-Signature-256` HMAC when `WHATSAPP_APP_SECRET` is set, handles `/start` handshake and auto-reply dispatch.
- `POST /setup` — registers the user's WhatsApp Business API creds, returns `{deep_link, phone_number_id, setup_token}`.
- `POST /toggle` — flips `auto_reply_enabled` for a given phone. Auth is the shared plugin bearer token (`Authorization: Bearer <AI_CLONE_PLUGIN_TOKEN>`); the request body is only `phone` + `enabled`. The Meta access_token is held by the plugin and NEVER requested over the chat tool surface.

## Architecture

- `main.py` — FastAPI app, routes.
- `whatsapp_client.py` — async wrapper around `graph.facebook.com/v22.0` (Cloud API).
- `simple_storage.py` — JSON-file persistence (users + pending_setups + nudge state).
- `persona_client.py` — re-export of `plugins/_shared/persona_client.py`.

## Security notes

- The Meta access token has full read/write access to your Meta Business portfolio, not just one bot — treat it as a top-tier secret. Never log it (full or partial), never include it in URLs, never echo it back to clients. The plugin holds it in storage; the chat tool surface (manifest + `/toggle` request body) deliberately does NOT include it.
- The webhook signature (`X-Hub-Signature-256`) must be verified in production by setting `WHATSAPP_APP_SECRET`. Without it, anyone who knows your webhook URL can forge messages.
- The `/toggle` endpoint is gated by the shared `AI_CLONE_PLUGIN_TOKEN` bearer (set via the plugin's env / `OMI_DEV_MODE=1` in dev). It returns the same 403 for unknown phone to prevent phone enumeration, even though the bearer holder is already authenticated.

## Tests

The async tests in this plugin require `pytest-asyncio`. Install both production and dev deps first:

```bash
cd plugins/omi-whatsapp-app
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest test/ -v
```

The shared client tests (`plugins/_shared/test/`) are separate; see `plugins/_shared/README.md` for their test instructions.

## Differences from `plugins/omi-telegram-app/`

| Concern | Telegram | WhatsApp Cloud API |
|---------|----------|-------------------|
| API base | `api.telegram.org/bot<token>/...` | `graph.facebook.com/v22.0/{phone_number_id}/...` |
| Bot identification | bot token in URL | access token in `Authorization: Bearer` header |
| Webhook verification | Header on every POST (`X-Telegram-Bot-Api-Secret-Token`) | GET query params on first connect (`hub.mode=subscribe`) |
| Webhook auth (subsequent) | Same header | `X-Hub-Signature-256` HMAC-SHA256(APP_SECRET, body) |
| User identifier | chat_id (integer) | from phone number (E.164 string) |
| Deep link | `https://t.me/<bot_username>?start=<token>` | `https://wa.me/<display_phone>?text=<urlencoded /start token>` |