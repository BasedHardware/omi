# `plugins/_shared/`

Code shared by the AI Clone plugins (Telegram, WhatsApp, iMessage).

## Contents

- `persona_client.py` — async HTTP client for the Omi persona-chat API.
  Imports: `from persona_client import chat`. Signature:
  ```python
  reply = await chat(
      app_id,           # Omi persona app id (e.g. "persona_abc")
      api_key,          # user's app API key ("omi_dev_...")
      omi_base,         # backend base URL (e.g. "https://api.omi.me")
      text,             # inbound message text
      *,
      uid,              # REQUIRED: Omi user id the persona reply is generated for.
                       # The backend uses this to verify the API key was issued
                       # for this exact uid (auth boundary — an app-level key
                       # cannot impersonate arbitrary users).
      timeout_seconds=30.0,
      context=None,
  )
  ```
  - `reply == ""` on timeout/connect error (logged at ERROR, includes uid).
  - Raises `httpx.HTTPStatusError` on 4xx/5xx (caller decides retry).
- `test/test_persona_client.py` — 13 unit tests (success, SSE parsing, errors, uid-param contract).
- `test/test_contract.py` — 4 tests pinning the URL and query-param contract with the backend route.

## Usage from a plugin

```python
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "_shared")))
from persona_client import chat

reply = await chat(
    app_id=user.persona_id,
    api_key=user.omi_dev_api_key,
    omi_base="https://api.omi.me",
    text=incoming_message.text,
    uid=user.omi_uid,  # the Omi user the persona reply is generated for
)
```

The plugin's `requirements.txt` must include `httpx>=0.27` and `httpx-sse>=0.4`.

## Conventions

- One async function per file. No classes.
- No framework imports — pure stdlib + httpx + httpx-sse.
- Logging via the standard `logging` module under the `persona_client` logger name.