# AI Clone — Spec

> Track 2 of PLAN.md. Omi responds to people on the user's behalf via Telegram, WhatsApp, iMessage (and reuses the existing Slack plugin pattern). Sources: `PLAN.md` and the `spectrum-ts` reference at `/Users/choguun/Documents/workspaces/cool-projects/spectrum-ts/packages/`.

## Problem & judgment

**What:** When a message arrives in Telegram / WhatsApp / iMessage, Omi auto-replies using the user's persona — their voice, their memories, their context.

**How the user judges it:**

1. *Answers personal questions well.* The reply must reflect the user's actual life — memories, recent conversations, tone. The existing `generate_persona_prompt()` + `execute_persona_chat_stream()` already do this; we just need a clean wire to call them.
2. *Connects to chat apps easily.* Setup must be <2 minutes per platform: paste a bot token / scan a QR / grant Messages automation. No fiddly webhook tunneling for the user.
3. *Good and simple UI in the Omi desktop app.* A single screen lists all clones, each shows status (connected / paused / error), a master per-platform toggle, and a "Test reply" button.

## Architecture decision: unified `spectrum-ts` self-hosted

PLAN.md proposed three separate Python FastAPI plugins + one TypeScript iMessage bridge. The `spectrum-ts` reference makes that split unnecessary:

- `spectrum-ts` is a **unified TypeScript SDK** with provider packages for `telegram`, `slack`, `imessage`, `whatsapp-business` (`/Users/choguun/Documents/workspaces/cool-projects/spectrum-ts/packages/`).
- One factory: `Spectrum({ providers: [...] })` returns a typed instance with `spectrum.messages: AsyncIterable<[Space, Message]>` and `space.send(content)`.
- It supports **self-hosted mode** (`projectId`/`projectSecret` omitted) — required for iMessage (local DB), and just as good for Telegram/WhatsApp where we run our own webhook.
- Every provider shares `verify`, `config`, `messages`, `send`, `space` semantics — so the persona-dispatch handler is identical across providers.

**Recommendation:** build **one** TypeScript service, `plugins/omi-clone-bridge/`, that wraps `Spectrum({ providers: [...] })` and dispatches every inbound message to the user's Omi persona. Same `omi-persona-client.ts` regardless of platform.

**What this changes vs PLAN.md:**

| PLAN.md (split) | New (unified) | Why |
|---|---|---|
| `plugins/omi-telegram-app/` (Python) | merged into `plugins/omi-clone-bridge/` (TS, `@spectrum-ts/telegram`) | one runtime, one deploy |
| `plugins/omi-whatsapp-app/` (Python) | merged into `plugins/omi-clone-bridge/` (TS, `@spectrum-ts/whatsapp-business`) | Twilio/Meta HTTP differences vanish behind `send` |
| `plugins/omi-imessage-app/` (TS, raw spectrum-ts) | merged into `plugins/omi-clone-bridge/` (TS, `@spectrum-ts/imessage`) | identical message loop |
| `plugins/omi-slack-app/` (Python, existing) | unchanged | existing production plugin, not in scope |

**iMessage constraint** (preserved): must run on the user's Mac (reads `~/Library/Messages/chat.db`). Deploy as a `launchd` service that `run.sh` starts after the Omi desktop app launches.

**Backwards compat:** the existing Python `omi-slack-app` stays. The clone bridge does NOT replace it — Slack remains a first-class plugin with its own deployment, and the bridge learns to also dispatch Slack via `@spectrum-ts/slack` only if/when we deprecate the Python plugin (separate AIDLC cycle).

## Backend additions

### New endpoint: `POST /v2/integrations/{app_id}/user/persona-chat`

Location: `backend/routers/integration.py` (alongside the existing `create_conversation_via_integration` pattern at line 68).

```python
@router.post('/v2/integrations/{app_id}/user/persona-chat')
async def persona_chat_via_integration(
    request: Request,
    app_id: str,
    uid: str,
    body: PersonaChatRequest,                   # {text: str, context?: dict}
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    api_key = authorization.replace('Bearer ', '')
    if not await run_blocking(critical_executor, verify_api_key, app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid integration API key")
    # Rate limit (mirror existing 10/hour ceiling in this file)
    await run_blocking(critical_executor, check_rate_limit_inline, f"{app_id}:{uid}:persona", "integration:persona")
    # Verify app exists + user enabled it + app has persona-chat capability
    # ... (same shape as create_conversation_via_integration)
    # Stream LLM reply chunks via execute_persona_chat_stream(uid, text, ...)
    return StreamingResponse(persona_event_stream(uid, app_id, body.text), media_type="text/event-stream")
```

Auth: app API key (`omi_dev_...` style), same `verify_api_key(app_id, key)` dependency already used by 7+ endpoints in this file. No Firebase JWT required (the bridge holds the key on the user's machine).

### New app capability: `external_integration.persona_chat`

Add to `apps_utils` (mirroring `app_can_create_conversation`): gates the new endpoint so only apps that opt in can call it. The bridge's registered app declares this capability in its manifest.

### No persona engine changes

`execute_persona_chat_stream(uid, text)` in `backend/utils/retrieval/graph.py:112` and `generate_persona_prompt()` in `backend/utils/apps.py:715-769` are reused as-is. The endpoint is a thin streaming wrapper.

## Plugin: `plugins/omi-clone-bridge/` (new, TypeScript)

Layout — modeled on `plugins/omi-slack-app/` for ops shape (Dockerfile, requirements→deps, README) but in TypeScript:

```
plugins/omi-clone-bridge/
├── package.json                   # spectrum-ts, @spectrum-ts/{telegram,whatsapp-business,imessage,slack}, undici
├── tsconfig.json
├── Dockerfile                     # node:22-alpine, multi-stage
├── README.md
├── .env.example                   # TELEGRAM_BOT_TOKEN, WHATSAPP_TOKEN, IMESSAGE_DB_PATH, OMI_API_BASE, OMI_BRIDGE_APP_ID, OMI_BRIDGE_API_KEY
├── src/
│   ├── index.ts                   # boot: read user config, build Spectrum(), dispatch loop
│   ├── config.ts                  # per-user clone config loader (sqlite or json file)
│   ├── spectrum.ts                # Spectrum({ providers: [...] }) factory, no projectId/projectSecret (self-hosted)
│   ├── persona.ts                 # callOmiPersona(apiKey, personaId, text) → async iterable of chunks
│   ├── dispatch.ts                # for-await over spectrum.messages → space.send(reply)
│   ├── webhooks.ts                # Express + raw-body parsing; forwards HTTP webhooks to spectrum.webhook()
│   ├── safety.ts                  # per-chat idempotency + cooldown (e.g. 30s between auto-replies in same thread)
│   └── manifest.ts                # /.well-known/omi-tools.json exposing toggle_auto_reply
└── test/
    ├── unit/                      # dispatch, safety, config
    └── e2e/                       # record/replay fixture for each provider
```

### Message loop (the heart of the service)

```ts
// src/dispatch.ts
import type { SpectrumInstance } from "spectrum-ts";

export async function runDispatch(spectrum: SpectrumInstance) {
  for await (const [space, message] of spectrum.messages) {
    const cfg = config.forSpace(space);          // telegram_chat_id / wa_from / imessage_chat_id → user config
    if (!cfg?.autoReplyEnabled) continue;
    if (safety.shouldSkip(space, message)) continue;
    try {
      await space.responding(async () => {
        const reply = await persona.call(cfg, message.text);
        await message.reply(reply);
      });
      safety.markReplied(space);
    } catch (err) {
      logger.error({ err, space: space.id }, "auto-reply failed");
      // never throw out of the loop — one bad reply must not crash the bridge
    }
  }
}
```

The handler is **identical for every provider**. That's the entire point of picking spectrum-ts.

### iMessage deployment shape

The bridge is a single Node process. iMessage's `dbPath` config points at `~/Library/Messages/chat.db`. We also run a tiny Express server (`src/webhooks.ts`) that exposes:

- `POST /webhooks/telegram` → `spectrum.webhook(req, handler)`
- `POST /webhooks/whatsapp` → same (Twilio or Meta Graph)
- `GET  /.well-known/omi-tools.json` → tool manifest
- `GET  /health` → liveness for the desktop launcher

When run from `Omi Dev`/`Omi Beta` desktop, `run.sh` starts the bridge as a child process bound to a per-worktree port (`OMI_BRIDGE_PORT`, default 47800). Production-style: a `launchd` plist under `~/Library/LaunchAgents/com.omi.clone-bridge.plist` for the iMessage requirement (always-on).

## Storage: per-user clone config

Where: `~/Library/Application Support/Omi/clone-config.json` on the user's Mac (matches desktop app's UserDefaults pattern). Schema:

```json
{
  "users": {
    "<omi_uid>": {
      "persona_id": "persona_abc",
      "omi_dev_api_key": "omi_dev_...",
      "auto_reply": { "telegram": true, "whatsapp": false, "imessage": true },
      "cooldown_seconds": 30,
      "ignored_chat_ids": ["..."]
    }
  }
}
```

Single-user-at-a-time on a desktop install — no DB engine. If a user has multiple Omi accounts on the same Mac (rare), they get a multi-entry map.

## Desktop UI (Flutter, `app/`)

New screen: **AI Clone** (`lib/ui/screens/clone_screen.dart`, registered in `app_router.dart`).

Contents:
- Header: "AI Clone — let Omi respond on your behalf"
- Per-platform card (Telegram, WhatsApp, iMessage): connection status, last reply timestamp, on/off toggle, "Test reply" button that sends a synthetic inbound message through the bridge and shows the generated reply.
- A "Setup" CTA per disconnected platform: deep-links to platform-specific setup (bot token paste for Telegram, QR for WhatsApp, automation permission prompt for iMessage).
- Surfaced from the main sidebar/menu next to "Apps".

Setup flow per platform:

| Platform | User action | What the bridge does |
|---|---|---|
| Telegram | Paste bot token, click "Connect" | `telegram.config({ botToken })` + `ensureWebhook()` registers with Telegram; status flips to "Connected" |
| WhatsApp | (dev) Twilio sandbox `join <sandbox-keyword>`; (prod) Meta Embedded Signup flow | `whatsapp-business.config({ phoneNumberId, accessToken, verifyToken })` |
| iMessage | Click "Grant Messages access" → macOS automation prompt; bridge reads `chat.db` | `imessage.config({ dbPath })` |

## Chat Tools manifest (`/.well-known/omi-tools.json`)

Exposed by the bridge's Express server. Enables inline auto-reply toggles from the Omi desktop chat:

```json
{
  "name": "omi-clone",
  "tools": [
    {
      "name": "toggle_auto_reply",
      "description": "Turn AI auto-reply on or off for a platform",
      "params": { "platform": "telegram|whatsapp|imessage", "enabled": "boolean" }
    },
    {
      "name": "test_reply",
      "description": "Send a test inbound message and show the persona's reply",
      "params": { "platform": "telegram|whatsapp|imessage", "text": "string" }
    }
  ]
}
```

Wired in the desktop chat surface (where existing Chat Tools are surfaced — see `docs/doc/developer/backend/ChatTools.mdx:302-330`).

## Out of scope (explicit non-goals)

- Voice messages (Telegram/WhatsApp voice notes). We accept text only for v1.
- Group chat auto-reply. Per-chat `ignored_chat_ids` lets users silence groups; bridge never auto-replies in groups by default.
- Per-contact opt-in lists (e.g. "only reply to my mom"). Single global on/off per platform for v1.
- Replacing the existing Python `omi-slack-app`. It's not in this AIDLC cycle.
- Migration to Photon Cloud (`projectId`/`projectSecret`). We are self-hosted from day one.

## Acceptance criteria

1. **Unit tests** (`plugins/omi-clone-bridge/test/unit/`) cover `dispatch.ts`, `safety.ts`, and `persona.ts` with at least: persona success, persona timeout (falls back to no reply), cooldown skip, ignored chat skip, malformed webhook rejection.
2. **E2E fixtures** (`plugins/omi-clone-bridge/test/e2e/`): one fixture per provider that replays a recorded webhook payload through `spectrum.webhook()` and asserts the persona client received the right text.
3. **Manual end-to-end** (per Desktop AGENTS.md self-test rule): a named bundle `omi-clone-test` connects a real Telegram bot to a real Omi persona and the user sees the reply in Telegram. Screenshot evidence to `/tmp/evidence.png` via `agent-swift`.
4. **Backend contract**: `curl -X POST /v2/integrations/{app_id}/user/persona-chat -H "Authorization: Bearer $KEY" -d '{"text":"hi"}'` returns a streaming response within 500ms (time-to-first-token), end-to-end latency <3s on a warm persona.
5. **Desktop UI** verified with `agent-flutter snapshot -i`; "Test reply" returns a non-empty response from the persona for all three providers.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `spectrum-ts` npm packages are not yet published (we'd be vendoring or pinning to a tag). | Pin to a git tag in `package.json` (`"spectrum-ts": "github:photon-codes/spectrum-ts#v0.x"`). Fall back to vendored copy in `plugins/omi-clone-bridge/vendor/spectrum-ts/` if install fails. |
| iMessage `chat.db` access requires Full Disk Access — extra macOS permission. | Surface a clear "Grant Full Disk Access" CTA on the iMessage card; abort bridge startup with a one-line actionable error if not granted. |
| Persona replies go to wrong chat (cross-talk bug). | `space.id` is per-(platform, conversation) — the bridge never mixes them. Unit test pins this. |
| Auto-reply loop (Omi replies to its own messages). | Bridge only replies to messages where `message.sender.id !== cfg.omi_uid` (per-provider sender resolution). |
| Persona emits something embarrassing in a group chat. | Default-on rule: never auto-reply in groups. Documented in `safety.ts`. |

## Open questions for the user

1. **Confirm unified TS architecture** instead of PLAN.md's split (Python Telegram/WhatsApp + TS iMessage). Strongly recommended; one codebase, one deploy.
2. **Self-hosted from day one** — OK to skip Photon Cloud for now and add later as a second mode?
3. **Desktop screen placement** — sidebar entry, or under Settings → Apps?
4. **Existing Slack plugin** — leave alone (recommended), or also port to spectrum-ts as part of this cycle?

_Updated: 2026-06-27T15:35:00Z_