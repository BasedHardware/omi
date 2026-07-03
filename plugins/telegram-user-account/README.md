# OMI Telegram AI-Clone — user-account plugin

A second AI-Clone mode for Telegram, distinct from the bot
plugin in `plugins/omi-telegram-app/`. Where the bot plugin
authenticates as a separate Bot account, the **user-account
plugin authenticates as the user's PERSONAL Telegram
account** (via Telethon's StringSession). AI replies then
appear to come from the user, not from a bot.

> ⚠️ **Telegram ToS risk.** A "userbot" — automation acting as
> a personal account — is in a gray area under Telegram's
> Terms of Service. Telegram's anti-flood systems target
> automated behavior, and accounts that exceed their
> thresholds can be rate-limited, shadow-banned, or fully
> banned. This plugin ships with explicit ToS acknowledgement
> gating in the desktop's connect sheet, a 30 sends/hour
> rate-limit cap, FLOOD_WAIT detection, and a daily sent
> counter. The user opts in explicitly.

The two plugins run **side-by-side**; the desktop's
"Reply as me" toggle in the connect sheet decides which
mode is active. The bot plugin remains the default for
new users (lower ToS risk, easier recovery).

## How it differs from the bot plugin

| | Bot plugin | User-account plugin |
|---|---|---|
| **Authenticates as** | Bot account (via BotFather) | User's personal account (via Telethon session) |
| **Setup** | `@BotFather` + bot token | api_id/api_hash/phone/code (Telethon interactive sign-in) |
| **Replies appear from** | The bot | The user |
| **ToS risk** | Low (the approved path) | High (gray zone) |
| **Rate-limit cap** | None (Telegram's own anti-flood) | 30 sends/hour (plan §8) + FLOOD_WAIT detection |
| **On FLOOD_WAIT** | Returns 502 | Returns 429 with Retry-After + registers local cooldown |
| **Discovery file** | `~/.config/omi/ai-clone-plugin.json` | `~/.config/omi/ai-clone-telegram-user.json` |
| **Storage** | `users_data.json` keyed by chat_id | `users_data.json` keyed by Telegram user id |
| **Per-user identifier** | Telegram chat_id | Telegram user id (str) |

## Setup

The setup flow is interactive and must be run from a
terminal-attached session (so the subprocess can prompt
for input). The desktop's connect sheet handles this
automatically when you click **"Generate session"**.

### Manual setup

1. Get Telegram API credentials at https://my.telegram.org/apps
   (the api_id and api_hash are public; many open-source
   Telegram tools publish theirs).
2. Run the desktop via `./run.sh` from a Terminal window
   (NOT from Finder — see the "Terminal requirement" note below).
3. From the Omi desktop, click **AI Clone → Telegram →
   Reply as me → Connect**. Tick the ToS acknowledgement
   checkbox. Click **Generate session**. The desktop launches
   `session_string_generator.py` as a subprocess.
4. Follow the prompts in the terminal: api_id, api_hash,
   phone (international format), verification code Telegram
   sends you, optional 2FA password.
5. On success, the subprocess prints the Telethon StringSession
   to stdout. The desktop captures it, writes it to the
   macOS Keychain, and sets `telegramAccountEnabled = true`.
6. On next launch, the desktop auto-discovers the
   user-account plugin via `~/.config/omi/ai-clone-telegram-user.json`
   and applies the account metadata.

### Terminal requirement

The subprocess uses `isatty(0)` to detect whether the desktop
was launched from a terminal. If it wasn't (e.g. launched
from Finder with no controlling terminal), the desktop
shows a clear error: "Reply as me requires a
terminal-attached session. Open Terminal.app and run the
desktop from there (e.g. via `./run.sh`)." The subprocess
is not spawned.

To use "Reply as me" in dev: `cd desktop/macos && ./run.sh`.
In production: documented in the connect sheet's error UI.

## Endpoints

All endpoints are bearer-gated via `AI_CLONE_PLUGIN_TOKEN`
(same convention as the bot plugin). Bearer failures return
the same 401 with no enumeration signal.

- `GET /health` — liveness, no auth.
- `GET /status` — connection state + auto-reply aggregate +
  rate-limit + daily-sent counter. Used by the desktop's
  30s poll.
- `GET /recent_messages?limit=N` — list recent chats.
- `GET /recent_messages/{chat_id}/messages` — recent
  messages in a chat (the desktop uses this to surface
  conversation context).
- `POST /persona_chat` — call the persona API for a chat,
  send the reply via Telethon. Bearer-gated. Returns 403
  if the user's `auto_reply_enabled` flag is False.
- `POST /toggle` — flip auto-reply for one user (or all).
  Bearer-gated.
- `POST /chat_memory` — append a message to a chat's
  ring buffer (used by the desktop for context).

### `POST /persona_chat` — request/response

Request body (JSON):
```json
{
  "chat_id": "999001",
  "text": "hi there",
  "sender_handle": "choguun_handle",
  "context": {
    "sender_name": "Alice",
    "sender_username": "alice",
    "chat_type": "private",
    "platform": "telegram"
  },
  "previous_messages": [
    {"role": "human", "text": "earlier turn"},
    {"role": "ai", "text": "earlier reply"}
  ]
}
```

Responses:
- `200` — `{chat_id, reply, sent}`
- `400` — no Omi account linked to this Telegram handle
  (caller must run "Reply as me" setup first)
- `401` — missing or wrong bearer
- `429` — rate-limit cap hit OR Telegram returned
  `FLOOD_WAIT_*`. Body: `{detail: "Rate limit hit. Wait Xs..."}`
  or `Telegram FLOOD_WAIT: wait Xs...`. Headers: `Retry-After: X`
- `502` — Telethon `send_message` failed (non-FLOOD_WAIT)

The 429 + Retry-After is the plan §8 "ban-warning panel"
mechanism: the desktop surfaces "Telegram asked us to wait
Xs" and backs off automatically.

### `POST /toggle` — request/response

Request body (JSON):

```json
{
  "handle": "all",
  "enabled": true
}
```

- `handle` — `"all"` toggles every user in storage (the
  typical case; the user-account flow is single-account so
  `"all"` is the single-user semantic). Per-handle toggles
  are reserved for future multi-account support.
- `enabled` — bool, the target state.

Responses:
- `200 OK` — `{auto_reply_enabled: bool, affected_users: int}`.
  `affected_users` is the count of user records updated.
- `403` — the target handle is unknown OR the `"all"` call
  has no users. Same 403 for both so a probe cannot
  distinguish "user exists with auto-reply off" from "user
  doesn't exist". The plugin bearer token already gates
  this endpoint; the per-handle check is defense-in-depth.

The endpoint writes through `simple_storage.update_auto_reply(handle, enabled)`
and the `/status` response picks up the change on the next
30s poll. The desktop's "Auto-reply" switch in
`ConnectSheet.userAccountSection` calls this endpoint and
rolls back the binding on error.

## Rate limit + flood control (plan §8)

The user-account flow is a userbot. Telegram's anti-flood
systems target automated behavior. To stay under the
threshold:

1. **Rolling 60-min cap of 30 sends** (configurable via
   `TELEGRAM_USER_RATE_PER_HOUR` env var, default 30).
   `flood_control.default_rate_limit.can_send()` returns
   False when the cap is hit.
2. **FLOOD_WAIT detection.** When Telethon raises
   `FloodWaitError`, the endpoint returns 429 with
   `Retry-After` set to Telegram's `seconds` value AND
   registers a local cooldown via
   `flood_control.default_rate_limit.block_for_seconds(N)`.
   The next request from the same desktop is rejected at
   `can_send()` before reaching the persona API (saves LLM
   tokens when the cap is hit).
3. **Daily sent counter** (`messages_sent_today` in
   /status). Exact, monotonic since local-time midnight,
   reset on rollover. Surfaced in the connect sheet as
   "X / 30 sent this hour" with a warning at >=80% of cap.

The rate-limit state is exposed via `/status` and polled
by the desktop every 30s. The `isNearCap` flag drives a
yellow warning badge; `isBlocked` (FLOOD_WAIT active)
drives a red banner.

## Security model

This plugin holds a fully-compromising identity secret:
the Telethon StringSession. Anyone with the string can
read all of the user's Telegram chats and send messages
as the user. The session string is the user's Telegram
identity.

Security guarantees:

- **Read from stdin ONCE at startup.** The
  `read_session_from_stdin()` function reads the session
  from the parent's stdin pipe, passes it to
  `StringSession`, then overwrites the local binding
  with `None`. The session does not persist in any Python
  variable across the plugin's lifetime.
- **Stored in macOS Keychain on the desktop.** Held in
  `AICloneKeychain.Key.telegramUserSession` (encrypted at
  rest, locked-screen gated). NEVER in UserDefaults.
  NEVER in the discovery file. NEVER in any HTTP
  response. NEVER logged.
- **Subprocess stdin pass-through.** The
  `session_string_generator.py` subprocess writes the
  session to stdout. The desktop captures it, writes it
  to Keychain via `setTelegramUserSession()`, then clears
  the in-memory copy. The subprocess itself is short-lived.
- **No on-disk session storage.** The plugin doesn't
  persist the session; it lives in Keychain on the
  desktop and is piped to the plugin over stdin on each
  launch. The plugin process holds the session only in
  Telethon's `StringSession` (in-memory).
- **Logging redaction.** The custom `RedactingFormatter`
  installed at module import time redacts any line that
  looks like a session string before it reaches
  `logger.*` output. Tested in `test_session_never_logged.py`.

A `Redact` module provides the regex-based redaction used
by both `redact.py` (formatter + helpers) and
`session_string_generator.py` (source-level invariants).

## Architecture

- `main.py` — FastAPI service. Routes `/health`, `/status`,
  `/recent_messages`, `/recent_messages/{chat_id}/messages`,
  `/persona_chat`, `/chat_memory`. Lifespan reads the
  Telethon session from stdin, builds a `TelethonClient`,
  connects, populates `simple_storage.account` from
  `get_me()`.
- `telethon_client.py` — `TelethonClient` wrapper. Constructor
  reads the session from stdin ONCE, overwrites the local
  binding with None, then uses Telethon's `StringSession`
  (no FileSession). Methods: `connect`, `disconnect`,
  `is_connected`, `get_chats`, `get_chat_history`,
  `send_message`. The `connect()` method checks `get_me()`
  for None and raises `RuntimeError("not authorized")` for
  revoked sessions.
- `simple_storage.py` — JSON-file persistence. Per-user
  config keyed by Telegram user id (NOT chat id — there's
  no bot_token concept). Per-chat ring buffer (capped at
  `CHAT_HISTORY_MAX = 10` entries per chat, document this
  bound on any "messages sent today" indicator that reads
  from the buffer). Account metadata from `get_me()`.
- `flood_control.py` — `RateLimit` class (rolling window
  + external cooldown) and `detect_flood_wait` helper.
  See "Rate limit + flood control" above.
- `redact.py` — `redact_session_string` helper + auto-
  installed `RedactingFormatter` that scrubs logs.
- `session_string_generator.py` — one-shot interactive
  Telethon sign-in helper. Prints the StringSession to
  stdout. The desktop captures the LAST line of stdout
  and writes it to Keychain.

## Tests

The async tests in this plugin require `pytest-asyncio`.
Install both production and dev deps first:

```bash
cd plugins/telegram-user-account
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest==8.3.3 pytest-asyncio==0.24.0
```

Run the test suite:

```bash
OMI_DEV_MODE=1 .venv/bin/python -m pytest test/ -v
```

The conftest.py at `test/conftest.py` installs an autouse
isolation fixture that clears the in-memory state between
tests. The fixture also patches `sys.modules` so the test
files can `import redact`, `import simple_storage`, etc.
without polluting the production module.

Test files:
- `test_redact.py` — session string redaction.
- `test_session_never_logged.py` — session string never
  appears in logs/HTTP/exception output.
- `test_discovery_schema.py` — discovery file schema.
- `test_state_isolation.py` — autouse isolation fixture
  correctness.
- `test_storage.py` — per-user config, ring buffer,
  account metadata, session-string-never-in-storage.
- `test_telethon_client.py` — Telethon wrapper.
- `test_flood_control.py` — rate limit, FLOOD_WAIT,
  block_for_seconds, daily counter.
- `test_session_string_generator.py` — generator source-
  level invariants (no file writes, stdout-clean errors).
- `test_main.py` — FastAPI service: bearer auth, route
  schemas, rate limit + FLOOD_WAIT integration.

## Stack runner integration

`desktop/macos/scripts/ai-clone-stack.sh` supports
`TELEGRAM_USER_ACCOUNT=1` to launch the user-account plugin
alongside the bot plugin. The script reads the session
from `$TELEGRAM_USER_SESSION_FILE` (default
`/tmp/omi-e2e/telegram-user.session`) and pipes it into
the plugin's stdin.

> ⚠️ **The session file is for E2E testing ONLY.** This
> path is a deliberate trade-off for hermetic test
> harnesses: a CI runner has no interactive way to run
> `session_string_generator.py`, so the stack runner
> accepts a pre-generated session string from disk so the
> test path can exercise the full plugin flow end-to-end.
>
> **Do NOT use a real session string here in any
> non-hermetic environment.** A real session string on
> disk under `/tmp` is a fully-compromising identity
> secret and contradicts the "no on-disk session storage"
> threat model documented in the Security Model section
> above. The E2E session file is expected to be a
> throwaway session generated for the test run only.
>
> If you need a real session for local dev, run the
> `session_string_generator.py` flow instead: the
> generated session is captured by the desktop's
> ConnectSheet and stored in the macOS Keychain, never on
> disk.

```bash
# E2E / hermetic test run only -- synthetic session.
TELEGRAM_USER_ACCOUNT=1 \
TELEGRAM_USER_SESSION_FILE=/path/to/e2e-session \
  bash desktop/macos/scripts/ai-clone-stack.sh

# Real session: do NOT use the stack runner path. Instead,
# use the desktop's ConnectSheet -> Reply as me -> Generate
# session flow, which writes the session to Keychain.
```

## Maintenance notes

- **Telethon API drift:** Telethon's `get_me()` signature
  is stable, but if you upgrade `telethon>=2.0`, check the
  `StringSession.save()` round-trip. The test
  `test_telethon_client.py` covers the wrapper contract.
- **Telegram ToS changes:** Telegram's stance on userbots
  can change. If Telegram tightens the rules, this plugin
  may need a more aggressive backoff (lower cap, longer
  cooldowns). Watch the FLOOD_WAIT seconds; a creeping
  upward trend in the daily log signals increased pressure.
- **FLOOD_WAIT_X changes:** if Telegram adds new
  FLOOD_WAIT_* variants, extend `detect_flood_wait` in
  `flood_control.py`. The current implementation matches
  by class name + `seconds` attribute.
