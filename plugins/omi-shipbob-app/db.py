"""
Redis-based storage for ShipBob tokens and user settings.
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

    redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or os.getenv("REDIS_PUBLIC_URL")
    if not redis_url:
        return None

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            _redis_client.ping()  # Test connection
            print("Connected to Redis")
        except Exception as e:
            print(f"Redis connection failed: {e}, falling back to file storage")
            return None

    return _redis_client


# File-based fallback for local development
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
OAUTH_STATES_FILE = os.path.join(DATA_DIR, "oauth_states.json")


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
# Token Management
# ============================================

def store_shipbob_tokens(
    uid: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    token_type: str = "Bearer",
    expires_in: Optional[int] = None,
    channel_id: Optional[int] = None
):
    """Store ShipBob OAuth2 tokens for a user."""
    r = _get_redis()

    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "channel_id": channel_id,
        "updated_at": datetime.utcnow().isoformat()
    }

    if r:
        key = f"shipbob:tokens:{uid}"
        r.set(key, json.dumps(token_data))
        r.expire(key, 60 * 60 * 24 * 30)  # 30 days
    else:
        tokens = _load_json(TOKENS_FILE)
        tokens[uid] = token_data
        _save_json(TOKENS_FILE, tokens)


def get_shipbob_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Get ShipBob tokens for a user."""
    r = _get_redis()

    if r:
        key = f"shipbob:tokens:{uid}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    else:
        tokens = _load_json(TOKENS_FILE)
        return tokens.get(uid)


def delete_shipbob_tokens(uid: str):
    """Delete ShipBob tokens for a user."""
    r = _get_redis()

    if r:
        key = f"shipbob:tokens:{uid}"
        r.delete(key)
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            del tokens[uid]
            _save_json(TOKENS_FILE, tokens)


def update_shipbob_channel(uid: str, channel_id: int):
    """Update the channel ID for a user."""
    tokens = get_shipbob_tokens(uid)
    if tokens:
        tokens["channel_id"] = channel_id
        store_shipbob_tokens(
            uid,
            tokens["access_token"],
            tokens.get("refresh_token"),
            tokens.get("token_type", "Bearer"),
            tokens.get("expires_in"),
            channel_id
        )


# ============================================
# OAuth State Management (CSRF protection)
# ============================================

def store_oauth_state(uid: str, state: str):
    """Store OAuth state for CSRF verification."""
    r = _get_redis()

    if r:
        key = f"shipbob:oauth_state:{uid}"
        r.set(key, state)
        # State is short-lived (10 minutes)
        r.expire(key, 60 * 10)
    else:
        states = _load_json(OAUTH_STATES_FILE)
        states[uid] = {
            "state": state,
            "created_at": datetime.utcnow().isoformat()
        }
        _save_json(OAUTH_STATES_FILE, states)


def get_oauth_state(uid: str) -> Optional[str]:
    """Get stored OAuth state for a user."""
    r = _get_redis()

    if r:
        key = f"shipbob:oauth_state:{uid}"
        return r.get(key)
    else:
        states = _load_json(OAUTH_STATES_FILE)
        state_data = states.get(uid)
        if state_data:
            return state_data.get("state")
        return None


def delete_oauth_state(uid: str):
    """Delete OAuth state after verification."""
    r = _get_redis()

    if r:
        key = f"shipbob:oauth_state:{uid}"
        r.delete(key)
    else:
        states = _load_json(OAUTH_STATES_FILE)
        if uid in states:
            del states[uid]
            _save_json(OAUTH_STATES_FILE, states)


# ============================================
# User Settings Management
# ============================================

def store_user_setting(uid: str, key: str, value: Any):
    """Store a setting for a user."""
    r = _get_redis()

    if r:
        redis_key = f"shipbob:settings:{uid}"
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
        redis_key = f"shipbob:settings:{uid}"
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
        redis_key = f"shipbob:settings:{uid}"
        settings = r.get(redis_key)
        return json.loads(settings) if settings else {}
    else:
        settings = _load_json(USER_SETTINGS_FILE)
        return settings.get(uid, {})
