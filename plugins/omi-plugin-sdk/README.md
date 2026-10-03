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

The SDK owns Omi webhook payload models and shared HMAC auth helpers
(`omi_plugin_sdk.auth`). Bare query/body `uid` is an identity hint, **not**
authentication — plugins must call `resolve_authenticated_uid` (or
`verify_headers`) and reject unsigned requests.

App-specific OAuth state, persisted settings, provider clients, and business
logic stay inside each app.

```python
from omi_plugin_sdk.auth import (
    build_auth_headers,
    get_webhook_secret,
    resolve_authenticated_uid,
)
```
