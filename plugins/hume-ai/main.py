"""
Omi Audio Emotion Analysis - FastAPI Server
Main file with API endpoints only. Helper functions are in app.py
"""

import os
import tempfile
from datetime import datetime
from typing import Optional
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# FastAPI imports
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

# Import all helper functions from app.py
from app import (
    # Config and globals
    audio_stats,
    EMOTION_CONFIG,
    load_emotion_config,

    # Rizz functions
    update_rizz_score,
    get_rizz_status_text,
    get_rizz_notification_message,
    can_send_notification,
    update_notification_time,
    NOTIFICATION_COOLDOWN_SECONDS,

    # Audio processing
    create_wav_header,
    cleanup_old_audio_files,

    # Omi integration
    send_omi_notification,
    create_omi_memory,
    save_emotion_memory,
    emotion_memory_background_task,
    generate_emotion_summary,

    # Emotion detection
    check_emotion_triggers,

    # Hume AI
    analyze_text_with_hume,
    analyze_audio_with_hume,
)

# Initialize FastAPI app
app = FastAPI(title="Omi Audio Streaming Service with Hume AI")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")


# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize background tasks on server startup"""
    import asyncio

    print("🚀 Starting emotion memory background task (runs every 1 hour)...")
    asyncio.create_task(emotion_memory_background_task())

    print("🗑️  Starting audio file cleanup task (runs every 1 minute)...")
    asyncio.create_task(cleanup_old_audio_files())


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.post("/audio")
async def handle_audio_stream(
    request: Request,
    sample_rate: int = Query(..., description="Audio sample rate in Hz"),
    uid: str = Query(..., description="User ID"),
    analyze_emotion: bool = Query(True, description="Whether to analyze emotions with Hume AI"),
    send_notification: Optional[bool] = Query(None, description="Override notification setting (uses config default if not specified)"),
    emotion_filters: Optional[str] = Query(None, description="Override emotion filters (uses config default if not specified)")
):
    """
    Endpoint to receive audio bytes from Omi device and analyze with Hume AI.

    Query Parameters:
        - sample_rate: Audio sample rate (e.g., 8000 or 16000)
        - uid: User unique ID
        - analyze_emotion: Whether to analyze emotions with Hume AI (default: True)
        - send_notification: Whether to send Omi notification (uses config default if not specified)
        - emotion_filters: JSON string of emotion:threshold pairs
                          Examples:
                          - '{"Anger":0.7}' - notify only if Anger >= 0.7
                          - '{"Anger":0.7,"Sadness":0.6}' - notify if Anger >= 0.7 OR Sadness >= 0.6
                          - null - notify for all detected emotions

    Body:
        - Binary audio data (application/octet-stream)

    Examples:
        # Basic emotion analysis
        POST /audio?sample_rate=16000&uid=user123

        # With notification for any emotion
        POST /audio?sample_rate=16000&uid=user123&send_notification=true

        # With notification only for high anger or sadness
        POST /audio?sample_rate=16000&uid=user123&send_notification=true&emotion_filters={"Anger":0.7,"Sadness":0.6}
    """
    try:
        # Update stats
        audio_stats["total_requests"] += 1
        audio_stats["last_request_time"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        audio_stats["last_uid"] = uid

        # Read audio bytes from request body
        audio_data = await request.body()

        if not audio_data:
            raise HTTPException(status_code=400, detail="No audio data received")

        print(f"Received {len(audio_data)} bytes of audio from user {uid} at {sample_rate}Hz")

        # Create temporary WAV file
        audio_dir = Path("audio_files")
        audio_dir.mkdir(exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{uid}_{timestamp}.wav"
        local_file_path = audio_dir / filename

        # Write WAV file with header
        wav_header = create_wav_header(sample_rate, len(audio_data))
        with open(local_file_path, 'wb') as f:
            f.write(wav_header)
            f.write(audio_data)

        print(f"Saved audio file: {local_file_path}")

        # Analyze with Hume AI if requested
        hume_results = None
        if analyze_emotion:
            hume_api_key = os.getenv('HUME_API_KEY')
            if not hume_api_key:
                print("Warning: HUME_API_KEY not set, skipping emotion analysis")
            else:
                print(f"Analyzing audio with Hume AI...")
                hume_results = await analyze_audio_with_hume(str(local_file_path))

                if hume_results.get("success"):
                    audio_stats["successful_analyses"] += 1

                    predictions = hume_results.get("predictions", [])
                    all_top_emotions = []

                    for pred in predictions:
                        top_3 = pred.get("top_3_emotions", [])
                        all_top_emotions.extend(top_3)

                        for emotion in top_3:
                            emotion_name = emotion.get("name")
                            if emotion_name:
                                audio_stats["emotion_counts"][emotion_name] = \
                                    audio_stats["emotion_counts"].get(emotion_name, 0) + 1

                    if all_top_emotions:
                        audio_stats["recent_emotions"] = all_top_emotions[:10]
                        update_rizz_score(all_top_emotions)

                    # Check if should send notification
                    should_notify = send_notification if send_notification is not None else EMOTION_CONFIG.get("notification_enabled", True)
                    has_predictions = len(predictions) > 0

                    print(f"🔔 Notification check: should_notify={should_notify}, has_predictions={has_predictions}")

                    if should_notify and has_predictions:
                        import json

                        # Use custom filters if provided, otherwise use config
                        if emotion_filters:
                            try:
                                custom_filters = json.loads(emotion_filters)
                                print(f"Using custom emotion filters: {custom_filters}")
                            except json.JSONDecodeError:
                                print(f"Warning: Invalid emotion_filters JSON, using config default")
                                custom_filters = EMOTION_CONFIG.get("emotion_thresholds", {})
                        else:
                            custom_filters = EMOTION_CONFIG.get("emotion_thresholds", {})
                            print(f"Using config emotion filters: {custom_filters}")

                        # Check trigger conditions
                        trigger_result = check_emotion_triggers(predictions, custom_filters)
                        print(f"📊 Trigger check result: triggered={trigger_result['triggered']}, count={trigger_result['count']}")

                        if trigger_result["triggered"]:
                            triggered_emotions = trigger_result["emotions"]
                            emotion_names = [e["name"] for e in triggered_emotions[:3]]

                            # Check cooldown before sending notification
                            if can_send_notification():
                                message = get_rizz_notification_message(audio_stats["rizz_score"], triggered_emotions)

                                notification_result = await send_omi_notification(uid, message)

                                if notification_result.get("success"):
                                    update_notification_time()
                                    audio_stats["recent_notifications"].append({
                                        "uid": uid,
                                        "emotions": emotion_names,
                                        "timestamp": datetime.utcnow().isoformat()
                                    })
                                    audio_stats["recent_notifications"] = audio_stats["recent_notifications"][-10:]
                            else:
                                print(f"⏳ Notification cooldown active. Skipping notification.")

                else:
                    audio_stats["failed_analyses"] += 1

        response_data = {
            "message": "Audio processed successfully",
            "filename": filename,
            "uid": uid,
            "sample_rate": sample_rate,
            "data_size_bytes": len(audio_data),
            "timestamp": timestamp,
            "local_file_path": str(local_file_path.absolute())
        }

        # Add Hume results if available
        if hume_results:
            response_data["hume_analysis"] = hume_results

        return JSONResponse(
            status_code=200,
            content=response_data
        )

    except Exception as e:
        print(f"Error processing audio: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint with web interface"""
    hume_configured = bool(os.getenv('HUME_API_KEY'))
    omi_configured = bool(os.getenv('OMI_APP_ID') and os.getenv('OMI_API_KEY'))

    # Build emotion statistics data
    emotion_stats = []
    if audio_stats['emotion_counts']:
        sorted_emotions = sorted(
            audio_stats['emotion_counts'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        total_count = sum(audio_stats['emotion_counts'].values())

        for emotion, count in sorted_emotions:
            percentage = (count / total_count) * 100
            bar_width = int(percentage * 2)
            bar = '█' * bar_width
            emotion_stats.append((emotion, count, percentage, bar))

    # Rizz meter display
    rizz_score = audio_stats.get("rizz_score", 75)
    rizz_status = get_rizz_status_text(rizz_score)
    rizz_color = "#4CAF50" if rizz_score >= 60 else "#ff9800" if rizz_score >= 40 else "#f44336"
    rizz_bg_color = "#2ecc71" if rizz_score >= 60 else "#f39c12" if rizz_score >= 40 else "#e74c3c"

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "hume_configured": hume_configured,
        "omi_configured": omi_configured,
        "stats": audio_stats,
        "emotion_stats": emotion_stats,
        "rizz_score": rizz_score,
        "rizz_status": rizz_status,
        "rizz_color": rizz_color,
        "rizz_bg_color": rizz_bg_color,
        "ngrok_url": os.getenv('NGROK_URL', 'https://your-ngrok-url.ngrok-free.app')
    })


@app.get("/status")
async def get_status():
    """Get current server status and stats"""
    hume_configured = bool(os.getenv('HUME_API_KEY'))
    omi_configured = bool(os.getenv('OMI_APP_ID') and os.getenv('OMI_API_KEY'))

    return JSONResponse({
        "status": "online",
        "service": "omi-audio-streaming",
        "configuration": {
            "hume_ai": hume_configured,
            "omi_integration": omi_configured
        },
        "stats": audio_stats
    })


@app.post("/analyze-text")
async def analyze_text_emotion(
    request: Request,
    uid: Optional[str] = Query(None, description="User ID (optional)")
):
    """
    Analyze emotion from text using Hume AI Language model.

    ⚠️ NOTE: This endpoint has NOT been tested yet.
    It's available for future use if you want to combine audio + text emotion analysis.
    Currently, the /audio endpoint only processes audio (speech prosody).

    Body (JSON):
    {
        "text": "Your text here...",
        "metadata": {}  // optional
    }

    Example curl:
        curl -X POST "https://your-url/analyze-text?uid=user123" \
             -H "Content-Type: application/json" \
             -d '{"text": "I am feeling really happy and excited today!"}'
    """
    try:
        # Parse JSON body
        body = await request.json()
        text = body.get('text')
        metadata = body.get('metadata', {})

        if not text:
            raise HTTPException(status_code=400, detail="Missing 'text' field in request body")

        # Check text length (API limit is 10,000 characters)
        if len(text) > 10000:
            raise HTTPException(
                status_code=400,
                detail=f"Text too long ({len(text)} characters). Maximum is 10,000 characters."
            )

        print(f"Analyzing text emotion for user: {uid or 'anonymous'}")
        print(f"Text length: {len(text)} characters")
        print(f"Text preview: {text[:100]}...")

        # Analyze text with Hume AI
        hume_results = await analyze_text_with_hume(text)

        response_data = {
            "message": "Text emotion analysis complete",
            "text_length": len(text),
            "uid": uid,
            "hume_analysis": hume_results,
            "metadata": metadata
        }

        return JSONResponse(
            status_code=200,
            content=response_data
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error analyzing text: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/emotion-config")
async def get_emotion_config():
    """Get current emotion notification configuration"""
    return JSONResponse({
        "current_config": EMOTION_CONFIG
    })


@app.post("/emotion-config")
async def update_emotion_config(request: Request):
    """
    Update emotion notification configuration

    Body (JSON):
    {
        "notification_enabled": true,
        "emotion_thresholds": {
            "Anger": 0.7,
            "Sadness": 0.6
        }
    }
    """
    global EMOTION_CONFIG

    try:
        new_config = await request.json()

        # Validate config
        if "notification_enabled" in new_config:
            if not isinstance(new_config["notification_enabled"], bool):
                raise HTTPException(status_code=400, detail="notification_enabled must be boolean")

        if "emotion_thresholds" in new_config:
            if not isinstance(new_config["emotion_thresholds"], dict):
                raise HTTPException(status_code=400, detail="emotion_thresholds must be a dict")

            # Validate thresholds are numbers between 0 and 1
            for emotion, threshold in new_config["emotion_thresholds"].items():
                if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Threshold for {emotion} must be between 0 and 1"
                    )

        # Update configuration
        EMOTION_CONFIG.update(new_config)

        # Save to file
        import json
        config_file = Path("emotion_config.json")
        with open(config_file, 'w') as f:
            json.dump(EMOTION_CONFIG, f, indent=2)

        print(f"✓ Updated emotion config: {EMOTION_CONFIG}")

        return {
            "message": "Configuration updated successfully",
            "new_config": EMOTION_CONFIG
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-stats")
async def reset_stats(request: Request):
    """Reset all statistics (requires confirmation)"""
    try:
        body = await request.json()
        if not body.get("confirm"):
            raise HTTPException(status_code=400, detail="Confirmation required")

        # Reset stats
        audio_stats["total_requests"] = 0
        audio_stats["successful_analyses"] = 0
        audio_stats["failed_analyses"] = 0
        audio_stats["last_request_time"] = None
        audio_stats["last_uid"] = None
        audio_stats["recent_emotions"] = []
        audio_stats["emotion_counts"] = {}
        audio_stats["rizz_score"] = 75
        audio_stats["recent_notifications"] = []

        print("✓ Statistics reset")

        return {"message": "Statistics reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error resetting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save-emotion-memory")
async def manual_save_emotion_memory(uid: Optional[str] = Query(None, description="User ID (optional)")):
    """
    Manually save current emotion statistics to Omi memories.

    Query Parameters:
        - uid: User ID (optional, uses last active user if not provided)
    """
    result = await save_emotion_memory(uid)

    if result.get("success"):
        return JSONResponse(
            status_code=200,
            content={
                "message": "Emotion memory saved successfully",
                "result": result
            }
        )
    else:
        return JSONResponse(
            status_code=400,
            content={
                "message": "Failed to save emotion memory",
                "error": result.get("error")
            }
        )


@app.post("/force-send-notification")
async def force_send_notification_endpoint(uid: Optional[str] = Query(None, description="User ID (optional)")):
    """
    Force send a notification immediately, bypassing cooldown.

    Query Parameters:
        - uid: User ID (optional, uses last active user if not provided)
    """
    target_uid = uid or audio_stats.get("last_uid")

    if not target_uid:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No user ID available. Please provide a UID or speak into your Omi device first.",
                "success": False
            }
        )

    # Get recent emotions for the notification
    recent_emotions = audio_stats.get("recent_emotions", [])[:3]

    if not recent_emotions:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No recent emotions detected. Please speak into your Omi device first.",
                "success": False
            }
        )

    # Generate message with current rizz score
    message = get_rizz_notification_message(audio_stats["rizz_score"], recent_emotions)

    # Send notification (force, ignore cooldown)
    notification_result = await send_omi_notification(target_uid, message)

    if notification_result.get("success"):
        # Update notification time
        update_notification_time()

        # Log notification
        emotion_names = [e.get("name") for e in recent_emotions]
        audio_stats["recent_notifications"].append({
            "uid": target_uid,
            "emotions": emotion_names,
            "timestamp": datetime.utcnow().isoformat(),
            "forced": True
        })
        audio_stats["recent_notifications"] = audio_stats["recent_notifications"][-10:]

        return JSONResponse(
            status_code=200,
            content={
                "message": "Notification sent successfully",
                "success": True,
                "uid": target_uid,
                "notification_message": message,
                "emotions": emotion_names
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "message": "Failed to send notification",
                "success": False,
                "error": notification_result.get("error")
            }
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "omi-audio-streaming"}


# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == "__main__":
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8080)
