# AI Clone — Plan

> Reads `.aidlc/spec.md`. One task per vertical slice. Each task is independently testable and lands on `feat/ai-clone` as its own commit.

## Ordering rationale

1. **Backend foundation first** — every plugin depends on the new endpoint, so it ships first and gets exercised by integration tests before the plugins build on top.
2. **Shared `persona_client` next** — three plugins import the same client; one canonical implementation, one test surface.
3. **Plugins in order of increasing complexity** — Telegram (simplest webhook), WhatsApp (similar with Meta payload shape), iMessage (local-only, sqlite poll, osascript, FDA). Each is a working slice before the next starts.
4. **Desktop UI after at least one plugin works end-to-end** — the Flutter screen is most useful when it has a real plugin behind it.
5. **Chat Tools manifest last** — it's the polish layer on top of the toggle endpoint that plugins already expose.

## Tasks

### T-001 · Backend: persona-chat endpoint + capability

- [x] Add `PersonaChatRequest` Pydantic model with `text: str` (min_length=1) + optional `context` dict.
- [x] Add `app_can_persona_chat(app)` capability check (1-line wrapper around `app_has_action(app, 'persona_chat')`).
- [x] Add `POST /v2/integrations/{app_id}/user/persona-chat` route: Bearer `omi_dev_...` auth via `verify_api_key`, `check_rate_limit_inline` rate-limit, app lookup, enabled-for-user check, capability gate, then stream via `execute_chat_stream`.
- [x] Unit tests: 14 green (capability 5, request model 3, endpoint auth/404/403/200 6).
- **Done**: `670585871`
- **Notes**: Test stubs use `__getattr__` to swallow long attribute lists from `utils.apps` imports. `run_blocking` is patched at the module level via an `AsyncMock`-backed router that dispatches by `id(fn)`. `Message` constructed inline with sender=human, type=text — same shape execute_chat_stream expects. The endpoint calls `apps_db.get_app_by_id_db` and `redis_db.get_enabled_apps` through `run_blocking` so the tests route by function id.

---

### T-002 · Shared `persona_client.py` module

---

### T-002 · Shared `persona_client.py` module

- [x] `plugins/_shared/persona_client.py` — async `chat(app_id, api_key, omi_base, text, *, timeout_seconds=30.0, context=None) -> str`. POSTs to `/v2/integrations/{app_id}/user/persona-chat` with Bearer auth. Reads SSE via `httpx_sse.EventSource`, joins chunks. Returns `""` on timeout/connect error (logs ERROR), raises `httpx.HTTPStatusError` on 4xx/5xx.
- [x] `plugins/_shared/test/test_persona_client.py` — 11 unit tests, all green (success: concat/auth/URL/JSON body; SSE: comments+empty stream; errors: 401/403/500 raise, timeout/connect return ""+log).
- [x] `plugins/_shared/README.md` — usage example, conventions.
- **Done**: `4b4b35b0a`
- **Notes**: `httpx_sse` 0.4.x uses `EventSource(response).aiter_sse()` (not module-level `aiter_sse`). Test fixtures attach a real `httpx.Request` to the mocked `Response` so `raise_for_status()` works. Empty `data:` frames yield empty string chunks which `_join_chunks` filters via `_split_lines` (only nonzero content survives). Plugins import this via `sys.path` insertion in `main.py` rather than a packaged module — matches the omi-slack-app pattern (no setup.py / packaging in the plugins tree).

---

### T-003 · `plugins/omi-telegram-app/` — skeleton + setup

---

### T-003 · `plugins/omi-telegram-app/` — skeleton + setup

- [x] Scaffold `plugins/omi-telegram-app/` per spec (main.py + telegram_client.py + simple_storage.py + persona_client.py + requirements.txt + Dockerfile + Procfile + runtime.txt + README.md + .gitignore).
- [x] `/health`, `/setup`, `/webhook` routes implemented. Auto-reply stubbed (T-004 territory).
- [x] Setup flow: bot_token + omi_uid + persona_id + omi_dev_api_key + public_base_url → setWebhook (with secret_token) → getMe → returns deep_link + bot_username + setup_token. /webhook handles `/start <setup_token>` handshake (binds chat_id to user, sends "Connected!"), nudges known chats with auto_reply disabled, silently 200s on unknown chats.
- [x] 15 unit tests, all green (health 1, setup 5, webhook 6, simple_storage 3).
- **Done**: `386dc38ce`
- **Notes**: Shared WEBHOOK_SECRET (env override: `TELEGRAM_WEBHOOK_SECRET`, else random at startup). One-shot setup tokens (popped on use). `users_data.json` and `pending_setups.json` added to `.gitignore` — they hold user tokens, must never be committed. Test fixture uses `_post_webhook(secret="default"|"none"|str)` to disambiguate "use the real secret" vs "send no header" vs "use this custom value" — caught a real bug where `secret=False` was being passed as a header value.

---

### T-004 · Telegram auto-reply (the heart of the plugin)

---

### T-004 · Telegram auto-reply (the heart of the plugin)

- [x] `_dispatch_auto_reply(user, chat_id, text)` calls `_persona_chat(...)` and `telegram_client.send_message(...)`. Empty reply + HTTP error + unexpected exception all logged, no crash.
- [x] Safety filters: groups / supergroups / channels skipped; bot senders skipped; non-text payloads skipped.
- [x] `POST /toggle {chat_id, enabled}` flips `auto_reply_enabled`; 404 on unknown chat.
- [x] 12 new unit tests, all green. Total plugin tests: 27.
- **Done**: `e44bd0fe9`
- **Notes**: `auto_reply` field already existed in `simple_storage.users` from T-003 — no schema change needed. `ignored_chat_ids` not implemented (per-chat ignore list); spec says "single global on/off per platform for v1". Catch-all `except Exception` on the dispatch path — webhook MUST always 200 to Telegram or it gets retried indefinitely. `_persona_chat` is aliased (underscore prefix) to avoid shadowing the `chat` name in test fixtures.

---

### T-005 · `plugins/omi-whatsapp-app/` — Meta Cloud API

---

### T-005 · `plugins/omi-whatsapp-app/` — Meta Cloud API

**Scope:**
- `plugins/omi-whatsapp-app/` scaffolded (same shape as Telegram).
- `whatsapp_client.py` — `httpx.AsyncClient` against `graph.facebook.com/v18.0/<phone_number_id>/messages`. `send_message(to, text)` posts to `/messages` with `{messaging_product: "whatsapp", to, text: {body: text}}`.
- Webhook verification: GET `hub.mode`, `hub.verify_token`, `hub.challenge` → echo challenge. POST: parse `entry[].changes[].value.messages[]`.
- Setup flow: user pastes `phone_number_id` + `access_token` + `verify_token` → app calls `set_webhook` (Meta side).
- Auto-reply: identical dispatch to T-004, different client.

**Acceptance:** real Meta test number → real message → Omi reply. (Dev path: use Meta's free test number; documented in README.)

**Risk:** Meta rate limits (80 msgs/sec/user). Not a v1 concern; document in README.

---

### T-006 · `plugins/omi-imessage-app/` — local-only bridge

**Scope:**
- `plugins/omi-imessage-app/` scaffolded (FastAPI for `/health`, `/toggle`; background task for polling).
- `imessage_db.py` — sqlite3 read of `~/Library/Messages/chat.db`. Query: `SELECT m.ROWID, m.text, m.is_from_me, m.handle_id, datetime(m.date/1000000000 + 978307200, 'unixepoch') AS ts FROM message m WHERE m.ROWID > ? AND m.text IS NOT NULL ORDER BY m.ROWID ASC`. Join `handle` for phone number.
- `imessage_client.py` — `subprocess.run(["osascript", "-e", f'tell application "Messages" to send "{text}" to buddy "{handle_id}"'])`.
- Background poller: 2s cadence, persists `last_seen_rowid` to storage. Skip `is_from_me=1`, skip groups (`chat.chat_identifier` not `chat_id+`).
- FDA check on startup: `os.access(chat_db_path, os.R_OK)`; if false, raise with a one-line message: "Grant Full Disk Access to Omi in System Settings → Privacy & Security → Full Disk Access, then restart."
- `launchd` plist template at `plugins/omi-imessage-app/launchd/com.omi.imessage-bridge.plist.example` for always-on.
- Unit tests: chat.db query parsing (using a fixture sqlite DB), osascript mock, FDA error path.

**Acceptance:** from another Apple ID on a different Mac, send an iMessage → Omi reply appears within ~3s. Confirmed on named bundle `omi-clone-test` with FDA granted.

**Risk:** Apple's sandboxing on macOS Sequoia may break osascript Messages send. If so, fall back to `py-imessage` or document the limitation.

---

### T-007 · Desktop UI: Clone screen (Flutter)

**Scope:**
- `app/lib/ui/screens/clone_screen.dart` — new screen. AppBar "AI Clone". Three `ClonePlatformCard` widgets (Telegram, WhatsApp, iMessage). Each shows: connection status icon, last reply timestamp, on/off switch, "Test reply" button, "Disconnect/Connect" CTA.
- `app/lib/app/routes.dart` (or whatever the routing file is — verify during implement) — add `/clone` route.
- `app/lib/ui/menus/` — sidebar entry "AI Clone" next to "Apps".
- Per-card backend: each card calls a new `lib/backend/clone_bridge.dart` that POSTs to the appropriate plugin's `/toggle` and `/health` endpoints. Discovery: each plugin's `/.well-known/omi-tools.json` exposes its base URL (or use a config file at `~/Library/Application Support/Omi/clone-plugins.json`).
- L10n: add `app_en.arb` keys for all strings (use the `add-a-new-localization-key-l10n-arb` skill).
- Verify with `agent-flutter snapshot -i` after hot restart.

**Acceptance:** navigating to the Clone screen shows 3 cards with status (Connected/Not configured). Toggle changes state and persists. Test reply returns non-empty reply.

**Risk:** l10n completeness — run `omi-add-missing-language-keys-l10n` and `flutter gen-l10n` after ARB edits.

---

### T-008 · Chat Tools manifest integration

**Scope:**
- Each plugin serves `GET /.well-known/omi-tools.json` per spec.
- Register each plugin in the existing `mcp/` server list so the Omi desktop chat surface discovers it (verify exact mechanism in `/implement` — search `mcp/` for similar registrations).
- Wire `toggle_auto_reply` from chat surface → plugin's `/toggle` endpoint.
- Wire `test_reply` from chat surface → synthetic inbound message → return persona reply inline.

**Acceptance:** in the Omi desktop chat, type "/clone telegram toggle" (or use the Chat Tools UI) → Telegram plugin's auto-reply toggles. Type "/clone telegram test hi" → reply displayed inline.

**Risk:** MCP tool discovery is the unknown — verify during implement; may need a new registration helper.

---

## Total: 8 tasks · ~3-5 days of focused work

Parallelization note: T-003, T-005, T-006 are independent plugin implementations after T-002 lands. If a subagent is available (via `subagent` tool), they can run in parallel. For solo work, sequential is fine — T-003 exercises the full pipeline first and is the most valuable regression target.

## Per-task review gate

Each task ends with:
1. Unit tests green for the new code.
2. Commit on `feat/ai-clone` (one commit per task, per AGENTS.md).
3. State file updated with `last_action`, `notes`, `next_action` = next T-id or "Run /test" if all tasks done.

## Test phase trigger

Once T-001..T-008 are committed, run `/test`. The test phase will:
- Run `backend/test.sh` (covers T-001, T-002).
- Run `app/test.sh` (covers T-007).
- Manual named-bundle smoke test of each plugin (T-003/004/005/006/008).

_Updated: 2026-06-27T16:00:00Z_