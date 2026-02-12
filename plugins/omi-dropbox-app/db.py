"""
Database layer for Dropbox Omi plugin.
Supports Redis (production) with file fallback (local development).
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

# Try to import redis, but make it optional
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Key prefixes
TOKEN_KEY_PREFIX = "dropbox:tokens:"
OAUTH_STATE_PREFIX = "dropbox:oauth_state:"
SETTINGS_PREFIX = "dropbox:settings:"

# File storage paths (fallback)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
OAUTH_STATE_FILE = os.path.join(DATA_DIR, "oauth_states.json")

# Redis client singleton
_redis_client = None


def _get_redis() -> Optional[Any]:
    """Get Redis client, return None if unavailable."""
    global _redis_client

    if not REDIS_AVAILABLE:
        return None

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            _redis_client.ping()
        except Exception:
            return None

    return _redis_client


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(filepath: str) -> Dict:
    """Load JSON file, return empty dict if not exists."""
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(filepath: str, data: Dict):
    """Save data to JSON file."""
    _ensure_data_dir()
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ============== Token Management ==============

def store_dropbox_tokens(
    uid: str,
    access_token: str,
    refresh_token: str,
    expires_at: str,
    account_id: Optional[str] = None,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
):
    """Store Dropbox OAuth tokens for a user."""
    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "account_id": account_id,
        "display_name": display_name,
        "email": email,
        "updated_at": datetime.utcnow().isoformat(),
    }

    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        r.set(key, json.dumps(token_data))
        r.expire(key, 60 * 60 * 24 * 365)  # 1 year
    else:
        tokens = _load_json(TOKENS_FILE)
        tokens[uid] = token_data
        _save_json(TOKENS_FILE, tokens)


def get_dropbox_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Get Dropbox tokens for a user."""
    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    else:
        tokens = _load_json(TOKENS_FILE)
        return tokens.get(uid)


def update_dropbox_tokens(uid: str, access_token: str, expires_at: str):
    """Update access token after refresh."""
    tokens = get_dropbox_tokens(uid)
    if not tokens:
        return

    tokens["access_token"] = access_token
    tokens["expires_at"] = expires_at
    tokens["updated_at"] = datetime.utcnow().isoformat()

    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        r.set(key, json.dumps(tokens))
        r.expire(key, 60 * 60 * 24 * 365)
    else:
        all_tokens = _load_json(TOKENS_FILE)
        all_tokens[uid] = tokens
        _save_json(TOKENS_FILE, all_tokens)


def delete_dropbox_tokens(uid: str):
    """Delete Dropbox tokens for a user (disconnect)."""
    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        r.delete(key)
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            del tokens[uid]
            _save_json(TOKENS_FILE, tokens)


# ============== OAuth State Management ==============

def store_oauth_state(uid: str, state: str):
    """Store OAuth state for CSRF protection."""
    r = _get_redis()
    if r:
        key = f"{OAUTH_STATE_PREFIX}{uid}"
        r.set(key, state)
        r.expire(key, 60 * 10)  # 10 minutes
    else:
        states = _load_json(OAUTH_STATE_FILE)
        states[uid] = {
            "state": state,
            "created_at": datetime.utcnow().isoformat(),
        }
        _save_json(OAUTH_STATE_FILE, states)


def get_oauth_state(uid: str) -> Optional[str]:
    """Get stored OAuth state for verification."""
    r = _get_redis()
    if r:
        key = f"{OAUTH_STATE_PREFIX}{uid}"
        return r.get(key)
    else:
        states = _load_json(OAUTH_STATE_FILE)
        state_data = states.get(uid)
        if state_data:
            return state_data.get("state")
        return None


def delete_oauth_state(uid: str):
    """Delete OAuth state after use."""
    r = _get_redis()
    if r:
        key = f"{OAUTH_STATE_PREFIX}{uid}"
        r.delete(key)
    else:
        states = _load_json(OAUTH_STATE_FILE)
        if uid in states:
            del states[uid]
            _save_json(OAUTH_STATE_FILE, states)


# ============== User Settings Management ==============

def get_user_settings(uid: str) -> Dict[str, Any]:
    """Get user settings with defaults."""
    defaults = {
        "folder_name": "Omi Conversations",
        "save_summary": True,
        "save_transcript": True,
    }

    r = _get_redis()
    if r:
        key = f"{SETTINGS_PREFIX}{uid}"
        data = r.get(key)
        if data:
            settings = json.loads(data)
            return {**defaults, **settings}
        return defaults
    else:
        all_settings = _load_json(SETTINGS_FILE)
        user_settings = all_settings.get(uid, {})
        return {**defaults, **user_settings}


def store_user_settings(uid: str, settings: Dict[str, Any]):
    """Store user settings."""
    r = _get_redis()
    if r:
        key = f"{SETTINGS_PREFIX}{uid}"
        r.set(key, json.dumps(settings))
        r.expire(key, 60 * 60 * 24 * 365)
    else:
        all_settings = _load_json(SETTINGS_FILE)
        all_settings[uid] = settings
        _save_json(SETTINGS_FILE, all_settings)


def update_user_setting(uid: str, key: str, value: Any):
    """Update a single user setting."""
    settings = get_user_settings(uid)
    settings[key] = value
    store_user_settings(uid, settings)
