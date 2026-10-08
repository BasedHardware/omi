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

Verifying a chat-tool call (see [Verify every tool call](https://docs.omi.me/doc/developer/apps/ChatTools#verify-every-tool-call)).
Chat-tool calls are signed with the same per-app secret, but with the request-bound `v2`
scheme, so they need the method, path and query as well as the body:

```python
import json

from fastapi import FastAPI, HTTPException, Request

from omi_plugin_sdk import verify_request

app = FastAPI()


@app.post("/tools/like_tweet")
async def like_tweet(request: Request):
    body = await request.body()  # raw bytes: parse only after verifying
    if not verify_request(
        request.headers,
        body,
        OMI_SIGNING_SECRET,
        method=request.method,
        path=request.url.path,  # the public path, if a proxy in front rewrites it
        query=request.query_params.multi_items(),
    ):
        raise HTTPException(status_code=401, detail="Invalid Omi signature")
    call = json.loads(body)  # a GET tool reads request.query_params instead
    uid = call["uid"]  # only now is uid trustworthy
    ...
```

`verify_request` checks the HMAC over the method, path, query, body, `X-Omi-Delivery` and
`X-Omi-Event`, so a captured call cannot be replayed with other arguments, against another tool's
path or with another method; the same five-minute window and rotation rules apply. To reject an
exact replay inside the window, remember `X-Omi-Delivery` values for five minutes and refuse
repeats. `canonical_query`, `canonical_path` and `compute_request_signature` in
`omi_plugin_sdk.webhook_signing` let you build a signed request to test your own endpoint.

The SDK owns Omi webhook payload models and these verifiers. App-specific OAuth state,
persisted settings, provider clients, and business logic stay inside each app.
