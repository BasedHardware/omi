Track 2: AI clone
I want omi Omi to respond to people on my behalf using my apps like telegram/whatsapp/imessage

How I’ll judge:
omi answers personal questions very well
Connects to my chatting apps easily
Has good and simple interface in omi desktop app


# Hybrid Implementation: Concrete Spec

## Architecture Overview

### Component 1: `plugins/omi-telegram-app/` (new)

Model directly after `plugins/omi-slack-app/` — same FastAPI structure, same file layout.

**Files to create:**

- `main.py` — FastAPI app with `/webhook` (receives Telegram updates), `/setup` (user links their Omi UID + enables auto-reply), `/health`
- `telegram_client.py` — wraps `python-telegram-bot` or `httpx` calls to Telegram Bot API
- `omi_persona_client.py` — calls `POST /v2/messages?app_id={persona_id}` with the user's Developer API key
- `simple_storage.py` — maps `telegram_chat_id` → `{omi_uid, persona_id, omi_dev_api_key, auto_reply_enabled}`
- `requirements.txt` — `fastapi`, `uvicorn`, `python-telegram-bot`, `httpx`, `python-dotenv`

**Key flow in `main.py`:**

```python
@app.post("/webhook")  
async def telegram_webhook(update: dict):  
    chat_id = update["message"]["chat"]["id"]  
    text = update["message"]["text"]  
    user = storage.get_user_by_chat_id(chat_id)  
    if not user or not user["auto_reply_enabled"]:  
        return {"ok": True}  
    # Call Omi persona chat  
    response = await omi_client.chat(user["omi_dev_api_key"], user["persona_id"], text)  
    await telegram_client.send_message(chat_id, response)
```

**Auth:** Use the existing Developer API key system (`omi_dev_...` keys). The user generates a key from Settings → Developer → Create Key in the Omi app. The bot stores it and uses it to call `/v2/messages`. `dependencies.py:55-68`

**Important:** `/v2/messages` currently uses `auth.get_current_user_uid` (Firebase JWT). You need to either:

- Add a new endpoint `POST /v2/integrations/{app_id}/user/persona-chat` that accepts app API keys (matching the pattern in `backend/routers/integration.py`), or
- Use the existing `get_api_key_auth` dependency to add API key support to `/v2/messages` (`integration.py:73-91`)

---

### Component 2: `plugins/omi-whatsapp-app/` (new)

Identical structure to the Telegram plugin. Differences:

- Use Twilio WhatsApp sandbox for development (no approval needed), or WhatsApp Business Cloud API for production
- Webhook receives `POST` from Twilio/Meta with `From`, `Body` fields
- `whatsapp_client.py` wraps Twilio's `Client.messages.create()` or Meta's Graph API
- `requirements.txt` additions: `twilio` (or `httpx` for Meta Graph API directly)

---

### Component 3: `plugins/omi-imessage-app/` (new, TypeScript)

Uses Spectrum self-hosted mode (no Spectrum Cloud dependency):

```typescript
// index.ts  
import { Spectrum } from "spectrum-ts";  
import { imessage } from "spectrum-ts/providers/imessage";  
  
const app = await Spectrum({  
  // self-hosted: no projectId/projectSecret needed  
  providers: [imessage.config({ dbPath: process.env.IMESSAGE_DB_PATH })],  
});  
  
for await (const [space, message] of app.messages) {  
  await space.responding(async () => {  
    const reply = await callOmiPersona(  
      process.env.OMI_DEV_API_KEY,  
      process.env.OMI_PERSONA_ID,  
      message.text  
    );  
    await message.reply(reply);  
  });  
}
```

**`package.json` deps:** `spectrum-ts`, `@spectrum-ts/imessage`, `node-fetch`

**Constraint:** Must run on the same macOS machine where iMessage is active. Deploy as a launchd service or run from the Omi desktop app process.

---

### Component 4: Backend — new persona chat endpoint with API key auth

Add to `backend/routers/integration.py` (or a new `backend/routers/persona_integration.py`):

```python
@router.post('/v2/integrations/{app_id}/user/persona-chat')  
async def persona_chat_via_integration(  
    app_id: str,  
    uid: str,  
    data: SendMessageRequest,  
    authorization: Optional[str] = Header(None),  
):  
    api_key = authorization.replace('Bearer ', '')  
    if not verify_api_key(app_id, api_key):  
        raise HTTPException(status_code=403, detail="Invalid API key")  
    # ... route to execute_persona_chat_stream()
```

This mirrors the existing integration endpoints pattern exactly. (`integration.py:155-204`)

---

### Component 5: Desktop UI — enable/disable auto-reply toggle

Each plugin exposes a `/.well-known/omi-tools.json` with a `toggle_auto_reply` tool. This lets users turn auto-reply on/off directly from the Omi desktop/mobile chat interface without going to a separate settings page. (`ChatTools.mdx:302-330`)

---

### Component 6: Persona setup flow

The user's persona is created via `POST /v1/user/persona` (already exists). The bot plugins need to store the returned `persona_id` per user. (`apps.py:665-719`)

The persona prompt is built from memories + recent conversations + tweets via `generate_persona_prompt()`: (`apps.py:715-769`)

---

## Summary: What to build vs. what already exists

| Item | Status | Location |
|------|--------|----------|
| Persona engine (prompt + LLM) | Exists | `backend/utils/apps.py`, `backend/utils/llm/persona.py` |
| Persona CRUD API | Exists | `backend/routers/apps.py /v1/user/persona` |
| Plugin pattern (FastAPI + webhook) | Exists | `plugins/omi-slack-app/` |
| App API key auth for integrations | Exists | `backend/routers/integration.py` |
| Developer API key auth | Exists | `backend/dependencies.py get_api_key_auth` |
| Telegram plugin | **Build** | `plugins/omi-telegram-app/` |
| WhatsApp plugin | **Build** | `plugins/omi-whatsapp-app/` |
| iMessage bridge (Spectrum self-hosted) | **Build** | `plugins/omi-imessage-app/` |
| Persona chat endpoint with API key auth | **Build** | `backend/routers/integration.py` new route |
| Desktop toggle UI (Chat Tools manifest) | **Build** | per-plugin `/.well-known/omi-tools.json` |


## REFERENCE
1. /Users/choguun/Documents/workspaces/cool-projects/spectrum-ts/packages