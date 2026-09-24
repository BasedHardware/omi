Here is the fixed code for `backend/routers/phone_calls.py`:

```python
from fastapi import HTTPException
from typing import Optional
import logging
from logger import logger

async def verify_phone_number(...):
    try:
        # ... existing code ...
        if not phone_number:
            raise ValueError("Phone number is required.")
        # ... existing code ...
    except Exception as e:
        detail = "Failed to start verification"
        description = "Failed to start verification"
        logger.error(f"Error in verify_phone_number: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail=detail,
            headers={"X-Error-Description": description},
        )

async def get_phone_token(...):
    try:
        # ... existing code ...
        if not phone_number:
            raise ValueError("Phone number is required.")
        # ... existing code ...
    except Exception as e:
        detail = "Failed to generate token"
        description = "Failed to generate token"
        logger.error(f"Error in get_phone_token: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail=detail,
            headers={"X-Error-Description": description},
        )
```

The code now uses static error messages and structured logging, ensuring that only the type of exception is logged without exposing internal details.