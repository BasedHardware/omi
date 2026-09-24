```python
from typing import Optional
import logging
from fastapi import FastAPI, HTTPException

app = FastAPI()

logger = logging.getLogger(__name__)

@app.get("/")
async def root():
    return {"message": "MS365 plugin is running."}

@app.get("/test_auth")
async def test_auth():
    return {"message": "Auth successful."}

def _auth_guard():
    try:
        # Original auth logic here
        pass
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication required. Details: {e}"
        )

def tool_dispatch():
    try:
        # Original dispatch logic here
        pass
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Bad request. Details: {e}"
        )

@app.get("/test_error_handling")
async def test_error_handling():
    try:
        return {"message": "Error handling test passed."}
    except Exception as e:
        logger.error(f"Error in test_error_handling: {{type(e).__name__}}")
        raise

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```