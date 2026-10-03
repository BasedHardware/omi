<content>
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from .app import send_omi_notification, save_emotion_memory, process_audio

app = FastAPI()

security = HTTPBearer()

def verify_hume_tools_secret(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the HUME_TOOLS_SECRET for authentication."""
    secret = os.environ.get("HUME_TOOLS_SECRET")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: HUME_TOOLS_SECRET not set"
        )
    if credentials.credentials != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing HUME_TOOLS_SECRET"
        )
    return credentials

@app.post("/audio")
async def audio_upload(request: Request, uid: str, hume_tools_token: str = None):
    """
    Ingest audio keyed by uid with authentication.
    """
    # Check for token in query parameter or Authorization header
    if hume_tools_token != os.environ.get("HUME_TOOLS_SECRET"):
        try:
            await verify_hume_tools_secret(request)
        except HTTPException as e:
            # If header check fails, return the error
            raise e
    
    # Process the audio
    form_data = await request.form()
    audio_file = form_data.get("audio")
    send_notification = form_data.get("send_notification", "false").lower() == "true"
    
    if not audio_file:
        raise HTTPException(status_code=400, detail="No audio file provided")
    
    # Process the audio (original logic)
    return await process_audio(uid, audio_file, send_notification)

@app.post("/save-emotion-memory")
async def save_memory(request: Request, uid: str, hume_tools_token: str = None):
    """
    Save an emotion memory into a user's Omi account with authentication.
    """
    # Check for token in query parameter or Authorization header
    if hume_tools_token != os.environ.get("HUME_TOOLS_SECRET"):
        try:
            await verify_hume_tools_secret(request)
        except HTTPException as e:
            # If header check fails, return the error
            raise e
    
    # Get form data
    form_data = await request.form()
    emotion_data = form_data.get("emotion_data")
    
    if not emotion_data:
        raise HTTPException(status_code=400, detail="No emotion data provided")
    
    # Save the memory (original logic)
    return await save_emotion_memory(uid, emotion_data)

@app.post("/force-send-notification")
async def force_send_notification(request: Request, uid: str, hume_tools_token: str = None):
    """
    Force send a notification to a user with authentication.
    """
    # Check for token in query parameter or Authorization header
    if hume_tools_token != os.environ.get("HUME_TOOLS_SECRET"):
        try:
            await verify_hume_tools_secret(request)
        except HTTPException as e:
            # If header check fails, return the error
            raise e
    
    # Get form data
    form_data = await request.form()
    message = form_data.get("message")
    
    if not message:
        raise HTTPException(status_code=400, detail="No message provided")
    
    # Send the notification (original logic)
    return await send_omi_notification(uid, message)
</content>