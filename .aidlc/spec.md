# AI Clone — Spec

> Track 2 of PLAN.md. Omi responds to people on the user's behalf via Telegram, WhatsApp, iMessage. Source: `PLAN.md` + the existing `plugins/omi-slack-app/` pattern.

## Problem & judgment

**What:** When a message arrives in Telegram / WhatsApp / iMessage, Omi auto-replies using the user's persona — their voice, their memories, their context.

**How the user judges it:**

1. *Answers personal questions well.* Reuse the existing `generate_persona_prompt()` + `execute_persona_chat_stream()` (in `backend/utils/llm/persona.py` and `backend/utils/retrieval/graph.py`). The plugins are thin transports; the persona engine is unchanged.
2. *Connects to chat apps easily.* Setup <2 minutes per platform: paste a bot token, scan a QR, grant a permission. No fiddly webhook tunneling for the user.
3. *Good and simple UI in the Omi desktop app.* One screen lists all clones, each shows status (connected / paused / error), a master per-platform toggle, and a "Test reply" button.

## Design principle: mirror `omi-slack-app`

The existing `plugins/omi-slack-app/` is the template. Each new plugin is a **standalone Python FastAPI app** in its own folder, deployed independently, with the same structure:

```
plugins/omi-<provider>-app/
├── main.py                 # FastAPI app, webhook + setup + health
├── <provider>_client.py    # wrapper around the platform's SDK/HTTP API
├── simple_storage.py       # JSON-file persistence (verbatim copy of omi-slack-app's)
├── persona_client.py       # calls POST /v2/integrations/{app_id}/user/persona-chat
├── requirements.txt        # fastapi, uvicorn, httpx, <provider SDK>
├── Dockerfile
├── README.md
├── Procfile / railway.toml # matches omi-slack-app deploy shape
└── runtime.txt
```

No new framework. No unified SDK layer. No TypeScript service. The only shared code is the `persona_client.py` (3 short functions) and `simple_storage.py` schema extension (one new key per user). Every other file is provider-specific.

### Why per-provider plugins, not a unified service

The honest tradeoff:

- **3 plugins = 3x boilerplate** (FastAPI app skeleton, Dockerfile, Procfile). Each is ~150 LOC of glue.
- **3 plugins = 3x deployment surface** (3 Railway/Render services).
- **Counterweight:** each plugin is dumb. A Telegram bug does not affect WhatsApp. iMessage has different lifecycle constraints (must run on the user's Mac with Full Disk Access) and a different transport (long-poll `chat.db` watch instead of HTTP webhook), so forcing it into a unified runtime complicates its real constraints instead of simplifying them.

This is the same tradeoff the existing `omi-slack-app` already makes. We do not introduce a new abstraction to solve a problem the codebase has not yet felt.

## Components

### Component 1: `plugins/omi-telegram-app/` (new)

**Files** (all Python 3.11):

- `main.py` — FastAPI app exposing `POST /webhook` (Telegram update payload), `GET /setup?token=...` (bot linking flow), `GET /health`, `POST /toggle` (from Chat Tools).
- `telegram_client.py` — wraps `httpx.AsyncClient` against `api.telegram.org/bot<token>/...`. Two methods: `set_webhook(url)`, `send_message(chat_id, text)`.
- `persona_client.py` — calls `POST /v2/integrations/{app_id}/user/persona-chat` with `{"text": incoming_message}` using the user's stored dev API key.
- `simple_storage.py` — verbatim copy of `plugins/omi-slack-app/simple_storage.py` plus one new key per user: `telegram_chat_id → { omi_uid, persona_id, omi_dev_api_key, auto_reply_enabled, app_id }`. (Schema is `Dict[str, dict]` keyed by `telegram_chat_id` instead of `uid` — Telegram has no uid concept pre-link.)
- `requirements.txt` — `fastapi==0.104.1`, `uvicorn[standard]==0.24.0`, `httpx==0.25.2`, `python-dotenv==1.2.2`.

**Flow** (`main.py`):

```python
@app.post("/webhook")
async def telegram_webhook(update: dict):
    msg = update.get("message") or update.get("edited_message")
    if not msg or not msg.get("text"):
        return {"ok": True}
    chat_id = str(msg["chat"]["id"])
    sender_id = str(msg["from"]["id"])
    text = msg["text"]
    user = storage.get_by_chat_id(chat_id)
    if not user or not user.get("auto_reply_enabled"):
        return {"ok": True}
    if safety.is_own_message(user, sender_id):
        return {"ok": True}
    reply = await persona_client.chat(user, text)         # streaming → join
    await telegram_client.send_message(chat_id, reply)
    return {"ok": True}
```

**Setup flow:** user clicks "Connect Telegram" in the Omi desktop → desktop opens `https://t.me/<bot_username>?start=<setup_token>` → bot DMs the user → user pastes the deep-link token in `/setup?token=...` → bot stores `chat_id → omi_uid` and asks the user to paste their `omi_dev_...` API key + persona id.

### Component 2: `plugins/omi-whatsapp-app/` (new)

Identical structure to Telegram. Differences:

- Uses the **Meta WhatsApp Cloud API** (production) or **Twilio sandbox** (dev). Pick Meta Cloud for v1 — Twilio's sandbox has UX papercuts the user will feel.
- Webhook payload shape: `{ "from": "...", "body": "..." }` (Twilio) or `{ "entry": [{"changes": [{"value": {"messages": [...]}}]}] }` (Meta).
- `whatsapp_client.py` wraps `httpx.AsyncClient` against `graph.facebook.com/v18.0/<phone_number_id>/messages`.
- `requirements.txt` adds nothing platform-specific — `httpx` is enough. We do NOT add the `twilio` SDK; it is dead weight when we use Meta directly.

### Component 3: `plugins/omi-imessage-app/` (new, local-only)

This one is **different from the other two** because iMessage has no webhook — it has a local SQLite database (`~/Library/Messages/chat.db`). The plugin must run on the user's Mac.

**Files:**

- `main.py` — FastAPI app exposing `GET /health`, `POST /toggle`, plus a **long-running background task** that polls `chat.db` for new rows.
- `imessage_db.py` — sqlite3 wrapper. One query: `SELECT ROWID, text, is_from_me, handle_id, datetime(date/1000000000 + strftime('%s','2001-01-01'), 'unixepoch') AS ts FROM message WHERE ROWID > ? ORDER BY ROWID ASC`. Joins to `handle` table for phone number.
- `imessage_client.py` — wraps `osascript` (`tell application "Messages" to send ...`) — AppleScript is the supported way to send iMessages without private APIs.
- `persona_client.py` — same as Telegram.
- `simple_storage.py` — copy with `phone_or_email → {...}` keys.
- `requirements.txt` — `fastapi`, `uvicorn`, `httpx`, `python-dotenv`. Nothing more.

**Flow:**

```python
# main.py — background poller
async def poll_chat_db():
    last_rowid = storage.get_last_seen_rowid()
    while not stop_event.is_set():
        rows = imessage_db.fetch_new(last_rowid)
        for row in rows:
            last_rowid = max(last_rowid, row["ROWID"])
            if row["is_from_me"]:
                continue                                # never reply to yourself
            user = storage.get_by_handle(row["handle_id"])
            if not user or not user.get("auto_reply_enabled"):
                continue
            reply = await persona_client.chat(user, row["text"])
            imessage_client.send(user["handle_id"], reply)
        storage.set_last_seen_rowid(last_rowid)
        await asyncio.sleep(2)                          # 2s poll cadence
```

**Deployment:** runs as a child process of `Omi Dev` / `Omi Beta` desktop (`run.sh` starts it on port `OMI_IMESSAGE_BRIDGE_PORT`, default 47801). Production-shaped: a `launchd` plist at `~/Library/LaunchAgents/com.omi.imessage-bridge.plist` for always-on. **Full Disk Access** is required to read `chat.db` — the bridge refuses to start without it and surfaces a one-line macOS prompt.

### Component 4: Backend — `POST /v2/integrations/{app_id}/user/persona-chat`

Location: `backend/routers/integration.py`, alongside `create_conversation_via_integration` (line 68).

```python
@router.post('/v2/integrations/{app_id}/user/persona-chat')
async def persona_chat_via_integration(
    request: Request,
    app_id: str,
    uid: str,
    body: PersonaChatRequest,                            # {text: str}
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    api_key = authorization.replace('Bearer ', '')
    if not await run_blocking(critical_executor, verify_api_key, app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid integration API key")
    await run_blocking(critical_executor, check_rate_limit_inline, f"{app_id}:{uid}:persona", "integration:persona")

    app = await run_blocking(db_executor, apps_db.get_app_by_id_db, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    enabled = await run_blocking(db_executor, redis_db.get_enabled_apps, uid)
    if app_id not in enabled:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")
    if not apps_utils.app_can_persona_chat(app):         # new capability gate
        raise HTTPException(status_code=403, detail="App does not have persona_chat capability")

    return StreamingResponse(
        _stream_persona_reply(uid, app_id, body.text),
        media_type="text/event-stream",
    )
```

`app_can_persona_chat(app)` is added to `backend/utils/apps.py` next to `app_can_create_conversation` (1-line capability check reading `app.capabilities`).

Streaming uses the existing `execute_persona_chat_stream(uid, text)` from `backend/utils/retrieval/graph.py:112`. No LLM changes.

**Auth:** app API key (`omi_dev_...`), same `verify_api_key(app_id, key)` used by 7+ existing endpoints in `integration.py`. The bridge plugins store the key on the user's machine during setup.

### Component 5: Desktop UI — Clone screen

New Flutter screen in `app/lib/ui/screens/clone_screen.dart`. Registered in `app/lib/app/routes.dart` (or wherever routes are listed — verify in `/implement` phase).

Contents:

- AppBar: "AI Clone"
- Per-platform card (Telegram, WhatsApp, iMessage):
  - Connection status: Connected (green dot + "Last reply 2m ago") / Not configured / Error (red dot + reason)
  - Master on/off switch (persisted via desktop chat-bridge POST /toggle)
  - "Test reply" button → triggers a synthetic inbound message through the plugin and shows the generated reply in a popup
  - "Disconnect" / "Connect" CTA
- Grouped under an "AI Clone" sidebar/menu entry next to "Apps" — not under Settings.

### Component 6: Chat Tools manifest (per plugin)

Each plugin exposes `/.well-known/omi-tools.json`:

```json
{
  "name": "omi-telegram-clone",
  "tools": [
    { "name": "toggle_auto_reply", "params": { "enabled": "boolean" } },
    { "name": "test_reply", "params": { "text": "string" } }
  ]
}
```

Surfaced in the Omi desktop chat surface per the existing `docs/doc/developer/backend/ChatTools.mdx:302-330` pattern. Plugins register themselves in `mcp/` (verify during `/implement`).

## Summary: what changes vs what's reused

| Item | Status | Location |
|------|--------|----------|
| Persona engine | Reused | `backend/utils/llm/persona.py`, `backend/utils/retrieval/graph.py` |
| Persona CRUD API | Reused | `backend/routers/apps.py /v1/user/persona` |
| App API key auth (`verify_api_key`) | Reused | `backend/routers/integration.py`, `backend/utils/apps.py:918` |
| Rate limit helper | Reused | `integration.py:check_rate_limit_inline` |
| Capability gate pattern | Reused + extended | new `apps_utils.app_can_persona_chat` |
| Telegram plugin | **Build** | `plugins/omi-telegram-app/` |
| WhatsApp plugin | **Build** | `plugins/omi-whatsapp-app/` |
| iMessage bridge (local, sqlite poll) | **Build** | `plugins/omi-imessage-app/` |
| `/v2/integrations/{app_id}/user/persona-chat` | **Build** | `backend/routers/integration.py` |
| Desktop Clone screen | **Build** | `app/lib/ui/screens/clone_screen.dart` |
| Existing `omi-slack-app` | Unchanged | `plugins/omi-slack-app/` |
| Desktop core (`Omi Dev`, `Omi Beta`) | Unchanged | — |

## Honest constraints (carried over from the existing pattern)

- **Bot token / API key is stored on the user's machine** in plaintext JSON. This matches `omi-slack-app`'s current posture. Rotating to OS keychain is a separate task.
- **No at-least-once delivery guarantees.** If the plugin crashes mid-reply, the message is lost. The existing `omi-slack-app` has the same property; we do not paper over it.
- **Persona engine quality** is owned by the persona team, not this cycle. We surface their output as-is.
- **No groups, no voice notes, no images.** v1 is text only, 1:1 chats only. Documented at the top of each plugin's README.

## Acceptance criteria

1. **Unit tests** for each plugin's `persona_client.py`, `simple_storage.py` round-trip, and webhook signature verification. ≥80% line coverage on the new code.
2. **Integration test** for the backend endpoint: `curl -X POST /v2/integrations/{app_id}/user/persona-chat` returns a streaming SSE response, time-to-first-token <500ms on a warm LLM.
3. **End-to-end manual test** per Desktop AGENTS.md: named bundle `omi-clone-test` connects a real Telegram bot to a real Omi persona; user sees the reply in Telegram. Screenshot evidence to `/tmp/evidence.png` via `agent-swift`.
4. **iMessage FDA prompt** verified on a clean macOS user — bridge refuses to start without Full Disk Access and surfaces a one-line prompt.
5. **Flutter UI** verified with `agent-flutter snapshot -i`; "Test reply" returns a non-empty response from the persona for all three providers.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| 3 plugins = 3x deploy surface | Each is dumb and standalone; debug one does not block others |
| iMessage needs Full Disk Access — extra permission friction | One-line macOS prompt; documented at setup |
| Bot token leak from JSON file | Matches existing `omi-slack-app` posture; OS keychain migration is a separate cycle |
| Persona replies in wrong chat | Per-(chat_id, handle_id) routing; unit test pins |
| Auto-reply loop (Omi replies to itself) | `is_from_me` / sender-id check at top of webhook handler |
| Rate-limit on `execute_persona_chat_stream` | Reuse existing rate limit per app+user; 10/hour matches `MAX_NOTIFICATIONS_PER_HOUR` in `integration.py:30` |

## Open questions — resolved

1. **Unified vs split?** → **Split, per-provider Python plugins** (matches `omi-slack-app`, no new framework).
2. **Self-hosted from day one?** → **Yes, skip Photon Cloud.**
3. **Desktop screen placement?** → **Sidebar entry next to "Apps"** (not Settings).
4. **Slack plugin** → **Leave alone.** Same pattern, separate AIDLC cycle if we ever unify.

## Out of scope

- Voice notes, images, group chats.
- OS keychain migration of stored tokens.
- Replacing `omi-slack-app`.
- Photon Cloud / spectrum-ts / any unified TS bridge.

_Updated: 2026-06-27T15:50:00Z_