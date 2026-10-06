"""
Database layer for pCloud Omi plugin.
Supports Redis (production) with file fallback (local development / testing).
Implements encrypted per-account token storage with account isolation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Try to import redis, but make it optional
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Key prefixes for account isolation
TOKEN_KEY_PREFIX = "pcloud:tokens:"
OAUTH_STATE_PREFIX = "pcloud:oauth_state:"
SETTINGS_PREFIX = "pcloud:settings:"

# File storage paths (fallback)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
OAUTH_STATE_FILE = os.path.join(DATA_DIR, "oauth_states.json")

# Redis client singleton
_redis_client = None


def _get_encryption_key() -> str:
    """Retrieves or derives the token encryption key."""
    key = os.getenv("PCLOUD_TOKEN_ENCRYPTION_KEY") or os.getenv("APP_SECRET")
    if not key:
        key = "omi-pcloud-default-secret-salt-32b"
    return key


def encrypt_payload(plaintext: str, key: Optional[str] = None) -> str:
    """Encrypts plaintext using authenticated SHA256-CTR keystream and HMAC-SHA256."""
    enc_key = (key or _get_encryption_key()).encode("utf-8")
    salt = secrets.token_bytes(16)
    derived = hashlib.sha256(enc_key + salt).digest()

    plain_bytes = plaintext.encode("utf-8")
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(plain_bytes):
        keystream.extend(hashlib.sha256(derived + counter.to_bytes(4, "big")).digest())
        counter += 1

    ciphertext = bytes(p ^ k for p, k in zip(plain_bytes, keystream[: len(plain_bytes)]))
    tag = hmac.new(enc_key, salt + ciphertext, hashlib.sha256).digest()
    return base64.b64encode(salt + tag + ciphertext).decode("ascii")


def decrypt_payload(token_b64: str, key: Optional[str] = None) -> Optional[str]:
    """Decrypts authenticated ciphertext and verifies HMAC integrity."""
    try:
        raw = base64.b64decode(token_b64.encode("ascii"))
        if len(raw) < 48:  # 16 salt + 32 tag
            return None
        salt = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]

        enc_key = (key or _get_encryption_key()).encode("utf-8")
        expected_tag = hmac.new(enc_key, salt + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            return None

        derived = hashlib.sha256(enc_key + salt).digest()
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(ciphertext):
            keystream.extend(hashlib.sha256(derived + counter.to_bytes(4, "big")).digest())
            counter += 1

        plain_bytes = bytes(c ^ k for c, k in zip(ciphertext, keystream[: len(ciphertext)]))
        return plain_bytes.decode("utf-8")
    except Exception:
        return None


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


def _load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON file, return empty dict if not exists."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(filepath: str, data: Dict[str, Any]):
    """Save data to JSON file atomically."""
    _ensure_data_dir()
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, filepath)


# ============== Token Management with Encryption ==============


def store_pcloud_tokens(
    uid: str,
    access_token: str,
    location_id: int = 1,
    userid: Optional[int] = None,
    email: Optional[str] = None,
) -> bool:
    """Stores encrypted pCloud OAuth access tokens for a user."""
    token_data = {
        "access_token": access_token,
        "location_id": location_id,
        "userid": userid,
        "email": email,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    encrypted_blob = encrypt_payload(json.dumps(token_data))

    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        r.set(key, encrypted_blob)
        r.expire(key, 60 * 60 * 24 * 365)  # 1 year
        return True
    else:
        tokens = _load_json(TOKENS_FILE)
        tokens[uid] = encrypted_blob
        _save_json(TOKENS_FILE, tokens)
        return True


def get_pcloud_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Retrieves and decrypts pCloud tokens for a user with account isolation."""
    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        raw = r.get(key)
        if not raw:
            return None
    else:
        tokens = _load_json(TOKENS_FILE)
        raw = tokens.get(uid)
        if not raw:
            return None

    decrypted = decrypt_payload(raw)
    if not decrypted:
        return None
    try:
        return json.loads(decrypted)
    except json.JSONDecodeError:
        return None


def delete_pcloud_tokens(uid: str) -> bool:
    """Deletes pCloud tokens for a user (disconnect)."""
    r = _get_redis()
    if r:
        key = f"{TOKEN_KEY_PREFIX}{uid}"
        r.delete(key)
        return True
    else:
        tokens = _load_json(TOKENS_FILE)
        if uid in tokens:
            del tokens[uid]
            _save_json(TOKENS_FILE, tokens)
        return True


# ============== OAuth State Management ==============


def store_oauth_state(state: str, uid: str, location_id: int = 1) -> bool:
    """Stores CSRF state with 15-minute expiration."""
    state_data = {
        "uid": uid,
        "location_id": location_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    r = _get_redis()
    if r:
        key = f"{OAUTH_STATE_PREFIX}{state}"
        r.set(key, json.dumps(state_data))
        r.expire(key, 900)  # 15 minutes
        return True
    else:
        states = _load_json(OAUTH_STATE_FILE)
        states[state] = state_data
        _save_json(OAUTH_STATE_FILE, states)
        return True


def get_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """Retrieves OAuth state for verification."""
    r = _get_redis()
    if r:
        key = f"{OAUTH_STATE_PREFIX}{state}"
        data = r.get(key)
        return json.loads(data) if data else None
    else:
        states = _load_json(OAUTH_STATE_FILE)
        return states.get(state)


def delete_oauth_state(state: str) -> bool:
    """Deletes OAuth state after one-time consumption."""
    r = _get_redis()
    if r:
        key = f"{OAUTH_STATE_PREFIX}{state}"
        r.delete(key)
        return True
    else:
        states = _load_json(OAUTH_STATE_FILE)
        if state in states:
            del states[state]
            _save_json(OAUTH_STATE_FILE, states)
        return True


# ============== User Settings Management ==============


def store_user_settings(uid: str, settings: Dict[str, Any]) -> bool:
    """Stores user backup preferences."""
    r = _get_redis()
    if r:
        key = f"{SETTINGS_PREFIX}{uid}"
        r.set(key, json.dumps(settings))
        return True
    else:
        all_settings = _load_json(SETTINGS_FILE)
        all_settings[uid] = settings
        _save_json(SETTINGS_FILE, all_settings)
        return True


def get_user_settings(uid: str) -> Dict[str, Any]:
    """Retrieves user backup preferences with safe defaults."""
    default_settings = {
        "folder_name": "Omi Conversations",
        "save_summary": True,
        "save_transcript": True,
        "save_audio": True,
        "location_id": 1,
    }
    r = _get_redis()
    if r:
        key = f"{SETTINGS_PREFIX}{uid}"
        data = r.get(key)
        if data:
            try:
                merged = dict(default_settings)
                merged.update(json.loads(data))
                return merged
            except json.JSONDecodeError:
                pass
        return default_settings
    else:
        all_settings = _load_json(SETTINGS_FILE)
        user_conf = all_settings.get(uid, {})
        merged = dict(default_settings)
        merged.update(user_conf)
        return merged
