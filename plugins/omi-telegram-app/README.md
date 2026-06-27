# OMI Telegram AI-Clone plugin

Lets Omi reply to people on the user's behalf in Telegram, using the user's persona.

Self-hosted FastAPI service. Receives Telegram webhook updates, calls the Omi persona API, and replies. Mirrors `plugins/omi-slack-app/` in shape.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather), copy the bot token.
2. Deploy this service to a public URL (e.g. via the desktop app launcher, or a public tunnel).
3. From the Omi desktop, click **AI Clone → Telegram → Connect**. Paste the bot token + your Omi UID + persona ID + `omi_dev_...` API key. The service registers the webhook with Telegram and returns a deep link.
4. Click the deep link on the device where Telegram is signed in. Send `/start` to the bot. The plugin binds your `chat_id` to your Omi user.
5. Toggle **Auto-reply** in the Omi desktop. Subsequent Telegram messages will be answered by your persona.

## Environment

- `OMI_BASE_URL` (default: `https://api.omi.me`) — backend to call for persona chats.
- `TELEGRAM_WEBHOOK_SECRET` (optional) — shared secret for `X-Telegram-Bot-Api-Secret-Token`. If unset, a random value is generated at startup (survives restarts via env var).
- `STORAGE_DIR` (default: `/app/data`) — where JSON files persist. Falls back to the plugin dir in dev.

## Endpoints

- `GET /health` — liveness.
- `POST /setup` — register a bot token, returns `{deep_link, bot_username, setup_token}`.
- `POST /webhook` — receives Telegram updates. Verifies `X-Telegram-Bot-Api-Secret-Token`.

## Architecture

- `main.py` — FastAPI app, routes.
- `telegram_client.py` — async wrapper around `api.telegram.org`.
- `simple_storage.py` — JSON-file persistence (users + pending_setups).
- `persona_client.py` — re-export of `plugins/_shared/persona_client.py`.

Auto-reply (persona dispatch) is wired in T-004. This skeleton handles setup only.

## Tests

```bash
cd plugins/omi-telegram-app && python -m pytest test/ -v
```