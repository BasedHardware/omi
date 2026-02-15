"""
Simple storage with file persistence - survives server restarts!
Note: For production, use a proper database
"""
from typing import Dict, Optional
from datetime import datetime, timedelta
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
oauth_states: Dict[str, dict] = {}  # Store OAuth state and code_verifier

# Load from file on startup
def load_storage():
    global users, sessions
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                print(f"✅ Loaded {len(users)} users from storage")
    except Exception as e:
        print(f"⚠️  Could not load users: {e}")
    
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r') as f:
                sessions = json.load(f)
                print(f"✅ Loaded {len(sessions)} sessions from storage")
    except Exception as e:
        print(f"⚠️  Could not load sessions: {e}")

def save_users():
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, default=str)
    except Exception as e:
        print(f"⚠️  Could not save users: {e}")

def save_sessions():
    try:
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(sessions, f, default=str)
    except Exception as e:
        print(f"⚠️  Could not save sessions: {e}")

# Load on module import
load_storage()


class SimpleUserStorage:
    """Store user OAuth tokens in memory"""
    
    @staticmethod
    def save_user(uid: str, access_token: str, refresh_token: Optional[str] = None, expires_in: int = 7200):
        """Save user tokens with expiration time"""
        users[uid] = {
            "uid": uid,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }
        save_users()  # Persist to file
        print(f"💾 Saved tokens for user {uid[:10]}... (expires in {expires_in/3600:.1f} hours)")
    
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
    def is_token_expired(uid: str) -> bool:
        """Check if user's token is expired"""
        user = users.get(uid)
        if not user or not user.get("expires_at"):
            return True
        
        try:
            expires_at = datetime.fromisoformat(user["expires_at"])
            # Consider expired if less than 5 minutes remaining
            return datetime.utcnow() >= (expires_at - timedelta(minutes=5))
        except:
            return True


class SimpleSessionStorage:
    """Store session state in memory"""
    
    @staticmethod
    def get_or_create_session(session_id: str, uid: str) -> dict:
        """Get or create a session"""
        if session_id not in sessions:
            sessions[session_id] = {
                "session_id": session_id,
                "uid": uid,
                "transcript": "",
                "tweet_mode": "idle",  # idle, recording, posted
                "tweet_content": "",
                "segments_count": 0,
                "last_segment_time": None,
                "accumulated_text": "",
                "created_at": datetime.utcnow().isoformat()
            }
            print(f"🆕 Created new session: {session_id}", flush=True)
        return sessions[session_id]
    
    @staticmethod
    def update_session(session_id: str, **kwargs):
        """Update session fields"""
        if session_id in sessions:
            sessions[session_id].update(kwargs)
            print(f"💾 Updated session {session_id}: {kwargs}", flush=True)
        else:
            print(f"⚠️  Session {session_id} not found for update!", flush=True)
    
    @staticmethod
    def reset_session(session_id: str):
        """Reset session to idle state"""
        if session_id in sessions:
            sessions[session_id].update({
                "transcript": "",
                "tweet_mode": "idle",
                "tweet_content": "",
                "segments_count": 0,
                "last_segment_time": None,
                "accumulated_text": ""
            })


class OAuthStateStorage:
    """Store OAuth state and code_verifier temporarily"""
    
    @staticmethod
    def save_oauth_state(uid: str, code_verifier: str, state: str):
        """Save OAuth state and code_verifier"""
        oauth_states[uid] = {
            "code_verifier": code_verifier,
            "state": state,
            "created_at": datetime.utcnow()
        }
    
    @staticmethod
    def get_oauth_state(uid: str) -> Optional[dict]:
        """Get OAuth state by uid"""
        return oauth_states.get(uid)
    
    @staticmethod
    def remove_oauth_state(uid: str):
        """Remove OAuth state after use"""
        if uid in oauth_states:
            del oauth_states[uid]

