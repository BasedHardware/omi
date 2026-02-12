"""
Redis-based storage for Notion tokens and user settings.
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
OAUTH_STATES_FILE = os.path.join(DATA_DIR, "oauth_states.json")
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
# Token Management
# ============================================

def store_notion_tokens(uid: str, access_token: str, workspace_id: str, workspace_name: str, bot_id: str):
    """Store Notion OAuth2 tokens for a user."""
    import sys
    r = _get_redis()

    token_data = {
        "access_token": access_token,
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "bot_id": bot_id,
        "updated_at": datetime.utcnow().isoformat()
    }

    if r:
        key = f"notion:tokens:{uid}"
        print(f"DB: Storing tokens in Redis for key={key}")
        sys.stdout.flush()
        r.set(key, json.dumps(token_data))
        # Notion tokens don't expire, but set TTL for cleanup
        r.expire(key, 60 * 60 * 24 * 365)  # 1 year
        print(f"DB: Tokens stored successfully in Redis")
        sys.stdout.flush()
    else:
        print(f"DB: Storing tokens in file for uid={uid}")
        sys.stdout.flush()
        tokens = _load_json(TOKENS_FILE)
        tokens[uid] = token_data
        _save_json(TOKENS_FILE, tokens)
        print(f"DB: Tokens stored successfully in file")
        sys.stdout.flush()


def get_notion_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Get Notion tokens for a user."""
    import sys
    r = _get_redis()

    if r:
        key = f"notion:tokens:{uid}"
        print(f"DB: Getting tokens from Redis for key={key}")
        sys.stdout.flush()
        data = r.get(key)
        if data:
            print(f"DB: Found tokens in Redis")
            sys.stdout.flush()
            return json.loads(data)
        print(f"DB: No tokens found in Redis for {uid}")
        sys.stdout.flush()
        return None
    else:
        print(f"DB: Using file storage (no Redis)")
        sys.stdout.flush()
        tokens = _load_json(TOKENS_FILE)
        result = tokens.get(uid)
        print(f"DB: File tokens for {uid}: {'found' if result else 'not found'}")
        sys.stdout.flush()
        return result


def update_notion_tokens(uid: str, access_token: str):
    """Update access token."""
    import sys
    r = _get_redis()

    if r:
        key = f"notion:tokens:{uid}"
        data = r.get(key)
        if data:
            token_data = json.loads(data)
            token_data["access_token"] = access_token
            token_data["updated_at"] = datetime.utcnow().isoformat()
            r.set(key, json.dumps(token_data))
            r.expire(key, 60 * 60 * 24 * 365)
            print(f"DB: Updated access token in Redis")
            sys.stdout.flush()
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            tokens[uid]["access_token"] = access_token
            tokens[uid]["updated_at"] = datetime.utcnow().isoformat()
            _save_json(TOKENS_FILE, tokens)
            print(f"DB: Updated access token in file")
            sys.stdout.flush()


def delete_notion_tokens(uid: str):
    """Delete Notion tokens for a user."""
    r = _get_redis()

    if r:
        key = f"notion:tokens:{uid}"
        r.delete(key)
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            del tokens[uid]
            _save_json(TOKENS_FILE, tokens)


# ============================================
# OAuth State Management (CSRF protection)
# ============================================

def store_oauth_state(uid: str, state: str):
    """Store OAuth state for CSRF verification."""
    r = _get_redis()

    if r:
        key = f"notion:oauth_state:{uid}"
        r.set(key, state)
        r.expire(key, 60 * 10)  # 10 minutes
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
        key = f"notion:oauth_state:{uid}"
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
        key = f"notion:oauth_state:{uid}"
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
        redis_key = f"notion:settings:{uid}"
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
        redis_key = f"notion:settings:{uid}"
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
        redis_key = f"notion:settings:{uid}"
        settings = r.get(redis_key)
        return json.loads(settings) if settings else {}
    else:
        settings = _load_json(USER_SETTINGS_FILE)
        return settings.get(uid, {})
