# Coding Guidelines

## Backend

### No In-Function Imports
All imports must be at the module top level. Never import inside functions.

```python
# Bad
def my_function():
    from database.redis_db import r  # Don't do this
    r.get('key')

# Good
from database.redis_db import r

def my_function():
    r.get('key')
```

### Import from Lower-Level Modules
Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

**Module hierarchy (lowest to highest):**
1. `database/` - Database connections, cache instances
2. `utils/` - Utility functions, helpers
3. `routers/` - API endpoints
4. `main.py` - Application entry point

```python
# Bad - utils importing from routers or main
# utils/apps.py
from main import memory_cache  # Don't import from higher level
from routers.apps import some_function  # Don't import from higher level

# Good - utils importing from database
# utils/apps.py
from database.cache import get_memory_cache
from database.redis_db import r
```

## App (Flutter)

### Localization Required
All user-facing strings must use l10n. Use `context.l10n.keyName` instead of hardcoded strings. Add new keys to ARB files using `jq` (never read full ARB files - they're large and will burn tokens). See skill `add-a-new-localization-key-l10n-arb` for details.

## Testing

### Always Run Tests Before Committing
After making changes, always run the appropriate test script to verify your changes.

- **Backend changes**: Run `backend/test.sh`
- **App changes**: Run `app/test.sh`
