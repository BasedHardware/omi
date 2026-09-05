# omi-integration (Python)

OpenAPI-generated client for the Omi Integration API.

```bash
pip install -e sdks/integration/python
```

```python
from omi_integration import OmiIntegrationClient

with OmiIntegrationClient("YOUR_KEY", "YOUR_APP_ID") as client:
    print(client.list_memories("USER_UID"))
```

See the parent [README](../README.md) for all languages and regenerate instructions.
