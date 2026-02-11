"""
Simple storage with file persistence - survives server restarts!
Stores user OAuth tokens, selected workspace/channels, and session state.
"""
from typing import Dict, Optional
from datetime import datetime
import json
import os

# Storage file paths - use /app/data for Railway persistence
STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.dirname(os.path.abspath(__file__)))
# Check if we're on Railway (has /app/data volume)
if os.path.exists("/app/data"):
    STORAGE_DIR = "/app/data"
    print(f"📁 Using persistent storage at: /app/data", flush=True)
else:
    STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"📁 Using local storage at: {STORAGE_DIR}", flush=True)

USERS_FILE = os.path.join(STORAGE_DIR, "users_data.json")
SESSIONS_FILE = os.path.join(STORAGE_DIR, "sessions_data.json")

# In-memory storage
users: Dict[str, dict] = {}
sessions: Dict[str, dict] = {}

# Load from file on startup
def load_storage():
    global users, sessions
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                print(f"✅ Loaded {len(users)} users from storage", flush=True)
    except Exception as e:
        print(f"⚠️  Could not load users: {e}", flush=True)
    
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r') as f:
                sessions = json.load(f)
                print(f"✅ Loaded {len(sessions)} sessions from storage", flush=True)
    except Exception as e:
        print(f"⚠️  Could not load sessions: {e}", flush=True)

def save_users():
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, default=str, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save users: {e}", flush=True)

def save_sessions():
    try:
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(sessions, f, default=str, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save sessions: {e}", flush=True)

# Load on module import
load_storage()


class SimpleUserStorage:
    """Store user OAuth tokens and Slack workspace preferences"""
    
    @staticmethod
    def save_user(
        uid: str,
        access_token: str,
        team_id: Optional[str] = None,
        team_name: Optional[str] = None,
        selected_channel: Optional[str] = None,
        available_channels: Optional[list] = None
    ):
        """Save or update user data"""
        if uid not in users:
            users[uid] = {
                "uid": uid,
                "created_at": datetime.utcnow().isoformat()
            }
        
        users[uid].update({
            "access_token": access_token,
            "updated_at": datetime.utcnow().isoformat()
        })
        
        if team_id:
            users[uid]["team_id"] = team_id
        if team_name:
            users[uid]["team_name"] = team_name
        if selected_channel:
            users[uid]["selected_channel"] = selected_channel
        if available_channels is not None:
            users[uid]["available_channels"] = available_channels
        
        save_users()  # Persist to file
        print(f"💾 Saved data for user {uid[:10]}...", flush=True)
    
    @staticmethod
    def update_channel_selection(uid: str, selected_channel: str):
        """Update user's selected default channel"""
        if uid in users:
            users[uid]["selected_channel"] = selected_channel
            users[uid]["updated_at"] = datetime.utcnow().isoformat()
            save_users()
            print(f"📝 Updated channel for {uid[:10]}... to {selected_channel}", flush=True)
            return True
        return False
    
    @staticmethod
    def get_user(uid: str) -> Optional[dict]:
        """Get user by uid"""
        return users.get(uid)
    
    @staticmethod
    def is_authenticated(uid: str) -> bool:
        """Check if user is authenticated"""
        user = users.get(uid)
        return user is not None and user.get("access_token") is not None
    
    @staticmethod
    def has_selected_channel(uid: str) -> bool:
        """Check if user has selected a default channel"""
        user = users.get(uid)
        return user is not None and user.get("selected_channel") is not None


class SimpleSessionStorage:
    """Store session state in memory"""
    
    @staticmethod
    def get_or_create_session(session_id: str, uid: str) -> dict:
        """Get or create a session"""
        if session_id not in sessions:
            sessions[session_id] = {
                "session_id": session_id,
                "uid": uid,
                "message_mode": "idle",  # idle, recording, processing
                "segments_count": 0,
                "accumulated_text": "",
                "target_channel": None,
                "created_at": datetime.utcnow().isoformat()
            }
            print(f"🆕 Created new session: {session_id}", flush=True)
        return sessions[session_id]
    
    @staticmethod
    def update_session(session_id: str, **kwargs):
        """Update session fields"""
        if session_id in sessions:
            # Always update the last activity timestamp
            kwargs["last_segment_at"] = datetime.utcnow().isoformat()
            sessions[session_id].update(kwargs)
            print(f"💾 Updated session {session_id}: {kwargs}", flush=True)
        else:
            print(f"⚠️  Session {session_id} not found for update!", flush=True)
    
    @staticmethod
    def get_session_idle_time(session_id: str) -> Optional[float]:
        """Get seconds since last segment. Returns None if session doesn't exist."""
        if session_id not in sessions:
            return None
        
        last_segment = sessions[session_id].get("last_segment_at")
        if not last_segment:
            return None
        
        try:
            last_time = datetime.fromisoformat(last_segment)
            idle_seconds = (datetime.utcnow() - last_time).total_seconds()
            return idle_seconds
        except Exception:
            return None
    
    @staticmethod
    def reset_session(session_id: str):
        """Reset session to idle state"""
        if session_id in sessions:
            sessions[session_id].update({
                "message_mode": "idle",
                "segments_count": 0,
                "accumulated_text": "",
                "target_channel": None
            })
            print(f"🔄 Reset session {session_id}", flush=True)

