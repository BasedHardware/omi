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

**Scope:**
- `backend/models/integrations.py` — add `PersonaChatRequest { text: str }` Pydantic model.
- `backend/utils/apps.py` — add `app_can_persona_chat(app)` capability check (mirrors `app_can_create_conversation`).
- `backend/routers/integration.py` — add `POST /v2/integrations/{app_id}/user/persona-chat` route, auth via `verify_api_key`, rate-limit via `check_rate_limit_inline`, return `StreamingResponse` over `execute_persona_chat_stream`.
- `backend/test/` — integration test: seed an app with the new capability, mint a valid `omi_dev_...` key, POST a sample message, assert SSE stream returns non-empty first chunk.

**Acceptance:** `curl -X POST .../persona-chat -d '{"text":"hi"}'` returns 200 + `text/event-stream` body. First token <500ms locally.

**Risk:** hot path is `execute_persona_chat_stream` — confirm it doesn't block on sync IO (uses `run_blocking` for LLM, `db_executor` for memory retrieval). Read `graph.py:112-200` carefully.

---

### T-002 · Shared `persona_client.py` module

**Scope:**
- `plugins/_shared/persona_client.py` — single async function `chat(app_id: str, api_key: str, omi_base: str, text: str) -> str`. Uses `httpx.AsyncClient` to POST, reads the SSE stream, concatenates chunks, returns full reply. Timeout 30s.
- `plugins/_shared/persona_client_test.py` — unit test with a mocked `httpx` transport: success path, timeout path (returns "" + logs error), 401/403 path (raises).
- `plugins/_shared/README.md` — one paragraph describing the contract.

**Acceptance:** `pytest plugins/_shared/` green. Three plugins will import this verbatim in T-003/T-005/T-006.

**Risk:** SSE parsing edge cases (multi-line `data:` frames, comments). Use `httpx-sse` or hand-roll a minimal parser. Decide in implementation.

---

### T-003 · `plugins/omi-telegram-app/` — skeleton + setup

**Scope:**
- `plugins/omi-telegram-app/` scaffolded per spec (main.py, telegram_client.py, simple_storage.py, persona_client.py → imports from `_shared`, requirements.txt, Dockerfile, Procfile, README.md, runtime.txt).
- `/health`, `/setup`, `/webhook` routes stubbed. No auto-reply yet.
- Setup flow: user pastes bot token → bot calls `set_webhook(url)` → user pastes deep-link `setup_token` → bot stores `chat_id → omi_uid` mapping. Asks user for `omi_dev_...` key + persona_id (also through `/setup`).
- Unit tests: webhook secret verification, setup token validation, storage round-trip.

**Acceptance:** with a real test bot token, `/health` returns 200; `/setup?token=...` registers a user; `/webhook` echoes back a debug reply ("auto-reply not enabled").

**Risk:** Telegram webhook secret handling. Use `X-Telegram-Bot-Api-Secret-Token` header check.

---

### T-004 · Telegram auto-reply (the heart of the plugin)

**Scope:**
- `main.py` `/webhook` handler: extract `chat_id`, `from.id`, `text` → look up user → skip if own message or group or `auto_reply_enabled=False` → call `persona_client.chat` → `telegram_client.send_message` → return `{ok: True}`.
- Safety: skip `is_from_me`, skip `chat.type in {"group", "supergroup"}`, skip if no user mapping.
- `simple_storage.py` extended with `auto_reply_enabled: bool` and `ignored_chat_ids: list[str]`.
- `/toggle` endpoint: flips `auto_reply_enabled` for the stored user. Called by Chat Tools (T-008).
- Unit tests: full dispatch path with mocked persona + telegram clients. Skip cases covered.

**Acceptance:** send a real message to a real bot → Omi persona reply appears in Telegram within ~3s. Confirmed via screenshot in named bundle `omi-clone-test`.

**Risk:** the persona reply might be empty (LLM refusal). Log + send a fallback "—" so the chat doesn't go silent.

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