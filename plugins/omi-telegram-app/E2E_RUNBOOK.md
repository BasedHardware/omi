# Telegram AI Clone — local E2E test runbook

Three layers. Run them in order; each layer builds on the previous.

| Layer | What it proves | Time | Requires |
|-------|----------------|------|----------|
| **1. Plugin only** | The Telegram plugin code is wired correctly end-to-end (no real Telegram, no real Omi persona). | 5 min | Python 3.11+ |
| **2. Plugin + real Telegram** | The plugin can register with Telegram and receive real updates. | 10 min | A real Telegram bot from @BotFather, a second Telegram account |
| **3. Full E2E** | A real Telegram message is auto-replied to with a persona response. | 15 min | All of the above + T-001 persona endpoint deployed to api.omi.me |

If you only have time for one: **Layer 1** caught the regression in commit `cc95e155d` ("send_message call lost in T-007 refactor"). It is the highest signal-to-noise check.

---

## Layer 1 — Plugin only (simulated)

Goal: prove the Telegram plugin's code path is correct without needing Telegram or Omi.

### Setup

```bash
cd /path/to/omi         # the worktree root
mkdir -p /tmp/omi-tg-e2e

# Create a venv (one-time)
python3.11 -m venv plugins/omi-telegram-app/.venv
plugins/omi-telegram-app/.venv/bin/pip install -r plugins/omi-telegram-app/requirements.txt
plugins/omi-telegram-app/.venv/bin/pip install requests
```

### Start the plugin

```bash
STORAGE_DIR=/tmp/omi-tg-e2e \
TELEGRAM_WEBHOOK_SECRET=test-secret-e2e \
OMI_BASE_URL=https://api.omi.me \
  plugins/omi-telegram-app/.venv/bin/uvicorn \
    --app-dir plugins/omi-telegram-app main:app \
    --host 127.0.0.1 --port 18800 --log-level info
```

### Seed a "bound" user

The /start handshake is what binds a chat_id to a user in production; for Layer 1 we write the storage file directly. (simple_storage loads `users_data.json` once at module load — restart the plugin after writing.)

```bash
echo '{"999001":{"chat_id":"999001","omi_uid":"test-uid-e2e","persona_id":"test-persona-e2e","omi_dev_api_key":"placeholder-key","bot_token":"placeholder-token","auto_reply_enabled":true,"created_at":"2026-06-29T00:00:00","updated_at":"2026-06-29T00:00:00"}}' \
  > /tmp/omi-tg-e2e/users_data.json

# Kill the plugin, restart it. The new process loads the file.
kill %1 ; sleep 1
STORAGE_DIR=/tmp/omi-tg-e2e TELEGRAM_WEBHOOK_SECRET=test-secret-e2e OMI_BASE_URL=https://api.omi.me \
  plugins/omi-telegram-app/.venv/bin/uvicorn --app-dir plugins/omi-telegram-app main:app \
  --host 127.0.0.1 --port 18800 --log-level info &
sleep 2
```

### Run the simulation

```bash
python plugins/omi-telegram-app/scripts/sim_e2e.py
```

Expected output (last line): `✓ All steps passed. Layer 1 E2E verified.`

What it asserts:
- `/health` returns 200
- `/.well-known/omi-tools.json` returns the manifest with `toggle_auto_reply`
- `/setup` rejects an obviously-invalid bot_token (4xx)
- `/webhook` rejects requests without the right secret (401)
- `/webhook` dispatches a regular message from the bound user to the persona endpoint (visible in plugin log as `POST /v2/integrations/test-persona-e2e/user/persona-chat`)
- `/webhook` silently drops `/start` from unknown chats, group chats, and malformed JSON
- `/toggle` accepts the right token (200), rejects the wrong token and unknown chat (both 403)

### Stash experiment — verify the dispatch path is real

After running Layer 1, do this to convince yourself the dispatch actually does something:

```bash
# In the plugin terminal, watch the log. Then in another terminal:
curl -X POST http://127.0.0.1:18800/webhook \
  -H 'X-Telegram-Bot-Api-Secret-Token: test-secret-e2e' \
  -H 'Content-Type: application/json' \
  -d '{"update_id":99,"message":{"message_id":99,"chat":{"id":999001,"type":"private"},"from":{"id":999001,"is_bot":false,"first_name":"Alice"},"text":"ping"}}'
```

You should see in the plugin log:
```
INFO httpx: HTTP Request: POST https://api.omi.me/v2/integrations/test-persona-e2e/user/persona-chat?uid=test-uid-e2e "HTTP/1.1 404 Not Found"
ERROR omi-telegram-clone: persona chat HTTP error for chat 999001: HTTP 404
```

That 404 is expected — `test-persona-e2e` doesn't exist in prod. The important thing is that the persona call fires at all. If you don't see it, `_dispatch_auto_reply` isn't running (or the user lookup failed).

### Stopping

```bash
kill %1   # in the plugin terminal
rm -rf /tmp/omi-tg-e2e
```

---

## Layer 2 — Plugin + real Telegram

Goal: prove the plugin can register its webhook with Telegram and receive real updates.

### Prereqs

- A Telegram account that can message a bot (you can use your own account; the bot you create will be able to DM you back).
- A second account (or a friend's account) to send the trigger message from. **You cannot trigger the auto-reply from the same account that owns the bot** because Telegram bots cannot initiate conversations.
- `cloudflared` installed (`brew install cloudflared`) — Telegram requires HTTPS for webhook delivery.

### Step 1: Create a real Telegram bot

1. Open Telegram on your phone.
2. Search for `@BotFather`, send `/newbot`.
3. Answer the prompts (give it a name and a unique username ending in `bot`).
4. BotFather replies with a token like `1234567890:ABC...`. **Save this.**

### Step 2: Start the plugin with a public tunnel

```bash
mkdir -p /tmp/omi-tg-e2e
STORAGE_DIR=/tmp/omi-tg-e2e \
TELEGRAM_WEBHOOK_SECRET=<paste-a-random-string> \
OMI_BASE_URL=https://api.omi.me \
  plugins/omi-telegram-app/.venv/bin/uvicorn \
    --app-dir plugins/omi-telegram-app main:app \
    --host 127.0.0.1 --port 18800 --log-level info &

# In another terminal — start a tunnel to the plugin
cloudflared tunnel --url http://localhost:18800
```

`cloudflared` will print a `https://...trycloudflare.com` URL. Save it as `$TUNNEL_URL`.

### Step 3: Configure the plugin URL in the Omi Desktop

Skip this for Layer 2 (we'll hit `/setup` directly with curl). You'll need it for Layer 3.

### Step 4: Register the webhook with Telegram

```bash
TUNNEL_URL=https://your-tunnel.trycloudflare.com
BOT_TOKEN=<your-bot-token>
SECRET=<your-telegram-webhook-secret>

curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=${TUNNEL_URL}/webhook" \
  -d "secret_token=${SECRET}"
```

Expected response: `{"ok":true,"result":true,"description":"Webhook was set"}`.

### Step 5: Send a message to your bot

From your second Telegram account:
1. Search for your bot's username (e.g. `@your_test_omi_bot`).
2. Tap **Start** or send any message.

The plugin's webhook will receive the update. In the plugin log you should see:
```
INFO:     127.0.0.1:XXXXX - "POST /webhook HTTP/1.1" 200 OK
```

### Step 6: Verify the chat_id binding

The `/start` path of the webhook handler will try to look up a pending setup token. Since we didn't go through `/setup`, it has no token to match. **The plugin will look up a `bot_token` for the chat, find nothing, and `telegram_client.send_message` will be called with an empty token — Telegram returns 404, the call fails silently, and no reply reaches your phone.** In the plugin log you'll see:

```
INFO httpx: HTTP Request: POST https://api.telegram.org/bot/sendMessage "HTTP/1.1 404 Not Found"
ERROR telegram_client: send_message failed for chat_id=999999: HTTP 404
```

The `/webhook` itself returns `200 OK` to Telegram (Telegram needs that — anything else triggers an infinite retry). So the **only** Layer 2 signal that the round-trip works is the `200 OK` in the plugin log, not anything on your phone. To actually see a Telegram reply from your bot, you need Layer 3 (which wires `/setup` first).

### Stopping

```bash
kill %1        # plugin
# Ctrl-C the cloudflared process
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook"
rm -rf /tmp/omi-tg-e2e
```

---

## Layer 3 — Full E2E (real Telegram + real persona)

Goal: a real Telegram message is auto-replied to using the user's Omi persona.

### Prereqs

All of Layer 2, plus:

- T-001 (the `POST /v2/integrations/{app_id}/user/persona-chat` endpoint) must be deployed to prod. PR #8437 is open as of this writing — merge it and run:
  ```
  gh workflow run gcp_backend.yml -f environment=prod -f branch=main
  ```
- A persona created for your user. In Omi desktop, open the **Persona** page and create one.
- A persona API key. From the same page, generate one (the desktop AI Clone screen does not yet have an inline key-creation flow — see gap G6).
- A second Telegram account (Layer 2 prereq).

### Step 1: Build the desktop with T-006

```bash
cd desktop/macos
git checkout feat/ai-clone-desktop
OMI_APP_NAME="omi-ai-clone-e2e" ./run.sh
```

This installs `/Applications/omi-ai-clone-e2e.app` and starts a local backend + tunnel for the desktop app. Auth is auto-seeded from "Omi Dev" if you have it signed in.

### Step 2: Configure the AI Clone plugin URL

In the Omi desktop app:
1. Open Settings (⌘+,)
2. Click **AI Clone**
3. In the **Plugin URL** field, paste your cloudflared tunnel URL (e.g. `https://abc.trycloudflare.com`).
4. (Optional) In the **Bearer token** field, paste a token if you've set one on the plugin side (currently the plugin doesn't enforce it — see gap G10).
5. In the **Developer API key** field, paste your `omi_dev_...` key.

### Step 3: Connect Telegram

1. In the AI Clone page, find the **Telegram** card.
2. Click **Connect**. A sheet opens.
3. Fill in:
   - **Bot token**: your real bot token from Layer 2
4. Click **Connect**. The plugin calls `POST /setup` against your tunnel URL. Telegram registers the webhook. The sheet now shows a deep link: `https://t.me/<your_bot>?start=<token>`.

### Step 4: Tap the deep link

On your phone (the account that owns the bot), tap the deep link. Telegram opens your bot with `/start <token>` pre-filled. Send it.

The plugin receives the `/start`, binds your chat_id to your Omi uid, and replies with "Connected! Open the Omi desktop and toggle AI Clone → Telegram to start receiving auto-replies."

The desktop's Connect sheet polls `/health` and detects the binding. The sheet's UI transitions to "Connected."

### Step 5: Toggle auto-reply on

In the desktop, flip the **Auto-reply** switch on the Telegram card.

### Step 6: Send a real message from the second account

From your second Telegram account, send any message to your bot. e.g. "what's my favorite coffee?"

### Step 7: Verify the persona reply

The bot replies with a persona-grounded answer. Check:
- The reply actually arrives (the dispatch path fired end-to-end).
- The reply references the user's memories / persona style (the persona engine ran).
- The reply is plausibly "you" (no generic LLM fallback).

If the reply arrives but is generic, the persona record is empty. Open the Persona page and ensure `persona_prompt` is populated.

---

## What this runbook doesn't cover

- iMessage — explicitly out of scope per the user
- WhatsApp — separate plugin; the WhatsApp plugin's `E2E_RUNBOOK.md` (if/when it exists) would mirror this one with Meta's WhatsApp Business Cloud API instead of Telegram's Bot API
- Multi-user concurrent load — out of scope for verifying the feature works; load testing is a separate concern
- Production deploy — `desktop/macos/run.sh --yolo` is for local dev; CI/CD for plugins is via their respective Dockerfiles

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `curl /health` hangs | Plugin not running | Re-check the `uvicorn` process is alive |
| `curl /webhook` returns 401 | `TELEGRAM_WEBHOOK_SECRET` mismatch | Make sure the env var passed to uvicorn matches the `secret_token` set on the webhook |
| `POST /setup` returns `Telegram setWebhook failed` | Invalid bot token, or the public URL doesn't resolve | Check the token at `@BotFather`, check `cloudflared` is still up |
| Auto-reply fires but no message arrives in Telegram | The `send_message` call is broken | Re-run Layer 1 — if it passes, the production code is fine. If it fails, see `git log -- plugins/omi-telegram-app/main.py` for the regression. |
| Persona call returns 404 | T-001 not deployed to prod | Check `https://api.omi.me/v2/integrations/{app_id}/user/persona-chat` returns 404 — that means the endpoint isn't deployed. Deploy PR #8437. |
| `chat_messages.enabled` keeps flipping to `true` | Not a real issue — v0.1 ships with `false` and that's by design (see gap G14 in `.aidlc/gaps.md`) | None — leave it `false` until the proactive notification API lands. |