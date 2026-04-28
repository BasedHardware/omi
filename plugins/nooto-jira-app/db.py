"""Token store, HMAC OAuth state, and Atlassian token refresh.

Slice B owns this file. Other slices import:
    get_jira_tokens, get_valid_access_token, is_setup_completed
and treat them as the only entry points.

Storage backends, in priority order:
    1. Redis if REDIS_URL or REDIS_PRIVATE_URL is set.
    2. JSON file fallback under DATA_DIR (default ./data) for local dev.

Keys:
    jira:tokens:{uid}        TTL 90d   — token blob (see models.TokenSet)
    jira:oauth_state:{uid}   TTL 600s  — one-shot replay guard (consume_oauth_state uses GETDEL)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

try:
    import redis as _redis_lib

    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover - redis is in requirements but be defensive
    _REDIS_AVAILABLE = False

log = logging.getLogger("nooto-jira-app.db")

# ── Constants ──────────────────────────────────────────────────────────────

ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"

TOKENS_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 days
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes
STATE_MAX_AGE_SECONDS = 600
REFRESH_LEEWAY_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 15.0

# ── Redis / file backend wiring ────────────────────────────────────────────

_redis_client: Optional[Any] = None


def _get_redis() -> Optional[Any]:
    """Return a connected Redis client, or None to fall back to file storage."""
    global _redis_client
    if not _REDIS_AVAILABLE:
        return None
    redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL")
    if not redis_url:
        return None
    if _redis_client is None:
        try:
            _redis_client = _redis_lib.from_url(redis_url, decode_responses=True)
            _redis_client.ping()
            log.info("Connected to Redis for jira token store")
        except Exception as exc:
            log.warning("Redis connection failed (%s); using file fallback", exc)
            _redis_client = None
            return None
    return _redis_client


# Public alias — every module imports this instead of re-implementing redis.from_url.
def get_redis() -> Optional[Any]:
    return _get_redis()


_httpx_client: Optional[httpx.Client] = None


def get_http_client() -> httpx.Client:
    """Module-level reusable sync httpx client. Pools connections across calls."""
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    return _httpx_client


def _data_dir() -> str:
    return os.getenv("DATA_DIR") or os.path.join(os.path.dirname(__file__), "data")


def _tokens_file() -> str:
    return os.path.join(_data_dir(), "jira_tokens.json")


def _oauth_state_file() -> str:
    return os.path.join(_data_dir(), "jira_oauth_state.json")


def _ensure_data_dir() -> None:
    os.makedirs(_data_dir(), exist_ok=True)


def _load_json(path: str) -> dict[str, Any]:
    _ensure_data_dir()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load %s (%s); treating as empty", path, exc)
        return {}


def _save_json(path: str, data: dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── Token storage ──────────────────────────────────────────────────────────


def store_jira_tokens(
    uid: str,
    access_token: str,
    refresh_token: str,
    expires_at: int,
    sites: list[dict[str, Any]],
    default_cloud_id: Optional[str] = None,
    scope: str = "",
) -> None:
    blob: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int(expires_at),
        "scope": scope,
        "token_type": "Bearer",
        "sites": sites or [],
        "default_cloud_id": default_cloud_id or (sites[0]["id"] if sites else None),
        "updated_at": datetime.utcnow().isoformat(),
    }

    r = _get_redis()
    if r is not None:
        key = f"jira:tokens:{uid}"
        r.set(key, json.dumps(blob))
        r.expire(key, TOKENS_TTL_SECONDS)
        return

    tokens = _load_json(_tokens_file())
    tokens[uid] = blob
    _save_json(_tokens_file(), tokens)


def get_jira_tokens(uid: str) -> Optional[dict[str, Any]]:
    r = _get_redis()
    if r is not None:
        raw = r.get(f"jira:tokens:{uid}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Corrupt jira token blob for uid=%s; ignoring", uid)
            return None

    tokens = _load_json(_tokens_file())
    return tokens.get(uid)


def clear_jira_tokens(uid: str) -> None:
    r = _get_redis()
    if r is not None:
        r.delete(f"jira:tokens:{uid}")
        return
    tokens = _load_json(_tokens_file())
    if uid in tokens:
        del tokens[uid]
        _save_json(_tokens_file(), tokens)


def is_setup_completed(uid: str) -> bool:
    return get_jira_tokens(uid) is not None


def set_default_cloud_id(uid: str, cloud_id: str) -> None:
    blob = get_jira_tokens(uid)
    if not blob:
        return
    blob["default_cloud_id"] = cloud_id
    blob["updated_at"] = datetime.utcnow().isoformat()

    r = _get_redis()
    if r is not None:
        key = f"jira:tokens:{uid}"
        r.set(key, json.dumps(blob))
        r.expire(key, TOKENS_TTL_SECONDS)
        return

    tokens = _load_json(_tokens_file())
    tokens[uid] = blob
    _save_json(_tokens_file(), tokens)


# ── Refresh loop ───────────────────────────────────────────────────────────


def _refresh_access_token(uid: str, blob: dict[str, Any]) -> Optional[str]:
    """Exchange refresh_token for a new access_token. Returns the new AT or None."""
    client_id = os.getenv("JIRA_CLIENT_ID", "")
    client_secret = os.getenv("JIRA_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        log.error("JIRA_CLIENT_ID/SECRET not configured; cannot refresh token for uid=%s", uid)
        return None

    refresh_token = blob.get("refresh_token")
    if not refresh_token:
        log.warning("No refresh_token stored for uid=%s; clearing tokens", uid)
        clear_jira_tokens(uid)
        return None

    try:
        resp = get_http_client().post(
            ATLASSIAN_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/json"},
        )
    except (httpx.HTTPError, OSError) as exc:
        log.warning("Network error refreshing jira token for uid=%s: %s", uid, exc)
        return None

    if resp.status_code >= 500:
        log.warning("Atlassian 5xx (%s) refreshing jira token for uid=%s; will retry later", resp.status_code, uid)
        return None

    if resp.status_code != 200:
        body: dict[str, Any] = {}
        try:
            body = resp.json()
        except Exception:
            body = {}
        if body.get("error") == "invalid_grant":
            log.warning("Atlassian invalid_grant for uid=%s; clearing tokens", uid)
            clear_jira_tokens(uid)
            return None
        log.warning("Atlassian token refresh failed (%s) for uid=%s", resp.status_code, uid)
        return None

    payload = resp.json()
    new_at = payload.get("access_token")
    # Atlassian rotates RTs — always overwrite with the new one if present.
    new_rt = payload.get("refresh_token") or refresh_token
    expires_in = int(payload.get("expires_in", 3600))
    new_expires_at = int(time.time()) + expires_in
    new_scope = payload.get("scope", blob.get("scope", ""))

    if not new_at:
        log.warning("Atlassian refresh returned no access_token for uid=%s", uid)
        return None

    store_jira_tokens(
        uid,
        access_token=new_at,
        refresh_token=new_rt,
        expires_at=new_expires_at,
        sites=blob.get("sites", []),
        default_cloud_id=blob.get("default_cloud_id"),
        scope=new_scope,
    )
    return new_at


def get_valid_access_token(uid: str) -> Optional[str]:
    """Return a non-expired access token, refreshing if expires_at - 60 < now.

    On `invalid_grant` from Atlassian, clears the stored tokens (user must
    reconnect). On 5xx / network errors, leaves tokens intact and returns None
    so the caller can retry later.
    """
    blob = get_jira_tokens(uid)
    if not blob:
        return None

    expires_at = int(blob.get("expires_at", 0))
    now = int(time.time())
    if expires_at - REFRESH_LEEWAY_SECONDS > now:
        return blob.get("access_token")

    return _refresh_access_token(uid, blob)


# ── Active-Jira context (single Redis fetch helper) ────────────────────────


def get_active_jira(uid: str) -> Optional[tuple[str, str, str, dict[str, Any]]]:
    """Resolve everything routes need to call Jira in one shot.

    Returns (access_token, cloudid, site_url, blob) or None when:
      - the user is not connected,
      - the refresh failed (transient or invalid_grant),
      - the user has no default Jira site.

    Reuses the in-memory blob to avoid a second `get_jira_tokens` call on the
    happy path.
    """
    blob = get_jira_tokens(uid)
    if not blob:
        return None

    expires_at = int(blob.get("expires_at", 0))
    now = int(time.time())
    if expires_at - REFRESH_LEEWAY_SECONDS > now:
        token = blob.get("access_token")
    else:
        token = _refresh_access_token(uid, blob)
        if not token:
            return None
        # Refresh persisted a new blob — re-read so site list / default match.
        blob = get_jira_tokens(uid) or blob

    cloudid = blob.get("default_cloud_id")
    if not token or not cloudid:
        return None

    site_url = ""
    for site in blob.get("sites", []) or []:
        if site.get("id") == cloudid:
            site_url = (site.get("url") or "").rstrip("/")
            break

    return token, cloudid, site_url, blob


# ── Settings store (jira:settings:{uid} hash) ──────────────────────────────


def get_settings(uid: str) -> dict[str, str]:
    r = _get_redis()
    if not r:
        return {}
    try:
        return r.hgetall(f"jira:settings:{uid}") or {}
    except Exception as exc:
        log.warning("settings load failed for uid=%s: %s", uid, exc)
        return {}


def is_enabled(uid: str) -> bool:
    return get_settings(uid).get("enabled", "true") != "false"


def is_autofile_enabled(uid: str) -> bool:
    return get_settings(uid).get("autofile") == "true"


def within_quiet_hours(uid: str) -> bool:
    """True when uid is currently inside their configured quiet_hours window."""
    raw = get_settings(uid).get("quiet_hours") or ""
    if not raw or "-" not in raw:
        return False
    try:
        start_s, end_s = raw.split("-", 1)
        sh, sm = (int(x) for x in start_s.strip().split(":"))
        eh, em = (int(x) for x in end_s.strip().split(":"))
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    minutes_now = now.hour * 60 + now.minute
    s_min = sh * 60 + sm
    e_min = eh * 60 + em
    if s_min == e_min:
        return False
    if s_min < e_min:
        return s_min <= minutes_now < e_min
    # Wraps midnight (e.g. 22:00-07:00).
    return minutes_now >= s_min or minutes_now < e_min


# ── HMAC-signed OAuth state ────────────────────────────────────────────────


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _state_secret() -> bytes:
    secret = os.getenv("JIRA_OAUTH_STATE_SECRET", "")
    if not secret:
        raise RuntimeError("JIRA_OAUTH_STATE_SECRET is not configured")
    return secret.encode("utf-8")


def sign_state(uid: str) -> str:
    """payload.sig where payload = b64url(json({uid, nonce, ts})) and sig = HMAC-SHA256."""
    payload_obj = {
        "uid": uid,
        "nonce": secrets.token_urlsafe(16),
        "ts": int(time.time()),
    }
    payload_bytes = json.dumps(payload_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    sig = hmac.new(_state_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


def verify_state(state: str) -> str:
    """Return uid from a valid state token; raise on tamper / expiry (>600s)."""
    if not state or "." not in state:
        raise ValueError("malformed state")
    payload_b64, sig_b64 = state.rsplit(".", 1)

    expected_sig = hmac.new(_state_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    try:
        provided_sig = _b64url_decode(sig_b64)
    except (ValueError, TypeError):
        raise ValueError("malformed state signature")

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("state signature mismatch")

    try:
        payload_obj = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise ValueError("malformed state payload")

    uid = payload_obj.get("uid")
    ts = int(payload_obj.get("ts", 0))
    if not uid:
        raise ValueError("state missing uid")
    if int(time.time()) - ts > STATE_MAX_AGE_SECONDS:
        raise ValueError("state expired")
    return uid


def store_oauth_state(uid: str, signed_state: str) -> None:
    """SETEX jira:oauth_state:{uid} 600 <state>."""
    r = _get_redis()
    if r is not None:
        r.setex(f"jira:oauth_state:{uid}", OAUTH_STATE_TTL_SECONDS, signed_state)
        return

    states = _load_json(_oauth_state_file())
    states[uid] = signed_state
    _save_json(_oauth_state_file(), states)


def consume_oauth_state(uid: str) -> Optional[str]:
    """One-shot read-and-delete (GETDEL on Redis 6.2+)."""
    r = _get_redis()
    if r is not None:
        key = f"jira:oauth_state:{uid}"
        try:
            value = r.execute_command("GETDEL", key)
        except Exception:
            # Fallback for Redis < 6.2: GET + DEL (race window is acceptable here).
            value = r.get(key)
            if value is not None:
                r.delete(key)
        return value

    states = _load_json(_oauth_state_file())
    value = states.pop(uid, None)
    _save_json(_oauth_state_file(), states)
    return value
