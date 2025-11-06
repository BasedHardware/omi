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
async def root():
    """Root endpoint with web interface"""
    hume_configured = bool(os.getenv('HUME_API_KEY'))
    omi_configured = bool(os.getenv('OMI_APP_ID') and os.getenv('OMI_API_KEY'))

    # Build emotion statistics HTML
    emotion_stats_html = ''
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
            emotion_stats_html += f"""
                <div style="margin: 10px 0; font-family: monospace;">
                    <span style="display: inline-block; width: 150px;">{emotion}</span>
                    <span style="color: #999;">Count: {count} | {percentage:.1f}%</span>
                    <span style="color: #4CAF50;"> {bar}</span>
                </div>
            """
    else:
        emotion_stats_html = '<p style="color: #999;">No emotion data yet. Speak into your Omi device!</p>'

    # Build recent emotions display
    recent_emotions_html = ''
    if audio_stats.get('recent_emotions'):
        for emotion in audio_stats['recent_emotions'][:5]:
            recent_emotions_html += f'<span style="background: #f0f0f0; padding: 5px 10px; margin: 5px; border-radius: 5px; display: inline-block;">{emotion.get("name")} ({emotion.get("score", 0):.2f})</span>'
    else:
        recent_emotions_html = '<p style="color: #999;">No recent emotions detected</p>'

    # Rizz meter display
    rizz_score = audio_stats.get("rizz_score", 75)
    rizz_status = get_rizz_status_text(rizz_score)
    rizz_color = "#4CAF50" if rizz_score >= 60 else "#ff9800" if rizz_score >= 40 else "#f44336"
    rizz_bg_color = "#2ecc71" if rizz_score >= 60 else "#f39c12" if rizz_score >= 40 else "#e74c3c"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Omi Audio Emotion Analysis Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
            }}
            .container {{
                background: white;
                border-radius: 15px;
                padding: 30px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #667eea;
                margin: 0 0 10px 0;
                font-size: 28px;
            }}
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }}
            .stat-card {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
                border-radius: 10px;
                color: white;
                text-align: center;
            }}
            .stat-value {{
                font-size: 32px;
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .stat-label {{
                font-size: 14px;
                opacity: 0.9;
            }}
            .config-section {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .check {{
                color: #4CAF50;
                font-weight: bold;
            }}
            .cross {{
                color: #f44336;
                font-weight: bold;
            }}
            .endpoint {{
                background: #f0f0f0;
                padding: 10px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 13px;
                margin: 10px 0;
                word-break: break-all;
            }}
            .refresh-btn {{
                background: #667eea;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: background 0.3s;
            }}
            .refresh-btn:hover {{
                background: #5568d3;
            }}
            .rizz-meter {{
                background: {rizz_bg_color};
                height: 30px;
                border-radius: 15px;
                position: relative;
                margin: 20px 0;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .rizz-indicator {{
                position: absolute;
                top: 0;
                left: {rizz_score}%;
                width: 4px;
                height: 100%;
                background: white;
                box-shadow: 0 0 10px rgba(0,0,0,0.5);
            }}
            .rizz-text {{
                text-align: center;
                font-size: 20px;
                font-weight: bold;
                color: {rizz_color};
                margin: 10px 0;
            }}
        </style>
        <script>
            setTimeout(() => {{
                window.location.reload();
            }}, 10000);

            function refreshPage() {{
                window.location.reload();
            }}

            async function resetStats() {{
                if (!confirm('Are you sure you want to reset all statistics?')) {{
                    return;
                }}

                try {{
                    const response = await fetch('/reset-stats', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }},
                        body: JSON.stringify({{ confirm: true }})
                    }});

                    if (response.ok) {{
                        alert('Statistics reset successfully!');
                        window.location.reload();
                    }} else {{
                        alert('Failed to reset statistics');
                    }}
                }} catch (error) {{
                    alert('Error: ' + error.message);
                }}
            }}

            async function forceSendNotification() {{
                const statusEl = document.getElementById('notificationStatus');
                statusEl.textContent = '🔔 Sending notification...';
                statusEl.style.color = '#666';

                try {{
                    const response = await fetch('/force-send-notification', {{
                        method: 'POST'
                    }});

                    const data = await response.json();

                    if (response.ok) {{
                        statusEl.textContent = `✅ Notification sent! "${{data.notification_message}}"`;
                        statusEl.style.color = '#28a745';
                        setTimeout(() => {{ statusEl.textContent = ''; }}, 5000);
                    }} else {{
                        statusEl.textContent = `❌ ${{data.message || 'Failed to send'}}`;
                        statusEl.style.color = '#dc3545';
                    }}
                }} catch (error) {{
                    statusEl.textContent = `❌ Error: ${{error.message}}`;
                    statusEl.style.color = '#dc3545';
                }}
            }}

            async function saveEmotionMemory() {{
                const statusEl = document.getElementById('memoryStatus');
                statusEl.textContent = '💾 Saving emotion summary to memories...';
                statusEl.style.color = '#666';

                try {{
                    const response = await fetch('/save-emotion-memory', {{
                        method: 'POST'
                    }});

                    const data = await response.json();

                    if (response.ok) {{
                        statusEl.textContent = '✅ Emotion summary saved to memories!';
                        statusEl.style.color = '#28a745';
                        setTimeout(() => {{ statusEl.textContent = ''; }}, 3000);
                    }} else {{
                        statusEl.textContent = `❌ Error: ${{data.error || 'Failed to save'}}`;
                        statusEl.style.color = '#dc3545';
                    }}
                }} catch (error) {{
                    statusEl.textContent = `❌ Error: ${{error.message}}`;
                    statusEl.style.color = '#dc3545';
                }}
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>🎤 Omi Audio Streaming Service ONLINE</h1>
            <p style="text-align: center; color: #999; font-size: 13px; margin: 0 0 10px 0;">
                Developer: Livia Ellen
            </p>
            <p style="text-align: center; font-size: 13px; margin: 0 0 30px 0;">
                <a href="https://www.hume.ai/products/speech-prosody-model" target="_blank" style="color: #667eea; text-decoration: none;">
                    🧠 Learn how we detect rizz + vibe + emotion using Hume AI Speech Prosody →
                </a>
            </p>

            <div class="config-section">
                <h3>⚙️ Configuration Status</h3>
                <p><span class="{'check' if hume_configured else 'cross'}">{'✓' if hume_configured else '✗'}</span> Hume AI API Key: {'Configured' if hume_configured else 'Not configured'}</p>
                <p><span class="{'check' if omi_configured else 'cross'}">{'✓' if omi_configured else '✗'}</span> Omi Integration: {'Configured' if omi_configured else 'Not configured'}</p>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{audio_stats['total_requests']}</div>
                    <div class="stat-label">Total Requests</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{audio_stats['successful_analyses']}</div>
                    <div class="stat-label">Successful</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{audio_stats['failed_analyses']}</div>
                    <div class="stat-label">Failed</div>
                </div>
            </div>

            <div class="config-section">
                <h3>🎭 Rizz Meter</h3>
                <div class="rizz-text">{rizz_status}</div>
                <div class="rizz-meter">
                    <div class="rizz-indicator"></div>
                </div>
                <p style="text-align: center; color: #666; font-size: 14px;">Score: {rizz_score:.0f}/100</p>
            </div>

            <div class="config-section">
                <h3>📊 Last Activity</h3>
                <p><strong>Time:</strong> {audio_stats['last_request_time'] or 'No requests yet'}</p>
                <p><strong>User ID:</strong> {audio_stats.get('last_uid', 'N/A')}</p>
                <div style="margin-top: 10px;">
                    {recent_emotions_html}
                </div>
            </div>

            <div class="config-section">
                <h3>🎭 Emotion Statistics</h3>
                {emotion_stats_html}
            </div>

            <div class="config-section">
                <h3>📱 Configure Your Omi Device</h3>
                <p style="font-size: 14px; line-height: 1.6; margin-bottom: 15px;">
                    <strong>Step 1: Enable Audio Streaming</strong>
                </p>
                <ol style="line-height: 1.8; margin-bottom: 20px;">
                    <li>Open the <strong>Omi App</strong></li>
                    <li>Go to <strong>Settings → Developer Mode</strong></li>
                    <li>Toggle <strong>Developer Mode ON</strong></li>
                    <li>Set <strong>"Realtime audio bytes"</strong> to:</li>
                    <div class="endpoint" id="audioUrl">{os.getenv('NGROK_URL', 'https://your-ngrok-url.ngrok-free.app')}/audio</div>
                    <li>Set <strong>"Every x seconds"</strong> to <code>5</code></li>
                </ol>

                <p style="font-size: 14px; line-height: 1.6; margin-bottom: 15px;">
                    <strong>Step 2: Create Integration App</strong>
                </p>
                <ol style="line-height: 1.8; margin-bottom: 20px;">
                    <li>Go to <strong>Apps</strong> tab → Click <strong>Create App</strong></li>
                    <li>Select <strong>External Integration</strong></li>
                    <li>Toggle <strong>"Audio Bytes Trigger"</strong> ON</li>
                    <li>Toggle <strong>"Create Memories"</strong> ON</li>
                    <li>Set Webhook URL to the same audio endpoint above</li>
                    <li>Save and <strong>Install the App</strong></li>
                </ol>

                <p style="font-size: 14px; line-height: 1.6; margin-bottom: 15px;">
                    <strong>Step 3: Update Environment Variables</strong>
                </p>
                <ol style="line-height: 1.8; margin-bottom: 20px;">
                    <li>Copy your <strong>App ID</strong> and <strong>API Key</strong> from the app</li>
                    <li>Go to <strong>Render Dashboard</strong> → Your Service → <strong>Environment</strong></li>
                    <li>Add/Update these variables:
                        <div style="background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; font-family: monospace; font-size: 12px;">
                            HUME_API_KEY=your_hume_api_key<br>
                            OMI_APP_ID=your_omi_app_id<br>
                            OMI_API_KEY=your_omi_api_key
                        </div>
                    </li>
                    <li>Save changes and wait for auto-redeploy</li>
                </ol>

                <p style="font-size: 13px; color: #666; margin-top: 15px;">
                    📖 For detailed setup instructions, see the
                    <a href="https://github.com/liviaellen/audio-sentiment-profiling#readme" target="_blank" style="color: #667eea; text-decoration: none;">
                        project README
                    </a>
                </p>
            </div>

            <div style="display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap;">
                <button class="refresh-btn" onclick="refreshPage()">🔄 Refresh Status</button>
                <button class="refresh-btn" onclick="forceSendNotification()" style="background: #ff6b35;">🔔 Send Notification</button>
                <button class="refresh-btn" onclick="resetStats()" style="background: #dc3545;">🗑️ Reset Statistics</button>
            </div>
            <p id="notificationStatus" style="color: #666; font-size: 14px; margin-top: 10px;"></p>
            {'<p style="color: #28a745; font-size: 13px; margin-top: 10px;">✓ User ID: ' + audio_stats.get("last_uid", "Not available") + '</p>' if audio_stats.get("last_uid") else '<p style="color: #ff9800; font-size: 13px; margin-top: 10px;">⚠️ No audio received yet. Speak into your Omi device first.</p>'}
            <p style="color: #666; font-size: 12px; margin-top: 10px;">Page auto-refreshes every 10 seconds</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


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
