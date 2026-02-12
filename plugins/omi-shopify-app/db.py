"""
Redis-based storage for Shopify tokens and user settings.
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
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
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

def store_shopify_tokens(uid: str, access_token: str, shop_domain: str, scope: str):
    """Store Shopify tokens for a user."""
    r = _get_redis()
    
    token_data = {
        "access_token": access_token,
        "shop_domain": shop_domain,
        "scope": scope,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    if r:
        # Use Redis
        key = f"shopify:tokens:{uid}"
        r.set(key, json.dumps(token_data))
        # Shopify access tokens don't expire, but we set a long TTL
        r.expire(key, 60 * 60 * 24 * 365)  # 1 year
    else:
        # Fallback to file
        tokens = _load_json(TOKENS_FILE)
        tokens[uid] = token_data
        _save_json(TOKENS_FILE, tokens)


def get_shopify_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Get Shopify tokens for a user."""
    r = _get_redis()
    
    if r:
        key = f"shopify:tokens:{uid}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    else:
        tokens = _load_json(TOKENS_FILE)
        return tokens.get(uid)


def delete_shopify_tokens(uid: str):
    """Delete Shopify tokens for a user."""
    r = _get_redis()
    
    if r:
        key = f"shopify:tokens:{uid}"
        r.delete(key)
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            del tokens[uid]
            _save_json(TOKENS_FILE, tokens)


# ============================================
# User Settings Management
# ============================================

def store_user_setting(uid: str, key: str, value: Any):
    """Store a setting for a user."""
    r = _get_redis()
    
    if r:
        redis_key = f"shopify:settings:{uid}"
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
        redis_key = f"shopify:settings:{uid}"
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
        redis_key = f"shopify:settings:{uid}"
        settings = r.get(redis_key)
        return json.loads(settings) if settings else {}
    else:
        settings = _load_json(USER_SETTINGS_FILE)
        return settings.get(uid, {})


def store_default_store(uid: str, shop_domain: str, shop_name: str):
    """Store the default store for a user."""
    store_user_setting(uid, "default_store", {
        "domain": shop_domain,
        "name": shop_name
    })


def get_default_store(uid: str) -> Optional[Dict[str, str]]:
    """Get the default store for a user."""
    return get_user_setting(uid, "default_store")

