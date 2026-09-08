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

The SDK owns Omi webhook payload models. App-specific OAuth state, persisted
settings, provider clients, and business logic stay inside each app.
