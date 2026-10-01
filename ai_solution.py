To fix the issue where an empty ADMIN_KEY authenticates an empty secret-key, we replace the condition with `admin_key_matches`.

```python
# routers/apps.py

from utils.admin_key import admin_key_matches

# Replace all instances like:
# if secret_key != os.getenv('ADMIN_KEY'):
# with:
if admin_key_matches(secret_key):

# Similarly, in other files like updates.py, notifications.py, memory_admin.py.

# In utils/admin_key.py, ensure the function is:

def admin_key_matches(candidate: str) -> bool:
    admin_key = os.getenv('ADMIN_KEY', '')
    return candidate == admin_key
```