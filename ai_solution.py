```python
import re

def is_valid_api_key(key: str) -> bool:
    """
    Validate that the API key contains only ASCII characters.
    """
    return all(c.isascii() for c in key)

class APIKey:
    @staticmethod
    def login(args):
        key = args.api_key.strip()
        if len(key) == 0:
            raise UsageError("API key is required.")
        if not is_valid_api_key(key):
            raise UsageError("API key must contain only ASCII characters.")
        # Continue with the rest of the logic
```

The code includes:
1. A helper function `is_valid_api_key` that checks if all characters are ASCII.
2. The `login` method raises a `UsageError` with an appropriate message when the key is invalid.
3. The solution maintains the existing trimming and preserves the original behavior for valid keys.

A test case for the new validation is included in the component tests.