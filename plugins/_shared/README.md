# `plugins/_shared/`

Code shared by the AI Clone plugins (Telegram, WhatsApp, iMessage).

## Contents

- `persona_client.py` — async HTTP client for the Omi persona-chat API.
  Imports: `from persona_client import chat`. Call shape:
  ```python
  reply = await chat(
      app_id="persona_abc",          # Omi persona app id
      api_key="omi_dev_...",          # user's app API key
      omi_base="https://api.omi.me",  # backend base URL
      text="hi",                     # inbound message text
      uid="<user uid>",              # REQUIRED: Omi user id the persona reply is generated for.
                                     # The backend uses this to verify the API key was
                                     # issued for this exact uid (auth boundary — an
                                     # app-level key cannot impersonate arbitrary users).
      timeout_seconds=30.0,           # optional; default 30
      context=None,                   # optional; platform context forwarded to the persona
  )
  ```
  - `reply == ""` on timeout/connect error (logged at ERROR, includes uid).
  - Raises `httpx.HTTPStatusError` on 4xx/5xx (caller decides retry).
- `test/test_persona_client.py` — 13 unit tests (success, SSE parsing, errors, uid-param contract).
- `test/test_contract.py` — 4 tests pinning the URL and query-param contract with the backend route.

## Running the tests

The async tests (`test_persona_client.py`, `test_contract.py`) require `pytest-asyncio` and the module's runtime deps (`httpx`, `httpx-sse`). Install the dev requirements and run pytest from the repo root:

```bash
pip install -r plugins/_shared/requirements-dev.txt
pytest plugins/_shared/test/ -v
```

The plugin that consumes this client (`plugins/omi-telegram-app/`) has its own `requirements-dev.txt` — run its tests from the plugin dir.

## Usage from a plugin

```python
import sys, os
# main.py lives at plugins/<plugin>/main.py; _shared/ is at plugins/_shared/.
# So from main.py, `_shared/` is one `..` up: plugins/<plugin>/.. → plugins/_shared.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_shared")))
from persona_client import chat

reply = await chat(
    app_id=user.persona_id,
    api_key=user.omi_dev_api_key,
    omi_base="https://api.omi.me",
    text=incoming_message.text,
    uid=user.omi_uid,  # the Omi user the persona reply is generated for
)
```

The plugin's `requirements.txt` must include `httpx==0.27.2` and `httpx-sse==0.4.3` (exact pins — keep these in sync with the versions used by every plugin's runtime and the shared dev requirements to avoid silent version drift).

## Conventions

- One async function per file. No classes.
- No framework imports — pure stdlib + httpx + httpx-sse.
- Logging via the standard `logging` module under the `persona_client` logger name.