Here is the solution code:

```python
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

def compute_expires_at(expires_in: Any) -> Optional[str]:
    if isinstance(expires_in, (int, float)):
        seconds = expires_in
    elif isinstance(expires_in, str):
        try:
            seconds = int(expires_in)
        except ValueError:
            return None
    else:
        return None

    if not isinstance(seconds, (int, float)):
        return None

    if seconds <= 0:
        return None

    try:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        return expires_at.isoformat()
    except OverflowError:
        return None

# In `backend/routers/task_integrations.py`:
async def handle_oauth_callback(request: Request, params: dict, state: str) -> dict:
    # Existing code
    expires_in = params.get("expires_in")
    expires_at = compute_expires_at(expires_in)
    if not expires_at:
        expires_at = None
    # Continue with the rest of the code

# In `backend/utils/task_integrations_ops.py`:
async def refresh_oauth_token(request: Request, integration: dict) -> dict:
    try:
        # Existing code
        expires_in = response.json().get("expires_in")
        expires_at = compute_expires_at(expires_in)
        if expires_at is None:
            raise Exception("Invalid expires_in value")
        # Continue with the rest of the code
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh {integration['name']} token due to an internal error"
        ) from e
```