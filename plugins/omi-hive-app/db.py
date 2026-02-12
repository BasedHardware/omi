"""
Redis-based storage for Hive API keys and user settings.
Supports both local development (file fallback) and production (Redis).
"""
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

# Try to import redis, fall back to file-based if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Redis connection
_redis_client = None


def _get_redis() -> Optional['redis.Redis']:
    """Get or create Redis connection."""
    global _redis_client
    
    if not REDIS_AVAILABLE:
        return None
    
    redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL")
    if not redis_url:
        return None
    
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            _redis_client.ping()  # Test connection
            print("✅ Connected to Redis")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}, falling back to file storage")
            return None
    
    return _redis_client


# File-based fallback for local development
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
API_KEYS_FILE = os.path.join(DATA_DIR, "api_keys.json")
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")


def _ensure_data_dir():
    """Ensure the data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON from file, return empty dict if not exists."""
    _ensure_data_dir()
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}


def _save_json(filepath: str, data: Dict[str, Any]):
    """Save data to JSON file."""
    _ensure_data_dir()
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


# ============================================
# API Key Management
# ============================================

def store_hive_credentials(uid: str, api_key: str, hive_user_id: str, hive_email: Optional[str] = None, hive_name: Optional[str] = None, workspace_id: Optional[str] = None):
    """Store Hive API key and user info for an Omi user."""
    r = _get_redis()
    
    credential_data = {
        "api_key": api_key,
        "hive_user_id": hive_user_id,
        "hive_email": hive_email,
        "hive_name": hive_name,
        "workspace_id": workspace_id,
        "connected_at": datetime.utcnow().isoformat()
    }
    
    if r:
        # Use Redis
        key = f"hive:credentials:{uid}"
        r.set(key, json.dumps(credential_data))
        # Set expiry to 365 days (API keys don't expire, but we want cleanup)
        r.expire(key, 60 * 60 * 24 * 365)
    else:
        # Fallback to file
        api_keys = _load_json(API_KEYS_FILE)
        api_keys[uid] = credential_data
        _save_json(API_KEYS_FILE, api_keys)


def get_hive_credentials(uid: str) -> Optional[Dict[str, Any]]:
    """Get Hive credentials for an Omi user."""
    r = _get_redis()
    
    if r:
        key = f"hive:credentials:{uid}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    else:
        api_keys = _load_json(API_KEYS_FILE)
        return api_keys.get(uid)


def delete_hive_credentials(uid: str):
    """Delete Hive credentials for an Omi user."""
    r = _get_redis()
    
    if r:
        key = f"hive:credentials:{uid}"
        r.delete(key)
    else:
        api_keys = _load_json(API_KEYS_FILE)
        if uid in api_keys:
            del api_keys[uid]
            _save_json(API_KEYS_FILE, api_keys)


def is_connected(uid: str) -> bool:
    """Check if the user has connected their Hive account."""
    credentials = get_hive_credentials(uid)
    return credentials is not None and credentials.get("api_key") is not None


# ============================================
# User Settings Management
# ============================================

def store_user_setting(uid: str, key: str, value: Any):
    """Store a setting for a user."""
    r = _get_redis()
    
    if r:
        redis_key = f"hive:settings:{uid}"
        settings = r.get(redis_key)
        settings = json.loads(settings) if settings else {}
        settings[key] = value
        r.set(redis_key, json.dumps(settings))
    else:
        settings = _load_json(USER_SETTINGS_FILE)
        if uid not in settings:
            settings[uid] = {}
        settings[uid][key] = value
        _save_json(USER_SETTINGS_FILE, settings)


def get_user_setting(uid: str, key: str) -> Optional[Any]:
    """Get a setting for a user."""
    r = _get_redis()
    
    if r:
        redis_key = f"hive:settings:{uid}"
        settings = r.get(redis_key)
        if settings:
            return json.loads(settings).get(key)
        return None
    else:
        settings = _load_json(USER_SETTINGS_FILE)
        return settings.get(uid, {}).get(key)


def get_user_settings(uid: str) -> Dict[str, Any]:
    """Get all settings for a user."""
    r = _get_redis()
    
    if r:
        redis_key = f"hive:settings:{uid}"
        settings = r.get(redis_key)
        return json.loads(settings) if settings else {}
    else:
        settings = _load_json(USER_SETTINGS_FILE)
        return settings.get(uid, {})


def store_default_project(uid: str, project_id: str, project_name: str):
    """Store the default project for a user."""
    store_user_setting(uid, "default_project", {
        "id": project_id,
        "name": project_name
    })


def get_default_project(uid: str) -> Optional[Dict[str, str]]:
    """Get the default project for a user."""
    return get_user_setting(uid, "default_project")


def store_default_workspace(uid: str, workspace_id: str, workspace_name: str):
    """Store the default workspace for a user."""
    store_user_setting(uid, "default_workspace", {
        "id": workspace_id,
        "name": workspace_name
    })


def get_default_workspace(uid: str) -> Optional[Dict[str, str]]:
    """Get the default workspace for a user."""
    return get_user_setting(uid, "default_workspace")

