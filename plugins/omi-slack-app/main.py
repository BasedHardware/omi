from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from .error_handler import exception_handler
from .slack_client import SlackClient
from .logger import logger

app = FastAPI(title="OMI Slack App")

# ----------------------------------------------------------------------
# OAuth authentication endpoint
# ----------------------------------------------------------------------
@app.get("/auth")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="OAuth initialization failed",
)
async def auth_endpoint(request: Request):
    # Simulated OAuth flow – replace with real logic
    try:
        # ... OAuth initialization logic that may raise
        raise RuntimeError("Simulated OAuth failure")  # placeholder
    except Exception as e:
        # The decorator will handle logging & sanitising
        raise e


# ----------------------------------------------------------------------
# Channel management endpoints
# ----------------------------------------------------------------------
@app.post("/update-channel")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="Failed to update channel",
)
async def update_channel(payload: dict):
    # Placeholder implementation
    raise RuntimeError("Simulated channel update error")


@app.post("/refresh-channels")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="Failed to refresh channels",
)
async def refresh_channels():
    raise RuntimeError("Simulated refresh error")


@app.post("/logout")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="Logout failed",
)
async def logout():
    raise RuntimeError("Simulated logout error")


# ----------------------------------------------------------------------
# Webhook endpoint
# ----------------------------------------------------------------------
@app.post("/webhook")
@exception_handler(
    status_code=status.HTTP_400_BAD_REQUEST,
    generic_detail="Invalid JSON payload",
)
async def webhook_endpoint(request: Request):
    try:
        payload = await request.json()
        # Process payload...
        raise RuntimeError("Simulated processing error")
    except Exception as e:
        raise e


# ----------------------------------------------------------------------
# Chat‑tool API routes (internal use)
# ----------------------------------------------------------------------
@app.post("/api/send_message")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="Failed to send message",
)
async def api_send_message(payload: dict):
    token = payload.get("token")
    channel = payload.get("channel")
    text = payload.get("text")
    client = SlackClient(token)
    result = await client.send_message(channel, text)
    return JSONResponse(content=result)


@app.post("/api/search_messages")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="Failed to search messages",
)
async def api_search_messages(payload: dict):
    token = payload.get("token")
    query = payload.get("query")
    client = SlackClient(token)
    result = await client.search_messages(query)
    return JSONResponse(content={"matches": result})


@app.post("/api/search_channels")
@exception_handler(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    generic_detail="Failed to search channels",
)
async def api_search_channels(payload: dict):
    token = payload.get("token")
    query = payload.get("query")
    client = SlackClient(token)
    # Re‑use search_messages for simplicity – real implementation may differ
    result = await client.search_messages(query)
    return JSONResponse(content={"matches": result})
