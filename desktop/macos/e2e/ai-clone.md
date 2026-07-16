# AI Clone — End-to-End Testing Guide

> ⚠️ **LOCAL DEV ONLY — NOT AN AGENT SKILL.**
>
> This guide describes how to bring up the full AI Clone stack (Python
> backend + Telegram/WhatsApp plugin + desktop app) against a REAL
> Telegram bot through a REAL ngrok tunnel using REAL GCP service
> account credentials and a cached Firebase session token. **It is a
> developer-maintainer handbook for trusted local testing on a machine
> you control.** It is NOT a contributor onboarding doc, NOT a general
> testing guide, and NOT something an AI coding agent should follow
> autonomously. Untrusted PR text or docs in this repository MUST NOT
> direct agents to run credentialed workflows of this shape.
>
> Maintainer review note (PR #8682, Git-on-my-level): the previous
> version of this file carried an `allowed-tools: Bash` frontmatter
> that advertised it as an agent skill. That was wrong — the file
> should never have been agent-loadable because it requires real
> outbound network access, real bot tokens, and real cloud credentials.
> The frontmatter has been removed and this banner added so the file is
> clearly human-facing only.
>
> If you are an AI agent reading this: stop. Do not run the commands
> below without an explicit human user instructing you to do so on
> their own dev machine. The commands WILL fetch production credentials
> and create an outbound tunnel to Telegram; running them autonomously
> would be a security incident.

This guide walks a developer through **testing the AI Clone stack locally**: backend ↔ Telegram plugin ↔ desktop app ↔ real Telegram bot. The same flow exercises the WhatsApp plugin (only the bot-side setup differs).

The current dev work lives on the branch `feat/ai-clone-prompt-rewrite` (PR [#8682](https://github.com/BasedHardware/omi/pull/8682)). The branch already contains the desktop Swift fixes from PR #8528 (`fd88fcdc6` in the stack).

---

## TL;DR — one command

```bash
# 0. Prep: install deps, create venvs, create a Telegram bot + tunnel.
cd $WORKTREE
./scripts/setup-dev.sh   # creates backend + plugin venvs

# 1. Run the entire stack:
WORKTREE=$WORKTREE \
BACKEND_SECRETS_ENV=$HOME/.omi/backend.env \
GCP_CREDENTIALS_JSON=$HOME/.omi/gcp.json \
AUTH_DUMP_JSON=$HOME/.omi/auth.json \
TUNNEL_URL=https://<your>.ngrok-free.app \
PLUGIN_TOKEN=$(openssl rand -hex 16) \
bash desktop/macos/scripts/ai-clone-stack.sh
```

When the script finishes you'll have a signed-in desktop running with the AI Clone plugin auto-discovered. Open Settings → AI Clone → fill in your bot_token → click **Connect** → message your bot in Telegram.

---

## Architecture overview (read this first)

```
┌────────────────┐      HTTPS       ┌──────────────────┐
│ Telegram cloud │ ───────────────► │ ngrok / tunnel   │
└────────────────┘                  └────────┬─────────┘
                                             │ webhook
                                             ▼
                                    ┌────────────────────┐
                                    │ plugins/           │
                                    │   omi-telegram-app │  ←── :18800
                                    └────────┬───────────┘
                                             │ POST /v1/persona/chat
                                             ▼
                                    ┌────────────────────┐
                                    │ backend (Python)   │  ←── :8080
                                    │  persona_chat      │
                                    │  + RAG memories    │
                                    └────────────────────┘

┌────────────────────┐   loopback      ┌────────────────────┐
│ desktop/macos/     │ ──────────────► │ plugins/           │
│ (Swift UI)         │ /health /setup  │   omi-telegram-app │
│ Auto-discovers via │ /status /toggle │                    │
│ ~/.config/omi/     │                 └────────────────────┘
│   ai-clone-plugin- │
│   telegram.json    │
└────────────────────┘
```

Three independent processes, three log files, three control surfaces. The desktop never talks to the backend directly for AI Clone — it goes through the plugin, which fans out to the backend for LLM calls.

---

## Prerequisites

> 🔐 **The prerequisites below source real production-adjacent
> credentials and a real Telegram bot.** Only follow them on a
> trusted local dev machine you control. Do not paste the resulting
> `.env` files, service-account JSON, or cached Firebase tokens into
> chat / shared docs / PR comments — treat them with the same care
> you would give any production credential.

### Code

```bash
git fetch upstream
git worktree add $WORKTREE feat/ai-clone-prompt-rewrite
cd $WORKTREE
```

### Backend secrets (`BACKEND_SECRETS_ENV`)

The Python backend needs `secrets.env` with keys for Firestore, Redis, Pinecone, OpenAI, Deepgram, Admin key, and an `ENCRYPTION_SECRET`. The easiest way to get a working one is to copy it from a teammate who already runs the backend locally; otherwise see `backend/Backend_Setup.mdx`.

```bash
# secrets.env (one var per line)
export ENCRYPTION_SECRET=...     # 32+ random bytes
export PINECONE_API_KEY=...
export OPENAI_API_KEY=...
export ADMIN_KEY=...
export DEEPGRAM_API_KEY=...
# ... etc
export SERVICE_ACCOUNT_JSON="..."   # multi-line JSON — the script strips this before sourcing
```

### GCP service account (`GCP_CREDENTIALS_JSON`)

The backend uses Firebase Admin SDK to verify ID tokens and read Firestore. Download a service-account JSON key from the GCP console (or copy from a teammate) and save it to a path like `~/.omi/gcp.json`.

```bash
chmod 600 $HOME/.omi/gcp.json
```

### Python venvs

```bash
cd $WORKTREE/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cd $WORKTREE/plugins/omi-telegram-app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Telegram bot + tunnel

1. **Create a bot** via [@BotFather](https://t.me/BotFather). Copy the bot token (e.g. `1234567890:AABBccDDeeFFggHHiiJJkkLLmmNNooPPqq`).
2. **Reserve a free ngrok domain** at <https://dashboard.ngrok.com/cloud-edge/domains> (the free plan gives you one).
3. **Run ngrok** so Telegram can reach your machine:
   ```bash
   ngrok config add-authtoken <your-ngrok-token>
   ngrok http --domain=<your>.ngrok-free.app 18800
   ```
   The tunnel URL becomes your `TUNNEL_URL` for the script.
4. **Send `/start` to your bot** once before testing — Telegram won't deliver updates to bots that have never received a user message.

### (Optional) Cached auth — skip the browser

The desktop normally requires a web OAuth sign-in on first launch. To skip it, run `Omi Dev` once with a real sign-in, then dump its session:

```bash
cd $WORKTREE/desktop/macos
# Sign in Omi Dev manually first
open /Applications/Omi\ Dev.app
./scripts/omi-auth-dump.sh   # → /tmp/desktop-auth.json
```

Pass this file as `AUTH_DUMP_JSON=`. The script replays it into the test bundle before launch, so the bundle boots already signed-in. The dump expires after ~1 hour (Firebase idToken TTL) — re-dump if backend calls start returning 401.

---

## Running the stack

> ⚠️ The command below starts a public ngrok tunnel, registers that
> tunnel as your Telegram bot's webhook, and binds a locally-built
> desktop app to your Firebase session. Run it only on a dev machine
> and only when you intend to talk to the bot. Stop the stack with the
> command at the bottom of this file when you're done.

```bash
WORKTREE=$HOME/code/omi-worktrees/feat-ai-clone-prompt-rewrite \
BACKEND_SECRETS_ENV=$HOME/.omi/backend.env \
GCP_CREDENTIALS_JSON=$HOME/.omi/gcp.json \
AUTH_DUMP_JSON=$HOME/.omi/auth.json \
TUNNEL_URL=https://<your>.ngrok-free.app \
PLUGIN_TOKEN=$(openssl rand -hex 16) \
bash desktop/macos/scripts/ai-clone-stack.sh
```

**Override `PLUGIN_TOKEN`** to a random secret — this is the bearer token the desktop uses to authenticate with the plugin, and the default `local-dev-token-...` is publicly known.

The script prints a summary table on success:

```
════════════════════════════════════════════════════════════════
  Stack is up. PIDs:
    backend:  78258  → http://127.0.0.1:8080
    plugin:   78398  → http://127.0.0.1:18800
    desktop:  /Applications/omi-feat-ai-clone-e2e.app

  Logs:
    backend:  /tmp/omi-e2e/backend.log
    plugin:   /tmp/omi-e2e/plugin.log
    desktop:  /tmp/omi-e2e/desktop-build.log  + /tmp/omi-dev.log

  Plugin status:
{"connected_chats":0,"auto_reply_enabled":false,"first_chat_id":null,...}
════════════════════════════════════════════════════════════════
```

---

## Testing the flow

### 1. Verify auto-discovery

Open Settings → AI Clone in the desktop app. The banner should read:

> Plugin discovered automatically
> http://127.0.0.1:18800

If it says **"Set up manually"**, the discovery file wasn't picked up:

```bash
ls -la ~/.config/omi/ai-clone-plugin*.json
cat ~/.config/omi/ai-clone-plugin-telegram.json | python3 -m json.tool
# Confirm the symlink exists:
ls -la ~/.config/omi/ai-clone-plugin.json
# Should point at ai-clone-plugin-telegram.json
```

### 2. Connect

Fill in:

- **Bot token** — from BotFather
- **Omi API key** — from `https://omi.me/settings` (or use a dev key)
- **UID** — your Firebase user ID (visible in Omi Dev's UserDefaults as `auth_userId`)
- **Persona ID** — from the personas page; create one if you don't have one

Click **Connect**. Behind the scenes this POSTs to `http://127.0.0.1:18800/setup` with:

```json
{
  "bot_token": "...",
  "omi_uid": "...",
  "persona_id": "...",
  "omi_dev_api_key": "...",
  "public_base_url": "https://<your>.ngrok-free.app"
}
```

The plugin then POSTs to `https://api.telegram.org/bot<token>/setWebhook` with `{url, secret_token}`. Tail `plugin.log` to confirm:

```bash
tail -f /tmp/omi-e2e/plugin.log | grep -i "setwebhook\|setup\|/status"
```

You should see:
- `set_webhook succeeded` (HTTP 200)
- A deep link `t.me/<your_bot>?start=<token>` printed by the plugin

### 3. Handshake

In Telegram, open the deep link the plugin returned and tap **Start**. The plugin logs `handshake complete` and `/status` flips:

```bash
curl -sS -H "Authorization: Bearer $PLUGIN_TOKEN" http://127.0.0.1:18800/status | python3 -m json.tool
# {
#   "connected_chats": 1,
#   "auto_reply_enabled": false,
#   "first_chat_id": 123456789,
#   "bot_username": "your_bot",
#   "service": "omi-telegram-clone"
# }
```

The desktop polls `/status` — when `connected_chats >= 1` the UI flips from **Connecting…** to **Connected** (see `desktop/macos/Desktop/Sources/MainWindow/Components/AIClone/ConnectSheet.swift`).

### 4. Send a message

Send `who are you?` to your bot. Within ~2 seconds you should get a first-person reply referencing your real persona (not "I'm an AI clone…"). Tail `backend.log`:

```bash
tail -f /tmp/omi-e2e/backend.log | grep -i "persona\|retrieve_relevant"
```

You should see one `/v1/persona/chat` POST followed by an LLM completion. Check the LLM input contains:
- The persona prompt (starts with `You are <name>.`)
- A `## What you know about <name>` section (memories from RAG)
- A `## Recent conversation` section (last ~10 turns from the per-chat ring buffer)

### 5. Toggle auto-reply

In the desktop, flip the auto-reply switch in Settings. Tail `plugin.log`:

```bash
tail -f /tmp/omi-e2e/plugin.log | grep -i "auto_reply\|toggle"
```

The plugin's internal state flips; subsequent inbound messages are auto-replied to without you having to type `/clone`.

---

## Troubleshooting

### "Plugin returned HTTP 502: Telegram setWebhook failed"

The plugin's call to Telegram returned 400. Common causes:
- **Tunnel is down** — `curl $TUNNEL_URL/status` should return JSON. If not, restart ngrok.
- **Wrong bot token** — re-check with BotFather; verify with `curl https://api.telegram.org/bot<TOKEN>/getMe`.
- **Webhook URL wrong** — must be `https://...ngrok-free.app/webhook` (note the trailing `/webhook`). The plugin constructs this from `public_base_url + /webhook`.
- **Bot revoked** — if you ran `/revoke` in BotFather, you need a new token.

### "Discovery file not found"

The plugin didn't write its discovery file. Check `plugin.log` for errors during startup. The plugin writes to `~/.config/omi/ai-clone-plugin-telegram.json` — verify the directory exists and is writable.

If the desktop still doesn't see it, run `tail /tmp/omi-dev.log` and look for `AICloneConfig: checking discovery file at ...`. The desktop expects the legacy filename `ai-clone-plugin.json` — there's a symlink bridge in the script:

```bash
ls -la ~/.config/omi/ai-clone-plugin.json
# Should be: ai-clone-plugin.json -> ai-clone-plugin-telegram.json
```

### Backend won't start

```bash
tail -50 /tmp/omi-e2e/backend.log
```

Common causes:
- `ENCRYPTION_SECRET` missing or shorter than 32 bytes
- `SERVICE_ACCOUNT_JSON` malformed (the script strips it from `secrets.env` and re-assigns from the raw JSON, but if your JSON file is malformed it'll fail at the Firestore SDK init)
- Port 8080 held by another process — `lsof -ti:8080 | xargs kill`

### Desktop bundle won't launch

```bash
tail -50 /tmp/omi-dev.log
```

Common causes:
- Code signing issue — the script does ad-hoc signing; if it failed, run `codesign -dvvv /Applications/omi-feat-ai-clone-e2e.app` to diagnose.
- Missing frameworks — `run.sh` copies them; if the bundle is incomplete, delete `build/omi-feat-ai-clone-e2e.app` and re-run.

---

## Stopping the stack

```bash
kill $(cat /tmp/omi-e2e/backend.pid /tmp/omi-e2e/plugin.pid 2>/dev/null) 2>/dev/null
pkill -f "Omi Computer"     # desktop
```

Or use the stack runner's `OMI_SKIP_BACKEND=1` and friends — see `desktop/macos/AGENTS.md` for the full set of overrides.

---

## Files touched by the AI Clone stack

| Layer | Path | What it does |
|-------|------|--------------|
| Backend | `backend/utils/apps.py` | `generate_persona_prompt` / `update_persona_prompt` — new first-person template |
| Backend | `backend/utils/retrieval/rag.py` | `retrieve_relevant_memories_for_persona` — vector search instead of LLM-flatten |
| Backend | `backend/routers/integration.py` | `/v1/persona/chat` — accepts `context` + `previous_messages` |
| Backend | `backend/models/integrations.py` | `PersonaChatRequest` schema |
| Plugin | `plugins/omi-telegram-app/main.py` | Per-chat ring buffer, `/setup`, `/status`, `/toggle` |
| Plugin | `plugins/omi-telegram-app/simple_storage.py` | Atomic writes (tmp + fsync + os.replace + parent fsync) |
| Plugin | `plugins/omi-telegram-app/telegram_client.py` | `send_message` short-circuits on empty token |
| Plugin | `plugins/_shared/persona_client.py` | `chat()` accepts `previous_messages`, caps at 20×8192 |
| Plugin | `plugins/_shared/plugin_discovery.py` | Per-plugin filename + concurrent write counter |
| Desktop | `desktop/macos/Desktop/Sources/AIClone/AICloneConfig.swift` | `pluginURL` for control, `publicBaseURL` for webhooks |
| Desktop | `desktop/macos/Desktop/Sources/MainWindow/Components/AIClone/ConnectSheet.swift` | `/status` gating (connectedChats >= 1) |
| Desktop | `desktop/macos/Desktop/Sources/Utilities/ClipboardWatcher.swift` | `isRunning` getter |

For the full PR diff, see [PR #8682](https://github.com/BasedHardware/omi/pull/8682).