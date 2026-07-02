# OMI Telegram AI-Clone plugin

Lets Omi reply to people on the user's behalf in Telegram, using the user's persona.

Self-hosted FastAPI service. Receives Telegram webhook updates, calls the Omi persona API, and replies. Mirrors `plugins/omi-slack-app/` in shape.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather), copy the bot token.
2. Deploy this service to a public URL (e.g. via the desktop app launcher, or a public tunnel).
3. From the Omi desktop, click **AI Clone → Telegram → Connect**. Paste the bot token + your Omi UID + persona ID + `omi_dev_...` API key. The service registers the webhook with Telegram and returns a deep link.
4. Click the deep link on the device where Telegram is signed in. Send `/start` to the bot. The plugin binds your `chat_id` to your Omi user.
5. Toggle **Auto-reply** in the Omi desktop (or call `POST /toggle` directly). Subsequent Telegram messages will be answered by your persona.

## Environment

- `TELEGRAM_WEBHOOK_SECRET` (**required in production**) — shared secret for `X-Telegram-Bot-Api-Secret-Token`. **Must be set in production** — if unset, a random value is generated at startup. Restarting the service then changes the secret, which invalidates the webhook with Telegram (subsequent updates fail signature verification until you re-run setup).
- `OMI_BASE_URL` (default: `https://api.omi.me`) — backend to call for persona chats.
- `NUDGE_COOLDOWN_SECONDS` (default: `14400` = 4h) — how often to re-send the "auto-reply disabled" message to a user who has the toggle off.
- `STORAGE_DIR` (default: `/app/data`) — where JSON files persist. Falls back to the plugin dir in dev.

## Endpoints

- `GET /health` — liveness.
- `POST /setup` — register a bot token, returns `{deep_link, bot_username, setup_token}`.
- `POST /webhook` — receives Telegram updates. Verifies `X-Telegram-Bot-Api-Secret-Token`, dispatches to the persona when auto-reply is on.
- `POST /toggle` — flips `auto_reply_enabled` for a given `chat_id`. Called by Chat Tools.

### `POST /toggle` — auth + body schema

The endpoint is gated by the **plugin bearer token** (set `AI_CLONE_PLUGIN_TOKEN` when launching the plugin; the desktop stores it in Keychain after reading `~/.config/omi/ai-clone-plugin.json`). The same 401 is returned for missing and wrong bearer so the endpoint can't be probed. The chat assistant never sees the bearer token — it's held in the desktop / Keychain.

Request body (JSON):

```json
{
  "chat_id": "999001",
  "enabled": true
}
```

- `chat_id` — the Telegram chat id (string of int) to flip.
- `enabled` — bool, the new value of `auto_reply_enabled`.

The endpoint looks up the user by `chat_id` (the chat was bound to a specific Telegram bot during `/setup` / `/start` handshake — see Setup above). Returns `403` for unknown chat_id with no enumeration signal.

Response: `200 OK` with `{"chat_id": "999001", "auto_reply_enabled": true}` on success.

> **Security note** — the manifest deliberately does NOT require the user to paste the bot token in chat. Long-lived platform secrets never transit through the chat assistant (chat history, tool-call logs, traces, model context). This was an explicit design decision per the maintainer security review on PR #8531.

## Architecture

- `main.py` — FastAPI app, routes.
- `telegram_client.py` — async wrapper around `api.telegram.org`.
- `simple_storage.py` — JSON-file persistence (users + pending_setups + nudge state).
- `persona_client.py` — re-export of `plugins/_shared/persona_client.py`.

## Tests

The async tests in this plugin require `pytest-asyncio`. Install both production and dev deps first:

```bash
cd plugins/omi-telegram-app
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest test/ -v
```

The shared client tests (`plugins/_shared/test/`) are separate; see `plugins/_shared/README.md` for their test instructions.