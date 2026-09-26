```python
#!/usr/bin/env python
from omi.conversations import Omi

def conversations_to_jsonl(category=None):
    """Convert Omi conversations to JSON Lines format."""
    import json
    omi = Omi()
    seen = set()
    for conv in omi.conversations(category=category):
        if conv.id in seen:
            continue
        seen.add(conv.id)
        print(json.dumps({"id": conv.id, "messages": conv.messages}))
    
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        conversations_to_jsonl(sys.argv[1])
    else:
        conversations_to_jsonl()
```