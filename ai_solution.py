To address the issue where a malformed summary app causes conversation processing to fail, the code is modified to safely deserialize each app and handle any validation errors.

```python
from ....utils.conversations.process_conversation import get_default_conversation_summarized_apps
from ....utils.conversations.process_conversation import trigger_conversation_apps

def get_default_conversation_summarized_apps():
    """Get default conversation summarized apps."""
    from ....utils.models import App
    from ....utils.redis import get_redis

    redis = get_redis()
    config = redis.hgetall("config") if redis else {}
    configured_ids = [k for k in (config.get("conversation_summarized_apps") or []) if k]
    
    apps = []
    for app_id in configured_ids:
        try:
            app = App.deserialize_safe(app_id)
        except ValidationError:
            continue
        apps.append(app)
    return apps
```

This code ensures that each app is safely deserialized, and any malformed app is skipped, allowing the conversation processing to proceed with valid apps.