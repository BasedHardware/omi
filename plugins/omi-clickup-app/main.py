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
from clickup_client import ClickUpClient
from task_detector import TaskDetector
from omi_notifications import notify_task_created, notify_task_failed

load_dotenv()

# Initialize services
clickup_client = ClickUpClient()
task_detector = TaskDetector()

app = FastAPI(
    title="OMI ClickUp Integration",
    description="Voice-activated ClickUp task creation via OMI",
    version="1.0.0"
)

# Store OAuth states temporarily (in production, use Redis or similar)
oauth_states = {}

# Background task for timeout monitoring
background_task = None


async def monitor_session_timeouts():
    """Background task that monitors sessions and processes them if idle for 5+ seconds."""
    print("🕐 Timeout monitor started", flush=True)
    
    while True:
        try:
            await asyncio.sleep(1)  # Check every second
            
            from simple_storage import sessions
            
            # Check all active recording sessions
            for session_id, session in list(sessions.items()):
                if session.get("task_mode") != "recording":
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
                            task_mode="processing"
                        )
                        
                        # Process the task
                        try:
                            # Fetch fresh lists and members
                            lists = user.get("available_lists", [])
                            members = user.get("available_members", [])
                            
                            # AI extracts task details
                            user_timezone = user.get("timezone", "UTC")
                            list_id, list_name, task_name, description, priority, due_date, assignee_ids = await task_detector.ai_extract_task_details(
                                accumulated,
                                lists,
                                members,
                                user_timezone
                            )
                            
                            # If no list, use default
                            if not list_id:
                                list_id = user.get("selected_list")
                                if list_id:
                                    for lst in lists:
                                        if lst["id"] == list_id:
                                            list_name = lst["name"]
                                            break
                            
                            if list_id and task_name and len(task_name.strip()) >= 3:
                                print(f"⏰ Creating timeout task in {list_name}", flush=True)
                                
                                result = await clickup_client.create_task(
                                    access_token=user["access_token"],
                                    list_id=list_id,
                                    name=task_name,
                                    description=description,
                                    priority=priority,
                                    due_date=due_date,
                                    timezone=user_timezone,
                                    assignees=assignee_ids
                                )
                                
                                if result and result.get("success"):
                                    print(f"⏰ SUCCESS! Task created in {list_name}", flush=True)
                                    # Send notification to user
                                    await notify_task_created(uid, task_name, list_name, due_date)
                                else:
                                    error_msg = result.get('error') if result else 'Unknown'
                                    print(f"⏰ FAILED: {error_msg}", flush=True)
                                    # Send failure notification
                                    await notify_task_failed(uid, error_msg)
                            else:
                                print(f"⏰ Insufficient content to create task", flush=True)
                            
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
    """Root endpoint - Homepage with list selection."""
    if not uid:
        return {
            "app": "OMI ClickUp Integration",
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
                    <div class="icon">✅→📋</div>
                    <h1>Voice to ClickUp Tasks</h1>
                    <p style="font-size: 18px;">Create ClickUp tasks with your voice through OMI</p>
                    
                    <a href="{auth_url}" class="btn btn-primary btn-block" style="font-size: 17px; padding: 16px;">
                        🔐 Connect ClickUp Workspace
                    </a>
                    
                    <div class="card">
                        <h3>✨ How It Works</h3>
                        <div class="steps">
                            <div class="step">
                                <div class="step-number">1</div>
                                <div class="step-content">
                                    <strong>Connect</strong> your ClickUp workspace securely
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">2</div>
                                <div class="step-content">
                                    <strong>Select</strong> your default list (optional)
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">3</div>
                                <div class="step-content">
                                    <strong>Speak</strong> your task naturally
                                </div>
                            </div>
                            <div class="step">
                                <div class="step-number">4</div>
                                <div class="step-content">
                                    <strong>Done!</strong> Task created in ClickUp instantly
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>🎯 Example Commands</h3>
                        <div class="example">
                            "Create ClickUp task fix login bug by tomorrow assign to John"
                        </div>
                        <div class="example">
                            "Add ClickUp task update docs by Friday 5pm for Sarah and Mike"
                        </div>
                        <div class="example">
                            "Create ClickUp task urgent code review in 2 hours assign to team"
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>Powered by <strong>Omi</strong> × <strong>AI</strong></p>
                        <p style="font-size: 13px; margin-top: 8px;">Voice-first task management</p>
                    </div>
                </div>
            </body>
        </html>
        """)
    
    # Authenticated - show list selection page
    lists = user.get("available_lists", [])
    selected_list = user.get("selected_list", "")
    team_name = user.get("team_name", "Unknown")
    user_timezone = user.get("timezone", "UTC")
    
    list_options = '<option value="">Select a list...</option>'
    for lst in lists:
        selected_attr = 'selected' if lst['id'] == selected_list else ''
        space_name = lst.get('space_name', '')
        display_name = f"{lst['name']}" + (f" ({space_name})" if space_name else "")
        list_options += f'<option value="{lst["id"]}" {selected_attr}>{display_name}</option>'
    
    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>ClickUp Tasks - Settings</title>
            <style>
                {get_mobile_css()}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card" style="margin-top: 20px;">
                    <h2>✅ ClickUp Settings</h2>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 8px; color: #8b949e;">
                        Connected to <span class="username">{team_name}</span>
                    </p>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 16px;">
                        Default list (optional - you can specify list in voice command):
                    </p>
                    
                    <select id="listSelect" class="repo-select">
                        {list_options if list_options else '<option>No lists found</option>'}
                    </select>
                    
                    <button class="btn btn-primary btn-block" onclick="updateList()">
                        💾 Save Default List
                    </button>
                    <button type="button" class="btn btn-secondary btn-block" onclick="refreshLists()">
                        🔄 Refresh Lists
                    </button>
                </div>
                
                <div class="card">
                    <h3 style="font-size: 18px;">🌍 Timezone Settings</h3>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 16px; color: #9ca0a5;">
                        Set your timezone for accurate due date/time parsing:
                    </p>
                    <p style="text-align: left; font-size: 14px; margin-bottom: 8px; color: #8b949e;">
                        Current: <span class="username">{user_timezone}</span>
                    </p>
                    
                    <select id="timezoneSelect" class="repo-select">
                        <option value="America/New_York" {'selected' if user_timezone == 'America/New_York' else ''}>🇺🇸 Eastern (New York)</option>
                        <option value="America/Chicago" {'selected' if user_timezone == 'America/Chicago' else ''}>🇺🇸 Central (Chicago)</option>
                        <option value="America/Denver" {'selected' if user_timezone == 'America/Denver' else ''}>🇺🇸 Mountain (Denver)</option>
                        <option value="America/Los_Angeles" {'selected' if user_timezone == 'America/Los_Angeles' else ''}>🇺🇸 Pacific (Los Angeles)</option>
                        <option value="Europe/London" {'selected' if user_timezone == 'Europe/London' else ''}>🇬🇧 London (GMT/BST)</option>
                        <option value="Europe/Paris" {'selected' if user_timezone == 'Europe/Paris' else ''}>🇪🇺 Paris (CET/CEST)</option>
                        <option value="Europe/Berlin" {'selected' if user_timezone == 'Europe/Berlin' else ''}>🇩🇪 Berlin (CET/CEST)</option>
                        <option value="Asia/Tokyo" {'selected' if user_timezone == 'Asia/Tokyo' else ''}>🇯🇵 Tokyo (JST)</option>
                        <option value="Asia/Shanghai" {'selected' if user_timezone == 'Asia/Shanghai' else ''}>🇨🇳 Shanghai (CST)</option>
                        <option value="Asia/Dubai" {'selected' if user_timezone == 'Asia/Dubai' else ''}>🇦🇪 Dubai (GST)</option>
                        <option value="Asia/Kolkata" {'selected' if user_timezone == 'Asia/Kolkata' else ''}>🇮🇳 India (IST)</option>
                        <option value="Australia/Sydney" {'selected' if user_timezone == 'Australia/Sydney' else ''}>🇦🇺 Sydney (AEDT/AEST)</option>
                        <option value="UTC" {'selected' if user_timezone == 'UTC' else ''}>🌐 UTC (Universal)</option>
                    </select>
                    
                    <button class="btn btn-primary btn-block" onclick="updateTimezone()">
                        🌍 Save Timezone
                    </button>
                </div>
                
                <div class="card">
                    <button type="button" class="btn btn-secondary btn-block" onclick="logoutUser()" style="border-color: #7B68EE; color: #7B68EE;">
                        🚪 Logout & Clear Data
                    </button>
                </div>
                
                <div class="card" style="background: rgba(123, 104, 238, 0.05); border-color: #7B68EE;">
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
                                Say <strong>"Create ClickUp task"</strong> or <strong>"Add ClickUp task"</strong>
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">2</div>
                            <div class="step-content">
                                Mention the task name and optionally the list - AI handles the rest
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">3</div>
                            <div class="step-content">
                                Task created in ClickUp instantly!
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h3>💡 Pro Tips</h3>
                    <ul style="list-style: none; padding: 0;">
                        <li style="padding: 8px 0;">
                            🎯 <strong>Specify list</strong> - "in bug tracker" or "to tasks list"
                        </li>
                        <li style="padding: 8px 0;">
                            👥 <strong>Assign people</strong> - "assign to John" or "for Sarah and Mike"
                        </li>
                        <li style="padding: 8px 0;">
                            📅 <strong>Set due date</strong> - "by tomorrow 5pm" or "in 2 hours"
                        </li>
                        <li style="padding: 8px 0;">
                            ⚡ <strong>Set priority</strong> - Say "urgent" or "high priority"
                        </li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>Powered by <strong>Omi</strong> × <strong>AI</strong></p>
                    <p style="font-size: 13px; margin-top: 8px;">Voice-first ClickUp integration</p>
                </div>
            </div>
            
            <script>
                async function updateList() {{
                    const select = document.getElementById('listSelect');
                    const list = select.value;
                    
                    try {{
                        const response = await fetch('/update-list?uid={uid}&list=' + encodeURIComponent(list), {{
                            method: 'POST'
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            alert('✅ Default list updated!');
                        }} else {{
                            alert('❌ Failed to update: ' + data.error);
                        }}
                    }} catch (error) {{
                        alert('❌ Error: ' + error.message);
                    }}
                }}
                
                function refreshLists() {{
                    fetch('/refresh-lists?uid={uid}', {{
                        method: 'POST'
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('✅ Lists refreshed! Reloading...');
                            window.location.reload();
                        }} else {{
                            alert('❌ Failed: ' + data.error);
                        }}
                    }})
                    .catch(error => {{
                        alert('❌ Error: ' + error.message);
                    }});
                }}
                
                async function updateTimezone() {{
                    const select = document.getElementById('timezoneSelect');
                    const timezone = select.value;
                    
                    try {{
                        const response = await fetch('/update-timezone?uid={uid}&timezone=' + encodeURIComponent(timezone), {{
                            method: 'POST'
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            alert('✅ Timezone updated to ' + timezone + '!');
                            window.location.reload();
                        }} else {{
                            alert('❌ Failed to update: ' + data.error);
                        }}
                    }} catch (error) {{
                        alert('❌ Error: ' + error.message);
                    }}
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
    """Start OAuth flow for ClickUp authentication."""
    redirect_uri = os.getenv("OAUTH_REDIRECT_URL", "http://localhost:8000/auth/callback")
    
    try:
        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)
        oauth_states[state] = uid
        
        # Get authorization URL
        auth_url = clickup_client.get_authorization_url(redirect_uri, state)
        
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
    """Handle OAuth callback from ClickUp."""
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
        # Exchange code for access token
        token_data = clickup_client.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        
        # Get user info
        user_info = clickup_client.get_authorized_user(access_token)
        
        # Get workspaces
        workspaces = clickup_client.get_workspaces(access_token)
        
        # Get first workspace's lists and members
        lists = []
        members = []
        team_id = None
        team_name = "ClickUp"
        
        if workspaces:
            team_id = workspaces[0]["id"]
            team_name = workspaces[0]["name"]
            lists = clickup_client.get_all_lists(access_token, team_id)
            members = clickup_client.get_workspace_members(access_token, team_id)
        
        # Save user data (default to America/Los_Angeles timezone)
        SimpleUserStorage.save_user(
            uid=uid,
            access_token=access_token,
            team_id=team_id,
            team_name=team_name,
            selected_list=lists[0]["id"] if lists else None,
            available_workspaces=workspaces,
            available_lists=lists,
            available_members=members,
            timezone="America/Los_Angeles"  # Default timezone
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
                                Your ClickUp workspace <strong>{team_name}</strong> is now linked
                            </p>
                            <p style="font-size: 16px; margin: 8px 0;">
                                Found <strong>{len(lists)}</strong> {('list' if len(lists) == 1 else 'lists')} and <strong>{len(members)}</strong> {('member' if len(members) == 1 else 'members')}
                            </p>
                        </div>
                        
                        <a href="/?uid={uid}" class="btn btn-primary btn-block" style="font-size: 17px; padding: 16px; margin-top: 24px;">
                            Continue to Settings →
                        </a>
                        
                        <div class="card" style="margin-top: 20px; text-align: center;">
                            <h3 style="margin-bottom: 16px;">🎤 Ready to Go!</h3>
                            <p style="font-size: 16px; line-height: 1.8;">
                                You can now create ClickUp tasks just by speaking to your OMI device.
                                <br><br>
                                Try saying:<br>
                                <strong style="font-size: 17px;">"Create ClickUp task fix the login bug"</strong>
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
    """Check if user has completed setup (authenticated with ClickUp)."""
    is_authenticated = SimpleUserStorage.is_authenticated(uid)
    
    return {
        "is_setup_completed": is_authenticated
    }


@app.post("/update-list")
async def update_list(
    uid: str = Query(...),
    list: str = Query(...)
):
    """Update user's selected default list."""
    try:
        success = SimpleUserStorage.update_list_selection(uid, list)
        if success:
            return {"success": True, "message": f"Default list updated"}
        else:
            return {"success": False, "error": "User not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/update-timezone")
async def update_timezone(
    uid: str = Query(...),
    timezone: str = Query(...)
):
    """Update user's timezone preference."""
    try:
        success = SimpleUserStorage.update_timezone(uid, timezone)
        if success:
            return {"success": True, "message": f"Timezone updated to {timezone}"}
        else:
            return {"success": False, "error": "User not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/refresh-lists")
async def refresh_lists(uid: str = Query(...)):
    """Refresh user's list from ClickUp."""
    try:
        user = SimpleUserStorage.get_user(uid)
        if not user or not user.get("access_token"):
            return {"success": False, "error": "User not authenticated"}
        
        # Get workspaces
        workspaces = clickup_client.get_workspaces(user["access_token"])
        
        # Get lists and members from first workspace
        lists = []
        members = []
        if workspaces and user.get("team_id"):
            lists = clickup_client.get_all_lists(user["access_token"], user["team_id"])
            members = clickup_client.get_workspace_members(user["access_token"], user["team_id"])
        
        # Update storage
        SimpleUserStorage.save_user(
            uid=uid,
            access_token=user["access_token"],
            team_id=user.get("team_id"),
            team_name=user.get("team_name"),
            selected_list=user.get("selected_list"),
            available_workspaces=workspaces,
            available_lists=lists,
            available_members=members
        )
        
        return {"success": True, "lists_count": len(lists)}
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
    Collects segments for task details extraction.
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
    print(f"📊 Session state: mode={session.get('task_mode')}, count={session.get('segments_count', 0)}", flush=True)
    
    # Process segments
    response_message = await process_segments(session, segments, user)
    
    # Only send notifications for final task creation
    if response_message and ("✅ Task created" in response_message or "❌" in response_message):
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
    AI extracts task name, description, list, and priority.
    """
    # Extract text from segments
    segment_texts = [seg.get("text", "") for seg in segments]
    full_text = " ".join(segment_texts)
    
    session_id = session["session_id"]
    is_test_session = session_id.startswith("test_session")
    
    print(f"🔍 Received: '{full_text}'", flush=True)
    print(f"📊 Session mode: {session['task_mode']}, Count: {session.get('segments_count', 0)}/5", flush=True)
    
    # Check for trigger phrase (but only if not already recording)
    if task_detector.detect_trigger(full_text) and session["task_mode"] == "idle":
        task_content = task_detector.extract_task_content(full_text)
        
        print(f"🎤 TRIGGER! {'[TEST MODE] Processing immediately...' if is_test_session else 'Starting segment collection...'}", flush=True)
        print(f"   Content: '{task_content}'", flush=True)
        
        # TEST MODE: Process entire text immediately
        if is_test_session and len(task_content) > 5:
            print(f"🧪 Test mode: Processing full text immediately...", flush=True)
            
            # Fetch fresh lists and members
            lists = user.get("available_lists", [])
            members = user.get("available_members", [])
            
            # AI extracts task details
            user_timezone = user.get("timezone", "UTC")
            list_id, list_name, task_name, description, priority, due_date, assignee_ids = await task_detector.ai_extract_task_details(
                task_content, 
                lists,
                members,
                user_timezone
            )
            
            # If no list identified, use default
            if not list_id:
                list_id = user.get("selected_list")
                if list_id:
                    # Find list name
                    for lst in lists:
                        if lst["id"] == list_id:
                            list_name = lst["name"]
                            break
                    print(f"📌 Using default list: {list_name}", flush=True)
                else:
                    SimpleSessionStorage.reset_session(session_id)
                    return "❌ No list specified and no default list set"
            
            if not task_name or len(task_name.strip()) < 3:
                    SimpleSessionStorage.reset_session(session_id)
                    return "❌ No task name found"
            
            print(f"📤 Creating task '{task_name}' in {list_name}", flush=True)
            
            result = await clickup_client.create_task(
                access_token=user["access_token"],
                list_id=list_id,
                name=task_name,
                description=description,
                priority=priority,
                due_date=due_date,
                timezone=user_timezone,
                assignees=assignee_ids
            )
            
            if result and result.get("success"):
                SimpleSessionStorage.reset_session(session_id)
                print(f"🎉 SUCCESS! Task created in {list_name}", flush=True)
                # Send notification to user
                uid = user.get("uid")
                if uid:
                    await notify_task_created(uid, task_name, list_name, due_date)
                return f"✅ Task created in {list_name}: {task_name}"
            else:
                error = result.get("error", "Unknown") if result else "Failed"
                SimpleSessionStorage.reset_session(session_id)
                print(f"❌ FAILED: {error}", flush=True)
                # Send failure notification
                uid = user.get("uid")
                if uid:
                    await notify_task_failed(uid, error)
                return f"❌ Failed: {error}"
        
        # REAL MODE: Start collecting segments
        SimpleSessionStorage.update_session(
            session_id,
            task_mode="recording",
            accumulated_text=task_content or full_text,
            segments_count=1
        )
        
        return "collecting_1"
    
    # If in recording mode, collect more segments
    elif session["task_mode"] == "recording":
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
                task_mode="processing"
            )
            
            # Fetch fresh lists and members
            lists = user.get("available_lists", [])
            members = user.get("available_members", [])
            
            # AI extracts task details
            user_timezone = user.get("timezone", "UTC")
            list_id, list_name, task_name, description, priority, due_date, assignee_ids = await task_detector.ai_extract_task_details(
                accumulated,
                lists,
                members,
                user_timezone
            )
            
            # If no list identified, use default
            if not list_id:
                list_id = user.get("selected_list")
                if list_id:
                    for lst in lists:
                        if lst["id"] == list_id:
                            list_name = lst["name"]
                            break
                    print(f"📌 Using default list: {list_name}", flush=True)
                else:
                    SimpleSessionStorage.reset_session(session_id)
                    return "❌ No list specified and no default list set"
            
            if not task_name or len(task_name.strip()) < 3:
                SimpleSessionStorage.reset_session(session_id)
                print(f"⚠️  No valid task name", flush=True)
                return "❌ No valid task name"
            
            print(f"📤 Creating task '{task_name}' in {list_name}", flush=True)
            
            result = await clickup_client.create_task(
                access_token=user["access_token"],
                list_id=list_id,
                name=task_name,
                description=description,
                priority=priority,
                due_date=due_date,
                timezone=user_timezone,
                assignees=assignee_ids
            )
            
            if result and result.get("success"):
                SimpleSessionStorage.reset_session(session_id)
                print(f"🎉 SUCCESS! Task created in {list_name}", flush=True)
                # Send notification to user
                uid = user.get("uid")
                if uid:
                    await notify_task_created(uid, task_name, list_name, due_date)
                return f"✅ Task created in {list_name}: {task_name}"
            else:
                error = result.get("error", "Unknown") if result else "Failed"
                SimpleSessionStorage.reset_session(session_id)
                print(f"❌ FAILED: {error}", flush=True)
                # Send failure notification
                uid = user.get("uid")
                if uid:
                    await notify_task_failed(uid, error)
                return f"❌ Failed: {error}"
        else:
            # Still collecting (not at max yet)
            print(f"⏳ Collecting more segments ({segments_count}/5)... [Background monitor will handle timeout]", flush=True)
            return f"collecting_{segments_count}"
    
    # If already processing, ignore
    elif session["task_mode"] == "processing":
        print(f"⏳ Already processing task, ignoring this segment", flush=True)
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
            <title>ClickUp Tasks - Test Interface</title>
            <style>
                {get_mobile_css()}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header-success">
                    <h1>🧪 Test Interface</h1>
                    <p>Test ClickUp task creation without OMI device</p>
                </div>

                <div class="card">
                    <h2>Authentication</h2>
                    <div class="input-group">
                        <label>User ID (UID):</label>
                        <input type="text" id="uid" value="{uid}">
                    </div>
                    <button class="btn btn-primary" onclick="authenticate()">🔐 Authenticate ClickUp</button>
                    <button class="btn btn-secondary" onclick="checkAuth()">🔍 Check Auth Status</button>
                    <button class="btn btn-secondary" onclick="logoutUser()" style="border-color: #7B68EE; color: #7B68EE;">🚪 Logout</button>
                    <div id="authStatus" style="margin-top: 10px;"></div>
                </div>

                <div class="card">
                    <h2>Test Voice Commands</h2>
                    <div class="input-group">
                        <label>What would you say to OMI:</label>
                        <textarea id="voiceInput" rows="5" placeholder='Example: "Create ClickUp task fix login bug in bug tracker high priority"'></textarea>
                    </div>
                    <button class="btn btn-primary" onclick="sendCommand()">🎤 Send Command</button>
                    <button class="btn btn-secondary" onclick="clearLogs()">🗑️ Clear Logs</button>
                    
                    <div id="status" class="status"></div>
                </div>

                <div class="card">
                    <h3>Quick Examples (Click to use)</h3>
                    <div class="example" onclick="useExample(this)">
                        Create ClickUp task fix the login page bug in bug tracker by tomorrow
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Add ClickUp task called update documentation for API endpoints by Friday 5pm
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Create ClickUp task review design mockups urgent priority in 2 hours
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Add ClickUp task team meeting next Monday at 10am high priority
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
                            authStatus.innerHTML = '<div class="success-box">✅ Connected to ClickUp</div>';
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
                    addLog('Opening ClickUp authentication...');
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
    return {"status": "healthy", "service": "omi-clickup-tasks"}


def get_mobile_css() -> str:
    """Returns ClickUp-inspired purple theme CSS styles."""
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
            color: #7B68EE;
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
            border-color: #7B68EE;
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
            background: #7B68EE;
            color: #ffffff;
        }
        
        .btn-primary:hover {
            background: #9F8FEF;
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
            border-color: #7B68EE;
            box-shadow: 0 0 0 3px rgba(123, 104, 238, 0.3);
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
            border-color: #7B68EE;
            box-shadow: 0 0 0 3px rgba(123, 104, 238, 0.3);
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
            border-color: #7B68EE;
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
            background: #7B68EE;
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
            background: rgba(123, 104, 238, 0.15);
            color: #9F8FEF;
            padding: 24px;
            border-radius: 8px;
            margin: 18px 0;
            text-align: center;
            border: 1px solid #7B68EE;
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
            background: rgba(123, 104, 238, 0.15);
            color: #9F8FEF;
            border-color: #7B68EE;
        }
        
        .status.recording {
            background: rgba(236, 178, 46, 0.15);
            color: #ecb22e;
            border-color: #ecb22e;
        }
        
        .status.success {
            background: rgba(123, 104, 238, 0.15);
            color: #9F8FEF;
            border-color: #7B68EE;
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
            color: #7B68EE;
        }
        
        .footer a {
            color: #7B68EE;
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
    
    print("✅ OMI ClickUp Tasks Integration", flush=True)
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

