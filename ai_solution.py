Here is the complete code solution:

```python
from typing import Union
from urllib.parse import urlparse
from .omi import UsageError

def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if not (parsed.scheme and parsed.netloc):
        raise UsageError("Invalid URL format: URL must have a scheme and a valid host.")
    if not parsed.hostname:
        raise UsageError("Invalid URL: Host is missing.")
    if parsed.port is not None:
        if not (1 <= parsed.port <= 65535):
            raise UsageError(f"Invalid port number: {parsed.port}.")
    return url

def configure(config: dict, key: str, value: Union[str, list[str]]) -> None:
    if key == "endpoint":
        if isinstance(value, list):
            value = value[0]
        if value:
            value = value.strip()
        if value:
            try:
                value = validate_url(value)
            except ValueError as e:
                raise UsageError(str(e))
        config[key] = value
```

This code ensures that the URL is validated correctly, raising `UsageError` for any issues like missing hostname, invalid port, or malformed URLs.