# Omi Plugin SDK

Shared Python primitives for Omi plugins.

Install locally from the repository checkout:

```bash
pip install -e plugins/omi-plugin-sdk
```

Canonical imports:

```python
from omi_plugin_sdk.models import (
    ActionItem,
    Conversation,
    ConversationPhoto,
    EndpointResponse,
    Event,
    Structured,
    TranscriptSegment,
)
```

Verifying a signed delivery (see [Verifying Webhook Signatures](https://docs.omi.me/doc/developer/apps/Integrations#verifying-webhook-signatures)
for how to issue a secret and what the header contains):

```python
from fastapi import FastAPI, HTTPException, Request

from omi_plugin_sdk import Conversation, verify_signature

app = FastAPI()


@app.post("/webhook")
async def conversation_created(request: Request, uid: str):
    body = await request.body()  # raw bytes: parse only after verifying
    if not verify_signature(request.headers, body, OMI_WEBHOOK_SECRET, uid=uid):
        raise HTTPException(status_code=401, detail="Invalid Omi signature")
    conversation = Conversation.model_validate_json(body)
    ...
```

`verify_signature` checks the HMAC over `"<t>.<uid>." + body`, rejects timestamps more than
five minutes away from now (`tolerance_seconds`), and accepts either secret during a rotation.

The SDK owns Omi webhook payload models and this verifier. App-specific OAuth state,
persisted settings, provider clients, and business logic stay inside each app.
