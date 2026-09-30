The task is to fix the `daily-summary` by replacing the use of `deserialize_conversation` with `deserialize_conversations` to handle a batch of conversations safely, allowing the daily recap to be generated even if one conversation is malformed.

Here's the fixed code:

```python
from ..models.conversations import deserialize_conversations

# ... other code ...

conversations = deserialize_conversations(data)
```

The code now uses the batch helper function `deserialize_conversations` to safely deserialize the conversations, handling any malformed records and preventing the 500 error and lock issues.