"""
Redis-based storage for Zomato OAuth tokens and OAuth state.
Supports both production (Redis) and local development (file fallback).
"""

import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

_redis_client = None


def _get_redis() -> Optional["redis.Redis"]:
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
            _redis_client.ping()
        except Exception:
            return None

    return _redis_client


# File-based fallback for local development
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
STATE_FILE = os.path.join(DATA_DIR, "oauth_state.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(filepath: str) -> Dict[str, Any]:
    _ensure_data_dir()
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}


def _save_json(filepath: str, data: Dict[str, Any]):
    _ensure_data_dir()
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Token Management
# ---------------------------------------------------------------------------


def store_zomato_tokens(uid: str, token_data: Dict[str, Any]):
    """Store Zomato OAuth tokens for a user."""
    token_data["updated_at"] = datetime.utcnow().isoformat()
    r = _get_redis()
    if r:
        key = f"zomato:tokens:{uid}"
        r.set(key, json.dumps(token_data))
        r.expire(key, 60 * 60 * 24 * 365)
    else:
        tokens = _load_json(TOKENS_FILE)
        tokens[uid] = token_data
        _save_json(TOKENS_FILE, tokens)


def get_zomato_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Get Zomato OAuth tokens for a user."""
    r = _get_redis()
    if r:
        key = f"zomato:tokens:{uid}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    else:
        tokens = _load_json(TOKENS_FILE)
        return tokens.get(uid)


def delete_zomato_tokens(uid: str):
    """Delete Zomato OAuth tokens for a user."""
    r = _get_redis()
    if r:
        r.delete(f"zomato:tokens:{uid}")
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            del tokens[uid]
            _save_json(TOKENS_FILE, tokens)


# ---------------------------------------------------------------------------
# OAuth State Management (temporary, for in-flight auth flows)
# ---------------------------------------------------------------------------


def store_oauth_state(state: str, data: Dict[str, Any]):
    """Store temporary OAuth state (PKCE verifier, client info, uid)."""
    r = _get_redis()
    if r:
        key = f"zomato:oauth_state:{state}"
        r.set(key, json.dumps(data))
        r.expire(key, 600)  # 10 minute TTL
    else:
        states = _load_json(STATE_FILE)
        states[state] = data
        _save_json(STATE_FILE, states)


def get_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """Retrieve and consume OAuth state."""
    r = _get_redis()
    if r:
        key = f"zomato:oauth_state:{state}"
        data = r.get(key)
        if data:
            r.delete(key)
            return json.loads(data)
        return None
    else:
        states = _load_json(STATE_FILE)
        return states.pop(state, None)
