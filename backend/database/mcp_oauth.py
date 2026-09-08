import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict, cast
import re
from urllib.parse import unquote, urlsplit

from google.cloud import firestore

from database._client import data_plane_db as db
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.memory_app_key_grants import (
    APP_KEY_MEMORY_GRANT_DOC_ID,
    APP_KEY_MEMORY_GRANTS_COLLECTION,
    MCP_CONSUMER,
    build_app_key_scope_grant_contract_state,
)

PRODUCTION_MCP_RESOURCE_URL = "https://api.omi.me/v1/mcp/sse"
# Omi Beta intentionally serves MCP data from dev while retaining the production
# OAuth authority and its production Firestore grants.
BETA_MCP_RESOURCE_URL = "https://api.omiapi.com/v1/mcp/sse"
MCP_RESOURCE_URL = os.getenv("MCP_RESOURCE_URL", PRODUCTION_MCP_RESOURCE_URL)
DEFAULT_CLIENT_ID = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_ID", "omi-chatgpt-prod")
DEFAULT_CLIENT_NAME = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_NAME", "ChatGPT")
DEFAULT_CLAUDE_CLIENT_ID = os.getenv("MCP_OAUTH_CLAUDE_CLIENT_ID", "omi-claude-prod")
DEFAULT_CLAUDE_CLIENT_NAME = os.getenv("MCP_OAUTH_CLAUDE_CLIENT_NAME", "Claude")
DEFAULT_PUBLIC_CLIENT_ID = os.getenv("MCP_OAUTH_PUBLIC_CLIENT_ID", "omi-mcp-public")
DEFAULT_PUBLIC_CLIENT_NAME = os.getenv("MCP_OAUTH_PUBLIC_CLIENT_NAME", "Omi MCP Public")
SUPPORTED_SCOPES = [
    "memories.read",
    "memories.write",
    "conversations.read",
    "action_items.read",
    "action_items.write",
    "goals.read",
    "chat.read",
    "screen_activity.read",
    "people.read",
]
ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS", "3600"))
AUTH_CODE_TTL_SECONDS = int(os.getenv("MCP_OAUTH_AUTH_CODE_TTL_SECONDS", "600"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("MCP_OAUTH_REFRESH_TOKEN_TTL_DAYS", "365"))
PKCE_ALLOWED_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
SUPPORTED_TOKEN_AUTH_METHODS = ["client_secret_post", "none"]
PUBLIC_CHATGPT_CLIENT_IDS = {"omi-chatgpt-prod", "omi-chatgpt-dev"}
PRODUCTION_CROSS_PLANE_CLIENT_IDS = {"omi-chatgpt-prod", "omi-claude-prod"}
CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX = "https://chatgpt.com/connector/oauth/"
CLAUDE_CONNECTOR_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"


class AccountDeletionAccessBlocked(RuntimeError):
    """Raised when an OAuth write loses the deletion-admission race."""


# --- OAuth token document contracts (Firestore write-path shapes) ------------


class OAuthAccessTokenDict(TypedDict):
    """MCP OAuth access-token document (mcp_oauth_access_tokens).

    Every field is populated when the document is written, so all keys are
    treated as required by the write-path contract.
    """

    id: str
    grant_id: str
    uid: str
    client_id: str
    resource: str
    scopes: List[str]
    created_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime]


class OAuthRefreshTokenDict(TypedDict):
    """MCP OAuth refresh-token document (mcp_oauth_refresh_tokens).

    Every field is populated when the document is written, so all keys are
    treated as required by the write-path contract.
    """

    id: str
    grant_id: str
    token_family_id: str
    uid: str
    client_id: str
    resource: str
    scopes: List[str]
    created_at: datetime
    expires_at: datetime
    used_at: Optional[datetime]
    replaced_by: Optional[str]
    revoked_at: Optional[datetime]
    replay_detected_at: Optional[datetime]


def _typed_transactional(func: Callable[..., Any]) -> Callable[..., Any]:
    """Typed shim around firestore.transactional (SDK stub gap)."""
    return firestore.transactional(func)  # type: ignore[reportUnknownMemberType]  # firestore transactional decorator is untyped


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for Firestore DocumentSnapshot.to_dict()."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _csv_env(name: str) -> List[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


def _csv_values(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in cast(List[Any], value) if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _secret_hash_from_config(config: Dict[str, Any]) -> str:
    secret_hash: Any = config.get("client_secret_hash") or config.get("secret_hash") or ""
    secret_hash_env = config.get("client_secret_hash_env") or config.get("secret_hash_env")
    if secret_hash_env:
        secret_hash = os.getenv(str(secret_hash_env), secret_hash)
    secret_env = config.get("client_secret_env") or config.get("secret_env")
    secret = os.getenv(str(secret_env), "") if secret_env else config.get("client_secret") or config.get("secret") or ""
    return str(secret_hash or (hash_secret(str(secret)) if secret else ""))


def _client_from_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    client_id = str(config.get("client_id") or config.get("id") or "").strip()
    if not client_id:
        return None
    auth_method: Any = config.get("token_endpoint_auth_method")
    if auth_method is None:
        public_value: Any = config.get("public")
        if public_value is not None and not isinstance(public_value, bool):
            return None
        client_type = str(config.get("client_type") or "").lower()
        if client_type and client_type not in ("public", "confidential"):
            return None
        auth_method = "none" if public_value is True or client_type == "public" else "client_secret_post"
    auth_method = str(auth_method)
    if auth_method not in SUPPORTED_TOKEN_AUTH_METHODS:
        return None
    client: Dict[str, Any] = {
        "id": client_id,
        "name": config.get("name") or client_id,
        "registration_mode": config.get("registration_mode") or "env",
        "allowed_redirect_uris": _csv_values(config.get("allowed_redirect_uris") or config.get("redirect_uris")),
        "allowed_redirect_uri_prefixes": _csv_values(
            config.get("allowed_redirect_uri_prefixes") or config.get("redirect_uri_prefixes")
        ),
        "allowed_resources": _csv_values(config.get("allowed_resources") or config.get("resources"))
        or [MCP_RESOURCE_URL],
        "allowed_scopes": _csv_values(config.get("allowed_scopes") or config.get("scopes")) or SUPPORTED_SCOPES,
        "token_endpoint_auth_method": auth_method,
        "client_secret_hash": _secret_hash_from_config(config) if auth_method == "client_secret_post" else "",
        "disabled_at": config.get("disabled_at"),
    }
    return client


def _env_clients() -> Dict[str, Dict[str, Any]]:
    raw_clients = os.getenv("MCP_OAUTH_CLIENTS_JSON", "")
    if not raw_clients:
        return {}
    try:
        parsed = json.loads(raw_clients)
    except json.JSONDecodeError:
        return {}
    entries: List[Dict[str, Any]] = []
    if isinstance(parsed, dict):
        for client_id, config in cast(Dict[Any, Any], parsed).items():
            if isinstance(config, dict):
                entries.append({"client_id": client_id, **cast(Dict[str, Any], config)})
    elif isinstance(parsed, list):
        for config in cast(List[Any], parsed):
            if isinstance(config, dict):
                entries.append(cast(Dict[str, Any], config))
    clients: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        client = _client_from_config(entry)
        if client:
            clients[client["id"]] = client
    return clients


def _legacy_chatgpt_client(client_id: Optional[str] = None) -> Dict[str, Any]:
    resolved_client_id = client_id or DEFAULT_CLIENT_ID
    secret = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_SECRET", "")
    secret_hash = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_SECRET_SHA256", "")
    auth_method = os.getenv("MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD", "").strip()
    if not auth_method and resolved_client_id in PUBLIC_CHATGPT_CLIENT_IDS:
        auth_method = "none"
    auth_method = auth_method or "client_secret_post"
    if auth_method not in SUPPORTED_TOKEN_AUTH_METHODS:
        auth_method = "client_secret_post"
    return {
        "id": resolved_client_id,
        "name": DEFAULT_CLIENT_NAME,
        "registration_mode": "legacy_env",
        "allowed_redirect_uris": _csv_env("MCP_OAUTH_CHATGPT_REDIRECT_URIS"),
        "allowed_redirect_uri_prefixes": (
            [CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX] if resolved_client_id in PUBLIC_CHATGPT_CLIENT_IDS else []
        ),
        "allowed_resources": [MCP_RESOURCE_URL],
        "allowed_scopes": SUPPORTED_SCOPES,
        "token_endpoint_auth_method": auth_method,
        "client_secret_hash": secret_hash
        or (hash_secret(secret) if secret and auth_method == "client_secret_post" else ""),
        "disabled_at": None,
    }


def _default_claude_client() -> Dict[str, Any]:
    return {
        "id": DEFAULT_CLAUDE_CLIENT_ID,
        "name": DEFAULT_CLAUDE_CLIENT_NAME,
        "registration_mode": "claude_env",
        "allowed_redirect_uris": _csv_env("MCP_OAUTH_CLAUDE_REDIRECT_URIS") or [CLAUDE_CONNECTOR_REDIRECT_URI],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [MCP_RESOURCE_URL],
        "allowed_scopes": SUPPORTED_SCOPES,
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }


def _public_redirect_uris() -> List[str]:
    return _csv_env("MCP_OAUTH_PUBLIC_REDIRECT_URIS") or _csv_env("MCP_OAUTH_CHATGPT_REDIRECT_URIS")


def _builtin_public_chatgpt_client(client_id: str) -> Optional[Dict[str, Any]]:
    """Built-in public PKCE clients the desktop references by stable id."""
    if client_id not in PUBLIC_CHATGPT_CLIENT_IDS:
        return None
    redirect_uris = _public_redirect_uris()
    if not redirect_uris:
        return None
    return {
        "id": client_id,
        "name": DEFAULT_CLIENT_NAME,
        "registration_mode": "builtin_public_chatgpt",
        "allowed_redirect_uris": redirect_uris,
        "allowed_resources": [MCP_RESOURCE_URL],
        "allowed_scopes": SUPPORTED_SCOPES,
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }


def _finalize_client(client: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Apply built-in provider defaults to configured and generated clients."""
    if not client:
        return None
    finalized = dict(client)
    client_id = finalized.get("id")
    if client_id in PUBLIC_CHATGPT_CLIENT_IDS:
        prefixes: List[str] = list(finalized.get("allowed_redirect_uri_prefixes") or [])
        if CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX not in prefixes:
            prefixes.append(CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX)
        finalized["allowed_redirect_uri_prefixes"] = prefixes
    if client_id in PRODUCTION_CROSS_PLANE_CLIENT_IDS and MCP_RESOURCE_URL == PRODUCTION_MCP_RESOURCE_URL:
        resources = _csv_values(finalized.get("allowed_resources")) or [MCP_RESOURCE_URL]
        if BETA_MCP_RESOURCE_URL not in resources:
            resources.append(BETA_MCP_RESOURCE_URL)
        finalized["allowed_resources"] = resources
    return finalized


def _default_public_client() -> Optional[Dict[str, Any]]:
    redirect_uris = _public_redirect_uris()
    if not redirect_uris:
        return None
    return {
        "id": DEFAULT_PUBLIC_CLIENT_ID,
        "name": DEFAULT_PUBLIC_CLIENT_NAME,
        "registration_mode": "public_env",
        "allowed_redirect_uris": redirect_uris,
        "allowed_resources": [MCP_RESOURCE_URL],
        "allowed_scopes": SUPPORTED_SCOPES,
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }


def get_client(client_id: str) -> Optional[Dict[str, Any]]:
    client: Optional[Dict[str, Any]] = None
    doc = db.collection("mcp_oauth_clients").document(client_id).get()
    if doc.exists:
        data: Dict[str, Any] = _typed_doc(doc)
        data.setdefault("id", client_id)
        data.setdefault("allowed_resources", [MCP_RESOURCE_URL])
        data.setdefault("allowed_scopes", SUPPORTED_SCOPES)
        data.setdefault("token_endpoint_auth_method", "client_secret_post")
        data.setdefault("allowed_redirect_uri_prefixes", [])
        client = data
    else:
        env_client = _env_clients().get(client_id)
        if env_client:
            client = env_client
        elif client_id == DEFAULT_CLIENT_ID:
            client = _legacy_chatgpt_client()
        elif client_id in PUBLIC_CHATGPT_CLIENT_IDS:
            client = _legacy_chatgpt_client(client_id)
        elif client_id == DEFAULT_CLAUDE_CLIENT_ID:
            client = _default_claude_client()
        elif client_id == DEFAULT_PUBLIC_CLIENT_ID:
            client = _default_public_client()
        else:
            client = _builtin_public_chatgpt_client(client_id)
    return _finalize_client(client)


def verify_client_secret(client: Dict[str, Any], client_secret: Optional[str]) -> bool:
    if client.get("token_endpoint_auth_method") != "client_secret_post":
        return False
    expected_hash: Any = client.get("client_secret_hash") or ""
    if not expected_hash or not client_secret:
        return False
    return hmac.compare_digest(expected_hash, hash_secret(client_secret))


def verify_client_auth(client: Dict[str, Any], client_secret: Optional[str]) -> bool:
    auth_method: Any = client.get("token_endpoint_auth_method") or "client_secret_post"
    if auth_method == "none":
        return not client_secret
    if auth_method == "client_secret_post":
        return verify_client_secret(client, client_secret)
    return False


def token_endpoint_auth_methods_supported() -> List[str]:
    return list(SUPPORTED_TOKEN_AUTH_METHODS)


def _path_has_unsafe_segment(path: str) -> bool:
    segments = path.split("/")
    for index, segment in enumerate(segments):
        decoded = unquote(segment)
        if decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
            return True
        if decoded == "" and index not in {0, len(segments) - 1}:
            return True
    return False


def _redirect_uri_matches_prefix(redirect_uri: str, prefix: str) -> bool:
    redirect_parts = urlsplit(redirect_uri)
    prefix_parts = urlsplit(prefix)
    redirect_path = redirect_parts.path
    prefix_path = prefix_parts.path
    if (
        redirect_parts.scheme != "https"
        or prefix_parts.scheme != "https"
        or redirect_parts.netloc != prefix_parts.netloc
        or redirect_parts.query
        or redirect_parts.fragment
        or prefix_parts.query
        or prefix_parts.fragment
        or _path_has_unsafe_segment(redirect_path)
        or _path_has_unsafe_segment(prefix_path)
    ):
        return False
    if not prefix_path:
        return False
    if prefix_path.endswith("/"):
        return redirect_path.startswith(prefix_path) and len(redirect_path) > len(prefix_path)
    return redirect_path == prefix_path or redirect_path.startswith(prefix_path + "/")


def validate_redirect_uri(client: Dict[str, Any], redirect_uri: str) -> bool:
    if urlsplit(redirect_uri).fragment:
        return False
    if redirect_uri in set(client.get("allowed_redirect_uris") or []):
        return True
    return any(
        _redirect_uri_matches_prefix(redirect_uri, prefix)
        for prefix in list(client.get("allowed_redirect_uri_prefixes") or [])
    )


def validate_resource(client: Dict[str, Any], resource: str) -> bool:
    return resource in set(client.get("allowed_resources") or [])


def normalize_scopes(scope: Optional[str], client: Optional[Dict[str, Any]] = None) -> List[str]:
    allowed = set((client or {}).get("allowed_scopes") or SUPPORTED_SCOPES).intersection(SUPPORTED_SCOPES)
    requested = [item for item in (scope or "").split(" ") if item]
    scopes = requested or ["memories.read"]
    if any(item not in allowed for item in scopes):
        raise ValueError("Unsupported scope requested")
    return sorted(set(scopes))


def pkce_s256(code_verifier: str) -> str:
    if not PKCE_ALLOWED_RE.fullmatch(code_verifier or ""):
        raise ValueError("Invalid PKCE verifier")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def validate_pkce_challenge(code_challenge: Optional[str], code_challenge_method: Optional[str]) -> bool:
    return bool(code_challenge) and code_challenge_method == "S256" and bool(PKCE_ALLOWED_RE.fullmatch(code_challenge))


def _grant_write(
    uid: str, client_id: str, resource: str, scopes: List[str], *, ref: Any, doc: Any, now: datetime
) -> Tuple[Any, Dict[str, Any], Dict[str, Any]]:
    existing: Dict[str, Any] = _typed_doc(doc) if doc.exists else {}
    if existing and (existing.get("revoked_at") or existing.get("status") == "revoked"):
        ref = db.collection("mcp_oauth_grants").document(f"{ref.id}:{uuid.uuid4()}")
        existing = {}
    existing_scopes = set(existing.get("scopes") or [])
    merged_scopes = sorted(existing_scopes.union(scopes))
    data: Dict[str, Any] = {
        "id": ref.id,
        "uid": uid,
        "client_id": client_id,
        "resource": resource,
        "scopes": merged_scopes,
        "updated_at": now,
        "last_used_at": now,
        "revoked_at": None,
        "status": "active",
    }
    if not existing:
        data["created_at"] = now
    return ref, existing, data


def _oauth_memory_grant_ref(uid: str) -> Any:
    return db.collection(f"users/{uid}/{APP_KEY_MEMORY_GRANTS_COLLECTION}").document(APP_KEY_MEMORY_GRANT_DOC_ID)


def _oauth_memory_grant_contract(grant: Dict[str, Any]) -> Dict[str, Any]:
    scopes = [scope for scope in grant.get("scopes") or [] if scope in {"memories.read", "memories.write"}]
    return build_app_key_scope_grant_contract_state(
        consumer=MCP_CONSUMER,
        app_id=cast(str, grant["client_id"]),
        key_id=cast(str, grant["id"]),
        scopes=scopes,
        default_read="memories.read" in scopes,
        archive_read=False,
        write="memories.write" in scopes,
        enabled=True,
    )


def _oauth_memory_grant_entry_is_absent(state: object, grant: Dict[str, Any]) -> bool:
    current = state
    for field in (
        "grants",
        MCP_CONSUMER,
        "apps",
        grant["client_id"],
        "keys",
        grant["id"],
    ):
        if not isinstance(current, dict):
            return False
        if field not in current:
            return True
        current = current[field]
    return False


def _create_oauth_memory_grant_if_absent(
    transaction: Any, grant_ref: Any, snapshot: Any, grant: Dict[str, Any]
) -> bool:
    if getattr(snapshot, "exists", False):
        state: object = snapshot.to_dict()
        if not _oauth_memory_grant_entry_is_absent(state, grant):
            return False
    transaction.set(grant_ref, _oauth_memory_grant_contract(grant), merge=True)
    return True


def _ensure_oauth_memory_grant(grant: Dict[str, Any]) -> bool:
    """Create a missing OAuth memory grant without changing control-plane state."""
    grant_ref = _oauth_memory_grant_ref(cast(str, grant["uid"]))
    transaction = db.transaction()

    @_typed_transactional
    def _create(transaction: Any) -> bool:
        snapshot = grant_ref.get(transaction=transaction)
        return _create_oauth_memory_grant_if_absent(transaction, grant_ref, snapshot, grant)

    return _create(transaction)


def create_or_update_grant(uid: str, client_id: str, resource: str, scopes: List[str]) -> Dict[str, Any]:
    deterministic_grant_id = f"{uid}:{client_id}:{hash_secret(resource)[:16]}"
    now = _now()
    ref = db.collection("mcp_oauth_grants").document(deterministic_grant_id)
    ref, existing, data = _grant_write(uid, client_id, resource, scopes, ref=ref, doc=ref.get(), now=now)
    ref.set(data, merge=True)
    grant = {**existing, **data}
    _ensure_oauth_memory_grant(grant)
    return grant


def _authorization_code_write(
    uid: str,
    grant_id: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scopes: List[str],
    code_challenge: str,
    *,
    now: datetime,
) -> Dict[str, Any]:
    return {
        "uid": uid,
        "grant_id": grant_id,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "resource": resource,
        "scopes": scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "created_at": now,
        "expires_at": now + timedelta(seconds=AUTH_CODE_TTL_SECONDS),
        "consumed_at": None,
    }


def issue_authorization_code(
    uid: str,
    grant_id: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scopes: List[str],
    code_challenge: str,
) -> str:
    raw_code = "omi_code_" + secrets.token_urlsafe(32)
    now = _now()
    db.collection("mcp_oauth_authorization_codes").document(hash_secret(raw_code)).set(
        _authorization_code_write(uid, grant_id, client_id, redirect_uri, resource, scopes, code_challenge, now=now)
    )
    return raw_code


def create_grant_and_authorization_code_if_allowed(
    uid: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scopes: List[str],
    code_challenge: str,
) -> Tuple[Dict[str, Any], str]:
    """Atomically fence deletion admission with both OAuth consent writes."""
    deterministic_grant_id = f"{uid}:{client_id}:{hash_secret(resource)[:16]}"
    deletion_ref = db.collection("account_deletions").document(uid)
    grant_ref = db.collection("mcp_oauth_grants").document(deterministic_grant_id)
    raw_code = "omi_code_" + secrets.token_urlsafe(32)
    code_ref = db.collection("mcp_oauth_authorization_codes").document(hash_secret(raw_code))
    transaction = db.transaction()

    @_typed_transactional
    def _create(transaction: Any) -> Tuple[Dict[str, Any], str]:
        deletion_doc = deletion_ref.get(transaction=transaction)
        deletion_data = _typed_doc(deletion_doc) if deletion_doc.exists else {}
        deletion_status = normalize_account_deletion_status(
            marker_exists=deletion_doc.exists,
            raw_status=deletion_data.get("wipe_status"),
        )
        if account_deletion_blocks_access(deletion_status):
            raise AccountDeletionAccessBlocked(deletion_status or "unknown")

        now = _now()
        grant_doc = grant_ref.get(transaction=transaction)
        current_grant_ref, existing, grant_data = _grant_write(
            uid, client_id, resource, scopes, ref=grant_ref, doc=grant_doc, now=now
        )
        memory_grant_ref = _oauth_memory_grant_ref(uid)
        memory_grant_doc = memory_grant_ref.get(transaction=transaction)
        code_data = _authorization_code_write(
            uid,
            current_grant_ref.id,
            client_id,
            redirect_uri,
            resource,
            scopes,
            code_challenge,
            now=now,
        )
        transaction.set(current_grant_ref, grant_data, merge=True)
        _create_oauth_memory_grant_if_absent(transaction, memory_grant_ref, memory_grant_doc, grant_data)
        transaction.set(code_ref, code_data)
        return {**existing, **grant_data}, raw_code

    return _create(transaction)


def consume_authorization_code(
    code: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    code_verifier: str,
) -> Optional[Dict[str, Any]]:
    ref = db.collection("mcp_oauth_authorization_codes").document(hash_secret(code))
    transaction = db.transaction()

    @_typed_transactional
    def _consume(transaction: Any) -> Optional[Dict[str, Any]]:
        doc = ref.get(transaction=transaction)
        if not doc.exists:
            return None
        data: Dict[str, Any] = _typed_doc(doc)
        expires_at = data.get("expires_at")
        if data.get("consumed_at") or (expires_at and expires_at <= _now()):
            return None
        if (
            data.get("client_id") != client_id
            or data.get("redirect_uri") != redirect_uri
            or data.get("resource") != resource
        ):
            return None
        try:
            verifier_challenge = pkce_s256(code_verifier)
        except ValueError:
            return None
        if data.get("code_challenge_method") != "S256" or not hmac.compare_digest(
            data.get("code_challenge") or "", verifier_challenge
        ):
            return None
        transaction.update(ref, {"consumed_at": _now()})
        return data

    return _consume(transaction)


def exchange_authorization_code_for_tokens(
    code: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    code_verifier: str,
) -> Optional[Dict[str, Any]]:
    code_ref = db.collection("mcp_oauth_authorization_codes").document(hash_secret(code))
    transaction = db.transaction()

    @_typed_transactional
    def _exchange(transaction: Any) -> Optional[Dict[str, Any]]:
        code_doc = code_ref.get(transaction=transaction)
        if not code_doc.exists:
            return None
        code_data: Dict[str, Any] = _typed_doc(code_doc)
        expires_at = code_data.get("expires_at")
        if code_data.get("consumed_at") or (expires_at and expires_at <= _now()):
            return None
        if (
            code_data.get("client_id") != client_id
            or code_data.get("redirect_uri") != redirect_uri
            or code_data.get("resource") != resource
        ):
            return None
        try:
            verifier_challenge = pkce_s256(code_verifier)
        except ValueError:
            return None
        if code_data.get("code_challenge_method") != "S256" or not hmac.compare_digest(
            code_data.get("code_challenge") or "", verifier_challenge
        ):
            return None
        grant_ref = db.collection("mcp_oauth_grants").document(code_data.get("grant_id"))
        grant_doc = grant_ref.get(transaction=transaction)
        grant: Optional[Dict[str, Any]] = _typed_doc(grant_doc) if grant_doc.exists else None
        if not grant or grant.get("revoked_at") or grant.get("status") == "revoked":
            return None
        grant.setdefault("id", code_data.get("grant_id"))
        access_token, refresh_token, access_ref, access_data, refresh_ref, refresh_data, _ = _build_token_pair_writes(
            grant, code_data.get("scopes") or []
        )
        now = _now()
        transaction.update(code_ref, {"consumed_at": now})
        transaction.set(access_ref, access_data)
        transaction.set(refresh_ref, refresh_data)
        transaction.set(grant_ref, {"last_used_at": now}, merge=True)
        return _token_pair_response(access_token, refresh_token, access_data["scopes"])

    return _exchange(transaction)


def _new_access_token() -> str:
    return "omi_oat_" + secrets.token_urlsafe(32)


def _new_refresh_token() -> str:
    return "omi_ort_" + secrets.token_urlsafe(48)


def issue_token_pair(
    grant: Dict[str, Any], scopes: Optional[List[str]] = None, token_family_id: Optional[str] = None
) -> Dict[str, Any]:
    access_token, refresh_token, access_ref, access_data, refresh_ref, refresh_data, grant_ref = (
        _build_token_pair_writes(grant, scopes, token_family_id)
    )
    access_ref.set(access_data)
    refresh_ref.set(refresh_data)
    grant_ref.set({"last_used_at": _now()}, merge=True)
    return _token_pair_response(access_token, refresh_token, access_data["scopes"])


def _build_token_pair_writes(
    grant: Dict[str, Any],
    scopes: Optional[List[str]] = None,
    token_family_id: Optional[str] = None,
) -> Tuple[str, str, Any, OAuthAccessTokenDict, Any, OAuthRefreshTokenDict, Any]:
    now = _now()
    issued_scopes: List[str] = sorted(set(scopes or grant.get("scopes") or []))
    access_token = _new_access_token()
    refresh_token = _new_refresh_token()
    access_id = str(uuid.uuid4())
    refresh_id = str(uuid.uuid4())
    family_id = token_family_id or str(uuid.uuid4())
    access_ref = db.collection("mcp_oauth_access_tokens").document(hash_secret(access_token))
    refresh_ref = db.collection("mcp_oauth_refresh_tokens").document(hash_secret(refresh_token))
    grant_ref = db.collection("mcp_oauth_grants").document(grant["id"])
    access_data: OAuthAccessTokenDict = {
        "id": access_id,
        "grant_id": grant["id"],
        "uid": grant["uid"],
        "client_id": grant["client_id"],
        "resource": grant["resource"],
        "scopes": issued_scopes,
        "created_at": now,
        "expires_at": now + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS),
        "revoked_at": None,
    }
    refresh_data: OAuthRefreshTokenDict = {
        "id": refresh_id,
        "grant_id": grant["id"],
        "token_family_id": family_id,
        "uid": grant["uid"],
        "client_id": grant["client_id"],
        "resource": grant["resource"],
        "scopes": issued_scopes,
        "created_at": now,
        "expires_at": now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
        "used_at": None,
        "replaced_by": None,
        "revoked_at": None,
        "replay_detected_at": None,
    }
    return access_token, refresh_token, access_ref, access_data, refresh_ref, refresh_data, grant_ref


def _token_pair_response(access_token: str, refresh_token: str, scopes: List[str]) -> Dict[str, Any]:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
        "scope": " ".join(scopes),
    }


def get_active_grant(grant_id: str) -> Optional[Dict[str, Any]]:
    if not grant_id.strip():
        return None
    doc = db.collection("mcp_oauth_grants").document(grant_id).get()
    if not doc.exists:
        return None
    data: Dict[str, Any] = _typed_doc(doc)
    if data.get("revoked_at") or data.get("status") == "revoked":
        return None
    return data


def _valid_oauth_scopes(value: object) -> Optional[List[str]]:
    if not isinstance(value, list) or not value:
        return None
    scopes = cast(List[Any], value)
    if any(not isinstance(scope, str) or not scope or scope not in SUPPORTED_SCOPES for scope in scopes):
        return None
    if len(scopes) != len(set(scopes)):
        return None
    return cast(List[str], scopes)


def _nonempty_string(data: Dict[str, Any], field: str) -> Optional[str]:
    value = data.get(field)
    return value if isinstance(value, str) and value.strip() else None


def _is_unexpired(value: object, now: datetime) -> bool:
    if not isinstance(value, datetime):
        return False
    try:
        return value > now
    except (TypeError, ValueError):
        return False


def _validated_access_token_identity(
    data: Dict[str, Any], grant: Dict[str, Any], resource: str, *, now: datetime
) -> Optional[Dict[str, Any]]:
    uid = _nonempty_string(data, "uid")
    client_id = _nonempty_string(data, "client_id")
    grant_id = _nonempty_string(data, "grant_id")
    token_resource = _nonempty_string(data, "resource")
    token_scopes = _valid_oauth_scopes(data.get("scopes"))
    grant_uid = _nonempty_string(grant, "uid")
    grant_client_id = _nonempty_string(grant, "client_id")
    persisted_grant_id = _nonempty_string(grant, "id")
    grant_resource = _nonempty_string(grant, "resource")
    grant_scopes = _valid_oauth_scopes(grant.get("scopes"))
    grant_expires_at = grant.get("expires_at")
    if (
        uid is None
        or client_id is None
        or grant_id is None
        or token_resource is None
        or token_scopes is None
        or grant_uid is None
        or grant_client_id is None
        or persisted_grant_id is None
        or grant_resource is None
        or grant_scopes is None
        or "revoked_at" not in data
        or data.get("revoked_at") is not None
        or not _is_unexpired(data.get("expires_at"), now)
        or grant.get("status") != "active"
        or "revoked_at" not in grant
        or grant.get("revoked_at") is not None
        or (grant_expires_at is not None and not _is_unexpired(grant_expires_at, now))
        or token_resource != resource
        or uid != grant_uid
        or client_id != grant_client_id
        or grant_id != persisted_grant_id
        or token_resource != grant_resource
        or not set(token_scopes).issubset(grant_scopes)
    ):
        return None
    return {
        "uid": uid,
        "auth_type": "oauth",
        "client_id": client_id,
        "resource": token_resource,
        "scopes": token_scopes,
        "grant_id": grant_id,
    }


def validate_access_token(access_token: str, resource: str = MCP_RESOURCE_URL) -> Optional[Dict[str, Any]]:
    doc = db.collection("mcp_oauth_access_tokens").document(hash_secret(access_token)).get()
    if not doc.exists:
        return None
    data: Dict[str, Any] = _typed_doc(doc)
    grant_id = _nonempty_string(data, "grant_id")
    if grant_id is None:
        return None
    grant = get_active_grant(grant_id)
    if not grant:
        return None
    identity = _validated_access_token_identity(data, grant, resource, now=_now())
    if identity is None:
        return None
    _ensure_oauth_memory_grant(grant)
    db.collection("mcp_oauth_grants").document(grant_id).set({"last_used_at": _now()}, merge=True)
    return identity


def rotate_refresh_token(
    refresh_token: str, client_id: str, resource: str, scope: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    ref = db.collection("mcp_oauth_refresh_tokens").document(hash_secret(refresh_token))
    transaction = db.transaction()
    replay_grant_id: Optional[str] = None

    @_typed_transactional
    def _rotate(transaction: Any) -> Optional[Dict[str, Any]]:
        nonlocal replay_grant_id
        doc = ref.get(transaction=transaction)
        if not doc.exists:
            return None
        data: Dict[str, Any] = _typed_doc(doc)
        now = _now()
        expires_at = data.get("expires_at")
        grant_ref = db.collection("mcp_oauth_grants").document(data.get("grant_id"))
        grant_doc = grant_ref.get(transaction=transaction)
        grant: Optional[Dict[str, Any]] = _typed_doc(grant_doc) if grant_doc.exists else None
        if (
            data.get("client_id") != client_id
            or data.get("resource") != resource
            or data.get("revoked_at")
            or (expires_at and expires_at <= now)
            or not grant
            or grant.get("revoked_at")
            or grant.get("status") == "revoked"
        ):
            return None
        grant.setdefault("id", data.get("grant_id"))
        if data.get("used_at") or data.get("replaced_by"):
            replay_grant_id = data.get("grant_id")
            transaction.set(grant_ref, {"revoked_at": now, "status": "revoked", "replay_detected": True}, merge=True)
            transaction.set(ref, {"replay_detected_at": now, "revoked_at": now}, merge=True)
            return None
        try:
            requested_scopes: List[str] = (
                normalize_scopes(scope, {"allowed_scopes": data.get("scopes")}) if scope else data.get("scopes") or []
            )
        except ValueError:
            return None
        if not set(requested_scopes).issubset(set(data.get("scopes") or [])):
            return None
        (
            access_token,
            new_refresh_token,
            access_ref,
            access_data,
            refresh_ref,
            refresh_data,
            _,
        ) = _build_token_pair_writes(grant, requested_scopes, data.get("token_family_id"))
        transaction.set(access_ref, access_data)
        transaction.set(refresh_ref, refresh_data)
        transaction.update(ref, {"used_at": now, "replaced_by": hash_secret(new_refresh_token)})
        transaction.set(grant_ref, {"last_used_at": now}, merge=True)
        return _token_pair_response(access_token, new_refresh_token, requested_scopes)

    token_pair: Optional[Dict[str, Any]] = _rotate(transaction)
    if replay_grant_id:
        revoke_grant(replay_grant_id, replay_detected=True)
    return token_pair


def revoke_grant(grant_id: str, replay_detected: bool = False) -> None:
    now = _now()
    db.collection("mcp_oauth_grants").document(grant_id).set(
        {"revoked_at": now, "status": "revoked", "replay_detected": replay_detected}, merge=True
    )
    for collection_name in ("mcp_oauth_access_tokens", "mcp_oauth_refresh_tokens"):
        docs = db.collection(collection_name).where("grant_id", "==", grant_id).stream()
        for doc in docs:
            doc.reference.set({"revoked_at": now}, merge=True)


def list_user_grants(uid: str) -> List[Dict[str, Any]]:
    docs = db.collection("mcp_oauth_grants").where("uid", "==", uid).stream()
    grants: List[Dict[str, Any]] = []
    for doc in docs:
        data: Dict[str, Any] = _typed_doc(doc)
        data.setdefault("id", doc.id)
        grants.append(data)
    grants.sort(
        key=lambda grant: grant.get("updated_at")
        or grant.get("created_at")
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return grants


def revoke_user_grant(uid: str, grant_id: str) -> bool:
    doc = db.collection("mcp_oauth_grants").document(grant_id).get()
    if not doc.exists:
        return False
    data: Dict[str, Any] = _typed_doc(doc)
    if data.get("uid") != uid:
        return False
    revoke_grant(grant_id)
    return True


def delete_user_oauth_credentials(uid: str) -> None:
    """Revoke and remove every OAuth credential and authorization code for a user."""
    grants = list(db.collection("mcp_oauth_grants").where("uid", "==", uid).stream())
    for grant in grants:
        grant_id = grant.id
        revoke_grant(grant_id)
        for collection_name in ("mcp_oauth_access_tokens", "mcp_oauth_refresh_tokens"):
            for token in db.collection(collection_name).where("grant_id", "==", grant_id).stream():
                token.reference.delete()
        grant.reference.delete()
    codes = list(db.collection("mcp_oauth_authorization_codes").where("uid", "==", uid).stream())
    for code in codes:
        code.reference.delete()
