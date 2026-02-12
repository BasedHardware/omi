from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import os
import sys
from dotenv import load_dotenv
from typing import List, Dict, Any
import secrets
import asyncio

# Force unbuffered output for instant logs
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

from simple_storage import SimpleUserStorage, SimpleSessionStorage
from slack_client import SlackClient
from message_detector import MessageDetector

load_dotenv()

# Initialize services
slack_client = SlackClient()
message_detector = MessageDetector()

app = FastAPI(
    title="OMI Slack Integration",
    description="Voice-activated Slack messaging via OMI",
    version="1.0.0"
)

# Store OAuth states temporarily (in production, use Redis or similar)
oauth_states = {}

# Background task for timeout monitoring
background_task = None


async def monitor_session_timeouts():
    """Background task that monitors sessions and processes them if idle for 5+ seconds.
    Processes any recording session after 5s of inactivity, regardless of segment count."""
    print("🕐 Timeout monitor started", flush=True)
    
    while True:
        try:
            await asyncio.sleep(1)  # Check every second
            
            from simple_storage import sessions
            
            # Check all active recording sessions
            for session_id, session in list(sessions.items()):
                if session.get("message_mode") != "recording":
                    continue
                
                # Check idle time
                idle_time = SimpleSessionStorage.get_session_idle_time(session_id)
                
                if idle_time and idle_time > 5:
                    segments_count = session.get("segments_count", 0)
                    accumulated = session.get("accumulated_text", "")
                    
                    print(f"⏰ TIMEOUT MONITOR: Processing session {session_id} after {idle_time:.1f}s idle ({segments_count} segment(s))", flush=True)
                    
                    # Get user
                    uid = session.get("uid")
                    user = SimpleUserStorage.get_user(uid)
                    
                    if user:
                        # Mark as processing
                        SimpleSessionStorage.update_session(
                            session_id,
                            message_mode="processing"
                        )
                        
                        # Process the message
                        try:
                            # Fetch fresh channels
                            channels = slack_client.list_channels(user["access_token"])
                            
                            if channels:
                                SimpleUserStorage.save_user(
                                    uid=user["uid"],
                                    access_token=user["access_token"],
                                    team_id=user.get("team_id"),
                                    team_name=user.get("team_name"),
                                    selected_channel=user.get("selected_channel"),
                                    available_channels=channels
                                )
                            
                            # AI extracts channel and message
                            channel_id, channel_name, message = await message_detector.ai_extract_message_and_channel(
                                accumulated,
                                channels
                            )
                            
                            # If no channel, use default
                            if not channel_id:
                                channel_id = user.get("selected_channel")
                                if channel_id:
                                    for ch in channels:
                                        if ch["id"] == channel_id:
                                            channel_name = ch["name"]
                                            break
                            
                            if channel_id and message and len(message.strip()) >= 3:
                                print(f"⏰ Sending timeout message to #{channel_name}", flush=True)
                                
                                result = await slack_client.send_message(
                                    access_token=user["access_token"],
                                    channel_id=channel_id,
                                    text=message
                                )
                                
                                if result and result.get("success"):
                                    print(f"⏰ SUCCESS! Timeout message sent to #{channel_name}", flush=True)
                                else:
                                    print(f"⏰ FAILED: {result.get('error') if result else 'Unknown'}", flush=True)
                            else:
                                print(f"⏰ Insufficient content to send (message: '{message[:50] if message else 'None'}...')", flush=True)
                            
                            # Reset session
                            SimpleSessionStorage.reset_session(session_id)
                            
                        except Exception as e:
                            print(f"⏰ Error processing timeout: {e}", flush=True)
                            SimpleSessionStorage.reset_session(session_id)
        
        except Exception as e:
            print(f"❌ Timeout monitor error: {e}", flush=True)
            await asyncio.sleep(5)  # Wait longer on error


@app.on_event("startup")
async def startup_event():
    """Start background timeout monitor."""
    global background_task
    background_task = asyncio.create_task(monitor_session_timeouts())
    print("✅ Background timeout monitor started", flush=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background timeout monitor."""
    global background_task
    if background_task:
        background_task.cancel()
        print("🛑 Background timeout monitor stopped", flush=True)


@app.get("/")
async def root(uid: str = Query(None)):
    """Root endpoint - Homepage with channel selection (mobile-first UI)."""
    if not uid:
        return {
            "app": "OMI Slack Integration",
            "version": "1.0.0",
            "status": "active",
            "endpoints": {
                "auth": "/auth?uid=<user_id>",
                "webhook": "/webhook?session_id=<session>&uid=<user_id>",
                "setup_check": "/setup-completed?uid=<user_id>"
            }
        }
    
    # Get user info
    user = SimpleUserStorage.get_user(uid)
    
    if not user or not user.get("access_token"):
        # Not authenticated - show auth page
        auth_url = f"/auth?uid={uid}"
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    {get_mobile_css()}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">💬→📱</div>
                    <h1>Voice to Slack Messages</h1>
                    <p style="font-size: 18px;">Send Slack messages with your voice through OMI</p>
                    
                    <a href="{auth_url}" class="btn btn-primary btn-block" style="font-size: 17px; padding: 16px;">
                        🔐 Connect Slack Workspace
                    </a>
                    
                    <div class="card">
                        <h3>✨ How It Works</h3>
                        <div class="steps">
                            <div class="step">
                                <div class="step-number">1</div>
                                <div class="step-content">
                                    <strong>Connect</strong> your Slack workspace securely
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">2</div>
                                <div class="step-content">
                                    <strong>Select</strong> your default channel (optional)
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">3</div>
                                <div class="step-content">
                                    <strong>Speak</strong> your message naturally
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">4</div>
                                <div class="step-content">
                                    <strong>Done!</strong> Message posted to Slack instantly
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>🎯 Example Commands</h3>
                        <div class="example">
                            "Send Slack message to general saying hello team!"
                        </div>
                        <div class="example">
                            "Post Slack message in marketing that the campaign is live"
                        </div>
                        <div class="example">
                            "Post in Slack to random saying great idea!"
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>Powered by <strong>Omi</strong> × <strong>AI</strong></p>
                        <p style="font-size: 13px; margin-top: 8px;">Voice-first team communication</p>
                    </div>
                </div>
            </body>
        </html>
        """)
    
    # Authenticated - show channel selection page
    channels = user.get("available_channels", [])
    selected_channel = user.get("selected_channel", "")
    team_name = user.get("team_name", "Unknown")
    
    channel_options = '<option value="">Select a channel...</option>'
    for channel in channels:
        selected_attr = 'selected' if channel['id'] == selected_channel else ''
        privacy = "🔒" if channel.get('is_private') else "#"
        channel_options += f'<option value="{channel["id"]}" {selected_attr}>{privacy} {channel["name"]}</option>'
    
    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Slack Messages - Settings</title>
            <style>
                {get_mobile_css()}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card" style="margin-top: 20px;">
                    <h2>💬 Slack Settings</h2>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 8px; color: #8b949e;">
                        Connected to <span class="username">{team_name}</span>
                    </p>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 16px;">
                        Default channel (optional - you can specify channel in voice command):
                    </p>
                    
                    <select id="channelSelect" class="repo-select">
                        {channel_options if channel_options else '<option>No channels found</option>'}
                    </select>
                    
                    <button class="btn btn-primary btn-block" onclick="updateChannel()">
                        💾 Save Default Channel
                    </button>
                    <button type="button" class="btn btn-secondary btn-block" onclick="refreshChannels()">
                        🔄 Refresh Channels
                    </button>
                    <button type="button" class="btn btn-secondary btn-block" onclick="logoutUser()" style="margin-top: 20px; border-color: #e01e5a; color: #e01e5a;">
                        🚪 Logout & Clear Data
                    </button>
                </div>
                
                <div class="card" style="background: rgba(29, 155, 209, 0.05); border-color: #1d9bd1;">
                    <h3 style="font-size: 16px;">ℹ️ Reset or Re-authenticate</h3>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 0; color: #9ca0a5;">
                        Use <strong>"Logout & Clear Data"</strong> to reset your connection and re-authenticate to the same workspace with fresh settings.
                    </p>
                </div>
                
                <div class="card">
                    <h3>🎤 Using Voice Commands</h3>
                    <p style="text-align: left; margin-bottom: 16px;">
                        Simply speak to your OMI device:
                    </p>
                    <div class="steps">
                        <div class="step">
                            <div class="step-number">1</div>
                            <div class="step-content">
                                Say <strong>"Send Slack message"</strong>, <strong>"Post Slack message"</strong>, or <strong>"Post in Slack"</strong>
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">2</div>
                            <div class="step-content">
                                Mention the channel and speak your message - AI handles the rest
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">3</div>
                            <div class="step-content">
                                Message posted to Slack instantly!
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h3>💡 Pro Tips</h3>
                    <ul style="list-style: none; padding: 0;">
                        <li style="padding: 8px 0;">
                            🎯 <strong>Specify channel</strong> - "Send to general saying..."
                        </li>
                        <li style="padding: 8px 0;">
                            🔄 <strong>Use default</strong> - Just "Send message..." (uses default above)
                        </li>
                        <li style="padding: 8px 0;">
                            🗣️ <strong>Natural speech</strong> - AI cleans up filler words
                        </li>
                        <li style="padding: 8px 0;">
                            🤖 <strong>Smart matching</strong> - AI finds the right channel
                        </li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>Powered by <strong>Omi</strong> × <strong>AI</strong></p>
                    <p style="font-size: 13px; margin-top: 8px;">Voice-first Slack integration</p>
                </div>
            </div>
            
            <script>
                async function updateChannel() {{
                    const select = document.getElementById('channelSelect');
                    const channel = select.value;
                    
                    try {{
                        const response = await fetch('/update-channel?uid={uid}&channel=' + encodeURIComponent(channel), {{
                            method: 'POST'
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            alert('✅ Default channel updated!');
                        }} else {{
                            alert('❌ Failed to update: ' + data.error);
                        }}
                    }} catch (error) {{
                        alert('❌ Error: ' + error.message);
                    }}
                }}
                
                function refreshChannels() {{
                    fetch('/refresh-channels?uid={uid}', {{
                        method: 'POST'
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('✅ Channels refreshed! Reloading...');
                            window.location.reload();
                        }} else {{
                            alert('❌ Failed: ' + data.error);
                        }}
                    }})
                    .catch(error => {{
                        alert('❌ Error: ' + error.message);
                    }});
                }}
                
                async function logoutUser() {{
                    try {{
                        const response = await fetch('/logout?uid={uid}', {{
                            method: 'POST'
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            window.location.href = '/?uid={uid}';
                        }} else {{
                            alert('❌ Logout failed: ' + data.error);
                        }}
                    }} catch (error) {{
                        alert('❌ Error: ' + error.message);
                    }}
                }}
            </script>
        </body>
    </html>
    """)


@app.get("/auth")
async def auth_start(uid: str = Query(..., description="User ID from OMI")):
    """Start OAuth flow for Slack authentication."""
    redirect_uri = os.getenv("OAUTH_REDIRECT_URL", "http://localhost:8000/auth/callback")
    
    try:
        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)
        oauth_states[state] = uid
        
        # Get authorization URL
        auth_url = slack_client.get_authorization_url(redirect_uri, state)
        
        return RedirectResponse(url=auth_url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OAuth initialization failed: {str(e)}")


@app.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None)
):
    """Handle OAuth callback from Slack."""
    if not code or not state:
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>{get_mobile_css()}</style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-box" style="margin-top: 40px; padding: 40px 24px;">
                            <h2 style="font-size: 24px; margin-bottom: 12px;">❌ Authentication Failed</h2>
                            <p style="margin-bottom: 0;">Authorization code not received. Please try again.</p>
                        </div>
                    </div>
                </body>
            </html>
            """,
            status_code=400
        )
    
    # Verify state and get uid
    uid = oauth_states.get(state)
    if not uid:
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>{get_mobile_css()}</style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-box" style="margin-top: 40px; padding: 40px 24px;">
                            <h2 style="font-size: 24px; margin-bottom: 12px;">❌ Invalid State</h2>
                            <p style="margin-bottom: 0;">OAuth state mismatch. Please try again.</p>
                        </div>
                    </div>
                </body>
            </html>
            """,
            status_code=400
        )
    
    try:
        redirect_uri = os.getenv("OAUTH_REDIRECT_URL", "http://localhost:8000/auth/callback")
        
        # Exchange code for access token
        token_data = slack_client.exchange_code_for_token(code, redirect_uri)
        access_token = token_data.get("access_token")
        team_id = token_data.get("team_id")
        team_name = token_data.get("team_name")
        
        # Get workspace channels
        channels = slack_client.list_channels(access_token)
        
        # Save user data
        SimpleUserStorage.save_user(
            uid=uid,
            access_token=access_token,
            team_id=team_id,
            team_name=team_name,
            selected_channel=channels[0]["id"] if channels else None,
            available_channels=channels
        )
        
        # Clean up state
        if state in oauth_states:
            del oauth_states[state]
        
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <title>Connected Successfully!</title>
                    <style>
                        {get_mobile_css()}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="success-box" style="padding: 40px 24px;">
                            <div class="icon" style="font-size: 72px; animation: pulse 1.5s infinite;">🎉</div>
                            <h2 style="font-size: 28px; margin: 16px 0;">Successfully Connected!</h2>
                            <p style="font-size: 17px; margin: 12px 0;">
                                Your Slack workspace <strong>{team_name}</strong> is now linked
                            </p>
                            <p style="font-size: 16px; margin: 8px 0;">
                                Found <strong>{len(channels)}</strong> {('channel' if len(channels) == 1 else 'channels')}
                            </p>
                        </div>
                        
                        <a href="/?uid={uid}" class="btn btn-primary btn-block" style="font-size: 17px; padding: 16px; margin-top: 24px;">
                            Continue to Settings →
                        </a>
                        
                        <div class="card" style="margin-top: 20px; text-align: center;">
                            <h3 style="margin-bottom: 16px;">🎤 Ready to Go!</h3>
                            <p style="font-size: 16px; line-height: 1.8;">
                                You can now send Slack messages just by speaking to your OMI device.
                                <br><br>
                                Try saying:<br>
                                <strong style="font-size: 17px;">"Send message to general saying hello!"</strong>
                            </p>
                        </div>
                    </div>
                </body>
            </html>
            """
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>{get_mobile_css()}</style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-box" style="margin-top: 40px; padding: 40px 24px;">
                            <h2 style="font-size: 24px; margin-bottom: 12px;">❌ Authentication Error</h2>
                            <p style="margin-bottom: 16px;">Failed to complete authentication: {str(e)}</p>
                            <a href="/auth?uid={uid}" class="btn btn-primary">Try again</a>
                        </div>
                    </div>
                </body>
            </html>
            """,
            status_code=500
        )


@app.get("/setup-completed")
async def check_setup(uid: str = Query(..., description="User ID from OMI")):
    """Check if user has completed setup (authenticated with Slack)."""
    is_authenticated = SimpleUserStorage.is_authenticated(uid)
    
    return {
        "is_setup_completed": is_authenticated
    }


@app.post("/update-channel")
async def update_channel(
    uid: str = Query(...),
    channel: str = Query(...)
):
    """Update user's selected default channel."""
    try:
        success = SimpleUserStorage.update_channel_selection(uid, channel)
        if success:
            return {"success": True, "message": f"Default channel updated"}
        else:
            return {"success": False, "error": "User not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/refresh-channels")
async def refresh_channels(uid: str = Query(...)):
    """Refresh user's channel list from Slack."""
    try:
        user = SimpleUserStorage.get_user(uid)
        if not user or not user.get("access_token"):
            return {"success": False, "error": "User not authenticated"}
        
        # Fetch fresh channel list
        channels = slack_client.list_channels(user["access_token"])
        
        # Update storage
        SimpleUserStorage.save_user(
            uid=uid,
            access_token=user["access_token"],
            team_id=user.get("team_id"),
            team_name=user.get("team_name"),
            selected_channel=user.get("selected_channel"),
            available_channels=channels
        )
        
        return {"success": True, "channels_count": len(channels)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/logout")
async def logout(uid: str = Query(...)):
    """Logout user - clear all data and sessions."""
    try:
        from simple_storage import users, sessions, save_users, save_sessions
        
        # Remove user data
        if uid in users:
            del users[uid]
            save_users()
            print(f"🚪 Logged out user {uid[:10]}...", flush=True)
        
        # Remove any active sessions for this user
        sessions_to_remove = [sid for sid, sess in sessions.items() if sess.get("uid") == uid]
        for sid in sessions_to_remove:
            del sessions[sid]
        if sessions_to_remove:
            save_sessions()
            print(f"🧹 Cleared {len(sessions_to_remove)} sessions", flush=True)
        
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/webhook")
async def webhook(
    request: Request,
    uid: str = Query(..., description="User ID from OMI"),
    session_id: str = Query(None, description="Session ID from OMI (optional)")
):
    """
    Real-time transcript webhook endpoint.
    Collects 3 segments for message + channel detection.
    """
    # Use consistent session_id per user
    if not session_id:
        session_id = f"omi_session_{uid}"
    
    # Get user
    user = SimpleUserStorage.get_user(uid)
    
    if not user or not user.get("access_token"):
        return JSONResponse(
            content={
                "message": "User not authenticated. Please complete setup first.",
                "setup_required": True
            },
            status_code=401
        )
    
    # Parse payload from OMI
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    
    # Handle both formats
    segments = []
    if isinstance(payload, dict):
        segments = payload.get("segments", [])
        if not session_id and "session_id" in payload:
            session_id = payload["session_id"]
    elif isinstance(payload, list):
        segments = payload
    
    # Log received data
    print(f"📥 Received {len(segments) if segments else 0} segment(s) from OMI", flush=True)
    if segments:
        for i, seg in enumerate(segments[:3]):
            text = seg.get('text', 'NO TEXT') if isinstance(seg, dict) else str(seg)
            print(f"   Segment {i}: {text[:100]}", flush=True)
    
    if not segments or not isinstance(segments, list):
        return {"status": "ok"}
    
    # Ensure consistent session_id
    if not session_id:
        session_id = f"omi_session_{uid}"
    
    # Get or create session
    session = SimpleSessionStorage.get_or_create_session(session_id, uid)
    
    # Debug session state
    print(f"📊 Session state: mode={session.get('message_mode')}, count={session.get('segments_count', 0)}", flush=True)
    
    # Process segments
    response_message = await process_segments(session, segments, user)
    
    # Only send notifications for final message post
    if response_message and ("✅ Message sent" in response_message or "❌" in response_message):
        print(f"✉️  USER NOTIFICATION: {response_message}", flush=True)
        return {
            "message": response_message,
            "session_id": session_id,
            "processed_segments": len(segments)
        }
    
    # Silent response during collection
    print(f"🔇 Silent response: {response_message}", flush=True)
    return {"status": "ok"}


async def process_segments(
    session: dict,
    segments: List[Dict[str, Any]],
    user: dict
) -> str:
    """
    Collect up to 5 segments after trigger, or timeout after 5s gap.
    - Segment 1+: Contains trigger + message content
    - Maximum: 5 segments (processes immediately)
    - Timeout: If 5+ seconds gap after any segment, process what we have
    - No minimum segments required - even 1 segment is processed on timeout
    - AI extracts channel and message content
    
    For test interface: processes the entire text immediately.
    """
    # Extract text from segments
    segment_texts = [seg.get("text", "") for seg in segments]
    full_text = " ".join(segment_texts)
    
    session_id = session["session_id"]
    is_test_session = session_id.startswith("test_session")
    
    print(f"🔍 Received: '{full_text}'", flush=True)
    print(f"📊 Session mode: {session['message_mode']}, Count: {session.get('segments_count', 0)}/5", flush=True)
    
    # Check for trigger phrase (but only if not already recording)
    if message_detector.detect_trigger(full_text) and session["message_mode"] == "idle":
        message_content = message_detector.extract_message_content(full_text)
        
        print(f"🎤 TRIGGER! {'[TEST MODE] Processing immediately...' if is_test_session else 'Starting segment collection...'}", flush=True)
        print(f"   Content: '{message_content}'", flush=True)
        
        # TEST MODE: Process entire text immediately
        if is_test_session and len(message_content) > 10:
            print(f"🧪 Test mode: Processing full text immediately...", flush=True)
            
            # Fetch fresh channels from Slack (always up-to-date)
            print(f"🔄 Fetching fresh channel list from Slack...", flush=True)
            channels = slack_client.list_channels(user["access_token"])
            
            # Update cached channels for next time
            if channels:
                SimpleUserStorage.save_user(
                    uid=user["uid"],
                    access_token=user["access_token"],
                    team_id=user.get("team_id"),
                    team_name=user.get("team_name"),
                    selected_channel=user.get("selected_channel"),
                    available_channels=channels
                )
                print(f"✅ Refreshed {len(channels)} channels", flush=True)
            
            # AI extracts channel and message from full text
            channel_id, channel_name, message = await message_detector.ai_extract_message_and_channel(
                message_content, 
                channels
            )
            
            # If no channel identified, use default
            if not channel_id:
                channel_id = user.get("selected_channel")
                if channel_id:
                    # Find channel name
                    for ch in channels:
                        if ch["id"] == channel_id:
                            channel_name = ch["name"]
                            break
                    print(f"📌 Using default channel: #{channel_name}", flush=True)
                else:
                    SimpleSessionStorage.reset_session(session_id)
                    return "❌ No channel specified and no default channel set"
            
            if not message:
                SimpleSessionStorage.reset_session(session_id)
                return "❌ No message content found"
            
            print(f"📤 Sending to #{channel_name}: '{message}'", flush=True)
            
            result = await slack_client.send_message(
                access_token=user["access_token"],
                channel_id=channel_id,
                text=message
            )
            
            if result and result.get("success"):
                SimpleSessionStorage.reset_session(session_id)
                print(f"🎉 SUCCESS! Message sent to #{channel_name}", flush=True)
                return f"✅ Message sent to #{channel_name}: {message}"
            else:
                error = result.get("error", "Unknown") if result else "Failed"
                SimpleSessionStorage.reset_session(session_id)
                print(f"❌ FAILED: {error}", flush=True)
                return f"❌ Failed: {error}"
        
        # REAL MODE: Start collecting segments
        SimpleSessionStorage.update_session(
            session_id,
            message_mode="recording",
            accumulated_text=message_content or full_text,
            segments_count=1
        )
        
        return "collecting_1"
    
    # If in recording mode, collect more segments
    elif session["message_mode"] == "recording":
        accumulated = session.get("accumulated_text", "")
        segments_count = session.get("segments_count", 0)
        
        # Add this segment
        accumulated += " " + full_text
        segments_count += 1
        
        print(f"📝 Segment {segments_count}/5: '{full_text}'", flush=True)
        print(f"📚 Full accumulated: '{accumulated[:150]}...'", flush=True)
        
        # Update session with new segment
        SimpleSessionStorage.update_session(
            session_id,
            accumulated_text=accumulated,
            segments_count=segments_count
        )
        
        # Process ONLY if we hit max 5 segments (background task handles timeout)
        if segments_count >= 5:
            print(f"✅ Max segments reached ({segments_count})! Processing...", flush=True)
            
            # Mark as processing to prevent duplicates
            SimpleSessionStorage.update_session(
                session_id,
                message_mode="processing"
            )
            
            # Fetch fresh channels from Slack (always up-to-date)
            print(f"🔄 Fetching fresh channel list from Slack...", flush=True)
            channels = slack_client.list_channels(user["access_token"])
            
            # Update cached channels for next time
            if channels:
                SimpleUserStorage.save_user(
                    uid=user["uid"],
                    access_token=user["access_token"],
                    team_id=user.get("team_id"),
                    team_name=user.get("team_name"),
                    selected_channel=user.get("selected_channel"),
                    available_channels=channels
                )
                print(f"✅ Refreshed {len(channels)} channels", flush=True)
            
            # AI extracts channel and message
            channel_id, channel_name, message = await message_detector.ai_extract_message_and_channel(
                accumulated,
                channels
            )
            
            # If no channel identified, use default
            if not channel_id:
                channel_id = user.get("selected_channel")
                if channel_id:
                    # Find channel name
                    for ch in channels:
                        if ch["id"] == channel_id:
                            channel_name = ch["name"]
                            break
                    print(f"📌 Using default channel: #{channel_name}", flush=True)
                else:
                    SimpleSessionStorage.reset_session(session_id)
                    return "❌ No channel specified and no default channel set"
            
            if not message or len(message.strip()) < 3:
                SimpleSessionStorage.reset_session(session_id)
                print(f"⚠️  No valid message content", flush=True)
                return "❌ No valid message content"
            
            print(f"📤 Sending to #{channel_name}: '{message}'", flush=True)
            
            result = await slack_client.send_message(
                access_token=user["access_token"],
                channel_id=channel_id,
                text=message
            )
            
            if result and result.get("success"):
                SimpleSessionStorage.reset_session(session_id)
                print(f"🎉 SUCCESS! Message sent to #{channel_name}", flush=True)
                return f"✅ Message sent to #{channel_name}: {message}"
            else:
                error = result.get("error", "Unknown") if result else "Failed"
                SimpleSessionStorage.reset_session(session_id)
                print(f"❌ FAILED: {error}", flush=True)
                return f"❌ Failed: {error}"
        else:
            # Still collecting (not at max yet)
            # Session already updated above, just wait for more segments or timeout
            print(f"⏳ Collecting more segments ({segments_count}/5)... [Background monitor will handle timeout]", flush=True)
            return f"collecting_{segments_count}"
    
    # If already processing, ignore
    elif session["message_mode"] == "processing":
        print(f"⏳ Already processing message, ignoring this segment", flush=True)
        return "processing"
    
    # Passive listening
    return "listening"


@app.get("/test")
async def test_interface(uid: str = Query("test_user_123"), dev: str = Query(None)):
    """Development testing interface."""
    if not dev or dev != "true":
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Not Found</title>
                <style>{get_mobile_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="card" style="margin-top: 40px; padding: 40px 24px; text-align: center;">
                        <h1 style="font-size: 48px; margin-bottom: 16px;">404</h1>
                        <h2 style="border-bottom: none; padding-bottom: 0;">Page Not Found</h2>
                        <p style="margin-bottom: 24px;">The page you're looking for doesn't exist.</p>
                        <a href="/" class="btn btn-primary">Go to Homepage</a>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=404)
    
    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Slack Messages - Test Interface</title>
            <style>
                {get_mobile_css()}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header-success">
                    <h1>🧪 Test Interface</h1>
                    <p>Test Slack messaging without OMI device</p>
                </div>

                <div class="card">
                    <h2>Authentication</h2>
                    <div class="input-group">
                        <label>User ID (UID):</label>
                        <input type="text" id="uid" value="{uid}">
                    </div>
                    <button class="btn btn-primary" onclick="authenticate()">🔐 Authenticate Slack</button>
                    <button class="btn btn-secondary" onclick="checkAuth()">🔍 Check Auth Status</button>
                    <button class="btn btn-secondary" onclick="logoutUser()" style="border-color: #e01e5a; color: #e01e5a;">🚪 Logout</button>
                    <div id="authStatus" style="margin-top: 10px;"></div>
                </div>

                <div class="card">
                    <h2>Test Voice Commands</h2>
                    <div class="input-group">
                        <label>What would you say to OMI:</label>
                        <textarea id="voiceInput" rows="5" placeholder='Example: "Send Slack message to general saying hello team, hope everyone is doing great today!"'></textarea>
                    </div>
                    <button class="btn btn-primary" onclick="sendCommand()">🎤 Send Command</button>
                    <button class="btn btn-secondary" onclick="clearLogs()">🗑️ Clear Logs</button>
                    
                    <div id="status" class="status"></div>
                </div>

                <div class="card">
                    <h3>Quick Examples (Click to use)</h3>
                    <div class="example" onclick="useExample(this)">
                        Send Slack message to general saying hello team, great work on the project!
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Post Slack message in marketing that the new campaign is now live!
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Post in Slack to random saying just had an amazing idea about this
                    </div>
                </div>

                <div class="card">
                    <h2>Activity Log</h2>
                    <div id="log" class="log">
                        <div class="log-entry">
                            <span class="timestamp">Ready</span>
                            <span>Waiting for commands...</span>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                const sessionId = 'test_session_' + Date.now();
                
                function addLog(message) {{
                    const log = document.getElementById('log');
                    const entry = document.createElement('div');
                    entry.className = 'log-entry';
                    const time = new Date().toLocaleTimeString();
                    entry.innerHTML = `<span class="timestamp">[${{time}}]</span><span>${{message}}</span>`;
                    log.insertBefore(entry, log.firstChild);
                }}
                
                function setStatus(message, type = 'info') {{
                    const status = document.getElementById('status');
                    status.textContent = message;
                    status.className = 'status ' + type;
                    status.style.display = 'block';
                }}
                
                async function checkAuth() {{
                    const uid = document.getElementById('uid').value;
                    try {{
                        const response = await fetch(`/setup-completed?uid=${{uid}}`);
                        const data = await response.json();
                        
                        const authStatus = document.getElementById('authStatus');
                        if (data.is_setup_completed) {{
                            authStatus.innerHTML = '<div class="success-box">✅ Connected to Slack</div>';
                            addLog('✅ Authentication verified');
                        }} else {{
                            authStatus.innerHTML = '<div class="error-box">❌ Not connected</div>';
                            addLog('❌ Not authenticated');
                        }}
                    }} catch (error) {{
                        addLog('❌ Error: ' + error.message);
                    }}
                }}
                
                function authenticate() {{
                    const uid = document.getElementById('uid').value;
                    addLog('Opening Slack authentication...');
                    window.open(`/auth?uid=${{uid}}`, '_blank');
                    setTimeout(() => addLog('After authenticating, click "Check Auth Status"'), 1000);
                }}
                
                async function sendCommand() {{
                    const uid = document.getElementById('uid').value;
                    const voiceInput = document.getElementById('voiceInput').value;
                    
                    if (!uid || !voiceInput) {{
                        alert('Please enter both User ID and voice command');
                        return;
                    }}
                    
                    setStatus('🎤 Processing command...', 'recording');
                    addLog('📤 Sending: "' + voiceInput.substring(0, 100) + '..."');
                    
                    try {{
                        const segments = [{{
                            text: voiceInput,
                            speaker: "SPEAKER_00",
                            speakerId: 0,
                            is_user: true,
                            start: 0.0,
                            end: 5.0
                        }}];
                        
                        const response = await fetch(`/webhook?session_id=${{sessionId}}&uid=${{uid}}`, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(segments)
                        }});
                        
                        const data = await response.json();
                        
                        if (response.ok) {{
                            if (data.message && data.message.includes('✅')) {{
                                setStatus(data.message, 'success');
                                addLog('✅ ' + data.message);
                            }} else if (data.message && data.message.includes('❌')) {{
                                setStatus(data.message, 'error');
                                addLog('❌ ' + data.message);
                            }} else {{
                                setStatus('Processing...', 'recording');
                                addLog('📝 ' + (data.message || 'Processing...'));
                            }}
                        }} else {{
                            setStatus('❌ Error: ' + (data.message || 'Unknown error'), 'error');
                            addLog('❌ Error: ' + (data.message || 'Unknown error'));
                        }}
                    }} catch (error) {{
                        setStatus('❌ Network error', 'error');
                        addLog('❌ Network error: ' + error.message);
                    }}
                }}
                
                function useExample(element) {{
                    document.getElementById('voiceInput').value = element.textContent.trim();
                    addLog('📝 Example loaded');
                }}
                
                function clearLogs() {{
                    document.getElementById('log').innerHTML = '<div class="log-entry"><span class="timestamp">Cleared</span><span>Logs cleared</span></div>';
                    setStatus('');
                }}
                
                async function logoutUser() {{
                    const uid = document.getElementById('uid').value;
                    
                    try {{
                        addLog('Logging out...');
                        const response = await fetch(`/logout?uid=${{uid}}`, {{
                            method: 'POST'
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            addLog('✅ Logged out successfully');
                            setTimeout(() => checkAuth(), 500);
                        }} else {{
                            addLog('❌ Logout failed: ' + data.error);
                        }}
                    }} catch (error) {{
                        addLog('❌ Error: ' + error.message);
                    }}
                }}
                
                window.onload = () => checkAuth();
            </script>
        </body>
    </html>
    """)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "omi-slack-messages"}


# ============================================================================
# Chat Tools Endpoints for OMI App Store
# ============================================================================

@app.post("/api/send_message")
async def chat_tool_send_message(request: Request):
    """
    Chat Tool: Send a message to a Slack channel
    
    Expected payload:
    {
        "uid": "user_id",
        "app_id": "slack_app_id",
        "tool_name": "send_slack_message",
        "channel": "#general",
        "message": "Hello from Omi!"
    }
    """
    try:
        data = await request.json()
        
        # Validate required parameters
        if not data:
            return JSONResponse(
                content={'error': 'Missing request body'},
                status_code=400
            )
        
        uid = data.get('uid')
        channel = data.get('channel')
        message = data.get('message')
        
        if not uid:
            return JSONResponse(
                content={'error': 'Missing uid parameter'},
                status_code=400
            )
        if not channel:
            return JSONResponse(
                content={'error': 'Missing required parameter: channel'},
                status_code=400
            )
        if not message:
            return JSONResponse(
                content={'error': 'Missing required parameter: message'},
                status_code=400
            )
        
        # Get user's authentication token
        user = SimpleUserStorage.get_user(uid)
        if not user or not user.get("access_token"):
            return JSONResponse(
                content={'error': 'Slack not connected. Please connect your Slack account.'},
                status_code=401
            )
        
        access_token = user["access_token"]
        
        # Get channels to find channel ID
        channels = slack_client.list_channels(access_token)
        channel_id = None
        channel_name = channel
        
        # Try to find channel by name (handle # prefix)
        channel_search = channel.lstrip('#').lower()
        for ch in channels:
            if ch["name"].lower() == channel_search:
                channel_id = ch["id"]
                channel_name = ch["name"]
                break
        
        if not channel_id:
            return JSONResponse(
                content={'error': f'Channel "{channel}" not found. Please check the channel name.'},
                status_code=400
            )
        
        # Send message
        result = await slack_client.send_message(
            access_token=access_token,
            channel_id=channel_id,
            text=message
        )
        
        if result and result.get("success"):
            return JSONResponse(
                content={'result': f'Successfully sent message to #{channel_name}'}
            )
        else:
            error = result.get("error", "Unknown error") if result else "Failed to send message"
            return JSONResponse(
                content={'error': f'Failed to send message: {error}'},
                status_code=400
            )
            
    except Exception as e:
        print(f"❌ Error in send_message tool: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={'error': f'Internal server error: {str(e)}'},
            status_code=500
        )


@app.post("/api/search_messages")
async def chat_tool_search_messages(request: Request):
    """
    Chat Tool: Search for messages in Slack
    
    Expected payload:
    {
        "uid": "user_id",
        "app_id": "slack_app_id",
        "tool_name": "search_slack_messages",
        "query": "meeting notes",
        "channel": "#general"  # optional
    }
    """
    try:
        data = await request.json()
        
        uid = data.get('uid')
        query = data.get('query')
        channel = data.get('channel')
        
        if not uid:
            return JSONResponse(
                content={'error': 'Missing uid parameter'},
                status_code=400
            )
        if not query:
            return JSONResponse(
                content={'error': 'Missing required parameter: query'},
                status_code=400
            )
        
        # Get user's authentication token
        user = SimpleUserStorage.get_user(uid)
        if not user or not user.get("access_token"):
            return JSONResponse(
                content={'error': 'Slack not connected. Please connect your Slack account.'},
                status_code=401
            )
        
        access_token = user["access_token"]
        
        # Convert channel name to ID if needed
        channel_id = None
        channel_name = None
        if channel:
            channels = slack_client.list_channels(access_token)
            channel_search = channel.lstrip('#').lower()
            for ch in channels:
                if ch["name"].lower() == channel_search:
                    channel_id = ch["id"]
                    channel_name = ch["name"]
                    break
        
        # Search messages
        print(f"🔍 Searching messages - query: '{query}', channel: '{channel_name or channel}'", flush=True)
        result = await slack_client.search_messages(
            access_token=access_token,
            query=query,
            channel=channel_id if channel_id else (channel if channel else None)
        )
        
        if result and result.get("success"):
            matches = result.get("matches", [])
            source = result.get("source", "search")
            
            if not matches:
                query_display = f'in #{channel_name}' if channel_name else ''
                return JSONResponse(
                    content={'result': f'No messages found for "{query}" {query_display}'.strip()}
                )
            
            # Format results
            results = []
            # Show up to 10 results for channel history, 5 for search
            max_results = 10 if source == "channel_history" else 5
            
            for msg in matches[:max_results]:
                text = msg.get('text', '')
                # For channel history, messages have different structure
                if source == "channel_history":
                    # Channel history messages have 'user' field, not 'username'
                    user_id = msg.get('user', 'Unknown')
                    # Try to get username from user info if available
                    username = f"user_{user_id[:8]}" if user_id != 'Unknown' else 'Unknown'
                    # Format timestamp if available
                    ts = msg.get('ts', '')
                    results.append(f"- {text[:150]} (by @{username})")
                else:
                    # Search API format
                    channel_name_msg = msg.get('channel', {}).get('name', channel_name or 'unknown')
                    username = msg.get('username', 'Unknown')
                    text_truncated = text[:100] if len(text) > 100 else text
                    results.append(f"- {text_truncated} (by @{username} in #{channel_name_msg})")
            
            source_note = " (from today)" if source == "channel_history" else ""
            result_text = f'Found {len(matches)} message(s){source_note}:\n' + '\n'.join(results)
            
            if len(matches) > max_results:
                result_text += f'\n... and {len(matches) - max_results} more message(s)'
            
            return JSONResponse(
                content={'result': result_text}
            )
        else:
            error = result.get("error", "Unknown error") if result else "Failed to search messages"
            return JSONResponse(
                content={'error': f'Failed to search messages: {error}'},
                status_code=400
            )
            
    except Exception as e:
        print(f"❌ Error in search_messages tool: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={'error': f'Internal server error: {str(e)}'},
            status_code=500
        )


@app.post("/api/search_channels")
async def chat_tool_search_channels(request: Request):
    """
    Chat Tool: Search for Slack channels
    
    Expected payload:
    {
        "uid": "user_id",
        "app_id": "slack_app_id",
        "tool_name": "search_slack_channels",
        "query": "general"
    }
    """
    try:
        data = await request.json()
        
        uid = data.get('uid')
        query = data.get('query', '')  # Allow empty query to list all channels
        
        if not uid:
            return JSONResponse(
                content={'error': 'Missing uid parameter'},
                status_code=400
            )
        # Query is optional - if empty or "all", will return all channels
        
        # Get user's authentication token
        user = SimpleUserStorage.get_user(uid)
        if not user or not user.get("access_token"):
            return JSONResponse(
                content={'error': 'Slack not connected. Please connect your Slack account.'},
                status_code=401
            )
        
        access_token = user["access_token"]
        
        # Log the request
        print(f"🔍 Search channels request - uid: {uid[:10]}..., query: '{query}'", flush=True)
        
        # Search channels (empty query or "all" returns all channels)
        matching_channels = slack_client.search_channels(
            access_token=access_token,
            query=query or "all"
        )
        
        print(f"📊 Found {len(matching_channels)} matching channels", flush=True)
        
        # Log channel details for debugging
        if matching_channels:
            for ch in matching_channels[:5]:  # Log first 5
                print(f"   - #{ch['name']} ({'private' if ch.get('is_private') else 'public'}, {'member' if ch.get('is_member') else 'not member'})", flush=True)
        
        if not matching_channels:
            query_display = query if query else "all channels"
            return JSONResponse(
                content={'result': f'No channels found matching "{query_display}"'}
            )
        
        # Format results
        results = []
        # Show up to 20 channels (increased from 10)
        for channel in matching_channels[:20]:
            privacy = "🔒 Private" if channel.get('is_private') else "# Public"
            member_status = " (member)" if channel.get('is_member') else " (not a member)"
            results.append(f"- #{channel['name']} - {privacy}{member_status}")
        
        # If there are more channels, mention it
        total_count = len(matching_channels)
        if total_count > 20:
            result_text = f'Found {total_count} channel(s) (showing first 20):\n' + '\n'.join(results)
        else:
            result_text = f'Found {total_count} channel(s):\n' + '\n'.join(results)
        
        return JSONResponse(
            content={'result': result_text}
        )
            
    except Exception as e:
        print(f"❌ Error in search_channels tool: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={'error': f'Internal server error: {str(e)}'},
            status_code=500
        )


def get_mobile_css() -> str:
    """Returns Slack-inspired dark theme CSS styles."""
    return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            background: #1a1d21;
            color: #d1d2d3;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
            animation: fadeIn 0.5s ease-out;
        }
        
        .container {
            max-width: 650px;
            margin: 0 auto;
            animation: fadeIn 0.6s ease-out;
        }
        
        .icon {
            font-size: 64px;
            text-align: center;
            margin-bottom: 20px;
            animation: pulse 2s infinite;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.5));
        }
        
        h1 {
            color: #ffffff;
            font-size: 32px;
            font-weight: 700;
            text-align: center;
            margin-bottom: 12px;
        }
        
        h2 {
            color: #ffffff;
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 15px;
            border-bottom: 1px solid #2c2d30;
            padding-bottom: 10px;
        }
        
        h3 {
            color: #ffffff;
            font-size: 19px;
            font-weight: 700;
            margin-bottom: 12px;
        }
        
        p {
            color: #9ca0a5;
            text-align: center;
            margin-bottom: 24px;
            font-size: 16px;
        }
        
        .username {
            color: #1d9bd1;
            font-weight: 700;
            font-size: 18px;
        }
        
        .header-success {
            background: #232529;
            padding: 40px 24px;
            border-radius: 8px;
            margin-bottom: 24px;
            border: 1px solid #2c2d30;
        }
        
        .card {
            background: #232529;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 16px;
            border: 1px solid #2c2d30;
            transition: border-color 0.2s;
        }
        
        .card:hover {
            border-color: #1d9bd1;
        }
        
        .btn {
            display: inline-block;
            padding: 10px 20px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: 700;
            font-size: 15px;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease-in-out;
            margin: 8px 8px 8px 0;
            text-align: center;
            line-height: 20px;
        }
        
        .btn-primary {
            background: #007a5a;
            color: #ffffff;
        }
        
        .btn-primary:hover {
            background: #148567;
        }
        
        .btn-secondary {
            background: transparent;
            color: #d1d2d3;
            border: 1px solid #545454;
        }
        
        .btn-secondary:hover {
            background: #2c2d30;
        }
        
        .btn-block {
            display: block;
            width: 100%;
            text-align: center;
        }
        
        .repo-select {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #545454;
            border-radius: 4px;
            font-size: 15px;
            margin-bottom: 18px;
            font-family: inherit;
            background: #1a1d21;
            color: #d1d2d3;
            transition: all 0.2s;
            cursor: pointer;
        }
        
        .repo-select:focus {
            outline: none;
            border-color: #1d9bd1;
            box-shadow: 0 0 0 3px rgba(29, 155, 209, 0.3);
        }
        
        input[type="text"], textarea {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #545454;
            border-radius: 4px;
            font-size: 15px;
            font-family: inherit;
            background: #1a1d21;
            color: #d1d2d3;
            transition: all 0.2s;
        }
        
        input[type="text"]:focus, textarea:focus {
            outline: none;
            border-color: #1d9bd1;
            box-shadow: 0 0 0 3px rgba(29, 155, 209, 0.3);
        }
        
        textarea {
            resize: vertical;
            min-height: 100px;
        }
        
        .input-group {
            margin-bottom: 15px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 700;
            color: #d1d2d3;
            font-size: 15px;
        }
        
        .example {
            background: #1a1d21;
            padding: 16px 18px;
            border-radius: 6px;
            margin: 12px 0;
            font-size: 15px;
            cursor: pointer;
            border: 1px solid #2c2d30;
            color: #d1d2d3;
            transition: all 0.2s;
            line-height: 1.6;
        }
        
        .example:hover {
            border-color: #1d9bd1;
            background: #232529;
        }
        
        .steps {
            margin: 20px 0;
        }
        
        .step {
            display: flex;
            margin: 18px 0;
            align-items: flex-start;
            padding: 12px;
            border-radius: 6px;
            transition: background 0.2s;
        }
        
        .step:hover {
            background: #2c2d30;
        }
        
        .step-number {
            background: #007a5a;
            color: white;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            margin-right: 14px;
            flex-shrink: 0;
            font-size: 15px;
        }
        
        .step-content {
            flex: 1;
            padding-top: 4px;
            font-size: 15px;
            line-height: 1.6;
            color: #9ca0a5;
        }
        
        .step-content strong {
            color: #d1d2d3;
        }
        
        .success-box {
            background: rgba(0, 122, 90, 0.15);
            color: #2eb67d;
            padding: 24px;
            border-radius: 8px;
            margin: 18px 0;
            text-align: center;
            border: 1px solid #007a5a;
        }
        
        .error-box {
            background: rgba(224, 30, 90, 0.15);
            color: #e01e5a;
            padding: 18px;
            border-radius: 8px;
            margin: 14px 0;
            border: 1px solid #e01e5a;
        }
        
        .status {
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
            font-weight: 500;
            display: none;
            border: 1px solid;
        }
        
        .status.info {
            background: rgba(29, 155, 209, 0.15);
            color: #1d9bd1;
            border-color: #1d9bd1;
        }
        
        .status.recording {
            background: rgba(236, 178, 46, 0.15);
            color: #ecb22e;
            border-color: #ecb22e;
        }
        
        .status.success {
            background: rgba(0, 122, 90, 0.15);
            color: #2eb67d;
            border-color: #007a5a;
        }
        
        .status.error {
            background: rgba(224, 30, 90, 0.15);
            color: #e01e5a;
            border-color: #e01e5a;
        }
        
        ul, ol {
            margin-left: 20px;
        }
        
        li {
            margin: 8px 0;
            color: #9ca0a5;
        }
        
        strong {
            color: #d1d2d3;
            font-weight: 700;
        }
        
        .footer {
            text-align: center;
            color: #9ca0a5;
            margin-top: 40px;
            padding: 20px;
            font-size: 14px;
            border-top: 1px solid #2c2d30;
        }
        
        .footer strong {
            color: #1d9bd1;
        }
        
        .footer a {
            color: #1d9bd1;
            text-decoration: none;
        }
        
        .footer a:hover {
            text-decoration: underline;
        }
        
        ::-webkit-scrollbar {
            width: 12px;
            height: 12px;
        }
        
        ::-webkit-scrollbar-track {
            background: #1a1d21;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #545454;
            border-radius: 6px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #616061;
        }
        
        .log {
            background: #1a1d21;
            border: 1px solid #2c2d30;
            border-radius: 6px;
            padding: 15px;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            margin-top: 15px;
        }
        
        .log-entry {
            padding: 5px 0;
            border-bottom: 1px solid #2c2d30;
            color: #d1d2d3;
        }
        
        .timestamp {
            color: #9ca0a5;
            margin-right: 10px;
        }
        
        @media (max-width: 480px) {
            body {
                padding: 12px;
            }
            
            .card {
                padding: 18px;
            }
            
            h1 {
                font-size: 26px;
            }
            
            .btn {
                display: block;
                width: 100%;
                margin: 10px 0;
            }
            
            .icon {
                font-size: 52px;
            }
        }
    """


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", 8000))
    host = os.getenv("APP_HOST", "0.0.0.0")
    
    print("💬 OMI Slack Messages Integration", flush=True)
    print("=" * 50, flush=True)
    print("✅ Using file-based storage", flush=True)
    print(f"🚀 Starting on {host}:{port}", flush=True)
    print("=" * 50, flush=True)
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True
    )

