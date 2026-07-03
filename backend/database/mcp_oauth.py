import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import re
from urllib.parse import unquote, urlsplit

from google.cloud import firestore

from database._client import db

MCP_RESOURCE_URL = os.getenv("MCP_RESOURCE_URL", "https://api.omi.me/v1/mcp/sse")
DEFAULT_CLIENT_ID = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_ID", "omi")
DEFAULT_CLIENT_NAME = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_NAME", "ChatGPT")
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
CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX = "https://chatgpt.com/connector/oauth/"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _csv_env(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


def _csv_values(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _secret_hash_from_config(config: dict) -> str:
    secret_hash = config.get("client_secret_hash") or config.get("secret_hash") or ""
    secret_hash_env = config.get("client_secret_hash_env") or config.get("secret_hash_env")
    if secret_hash_env:
        secret_hash = os.getenv(str(secret_hash_env), secret_hash)
    secret_env = config.get("client_secret_env") or config.get("secret_env")
    secret = os.getenv(str(secret_env), "") if secret_env else config.get("client_secret") or config.get("secret") or ""
    return str(secret_hash or (hash_secret(str(secret)) if secret else ""))


def _client_from_config(config: dict) -> Optional[dict]:
    client_id = str(config.get("client_id") or config.get("id") or "").strip()
    if not client_id:
        return None
    auth_method = config.get("token_endpoint_auth_method")
    if auth_method is None:
        public_value = config.get("public")
        if public_value is not None and not isinstance(public_value, bool):
            return None
        client_type = str(config.get("client_type") or "").lower()
        if client_type and client_type not in ("public", "confidential"):
            return None
        auth_method = "none" if public_value is True or client_type == "public" else "client_secret_post"
    auth_method = str(auth_method)
    if auth_method not in SUPPORTED_TOKEN_AUTH_METHODS:
        return None
    client = {
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


def _env_clients() -> dict[str, dict]:
    raw_clients = os.getenv("MCP_OAUTH_CLIENTS_JSON", "")
    if not raw_clients:
        return {}
    try:
        parsed = json.loads(raw_clients)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        entries = []
        for client_id, config in parsed.items():
            if isinstance(config, dict):
                entries.append({"client_id": client_id, **config})
    elif isinstance(parsed, list):
        entries = [config for config in parsed if isinstance(config, dict)]
    else:
        entries = []
    clients = {}
    for entry in entries:
        client = _client_from_config(entry)
        if client:
            clients[client["id"]] = client
    return clients


def _legacy_chatgpt_client() -> dict:
    secret = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_SECRET", "")
    secret_hash = os.getenv("MCP_OAUTH_CHATGPT_CLIENT_SECRET_SHA256", "")
    auth_method = os.getenv("MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD", "").strip()
    if not auth_method and DEFAULT_CLIENT_ID in PUBLIC_CHATGPT_CLIENT_IDS:
        auth_method = "none"
    auth_method = auth_method or "client_secret_post"
    if auth_method not in SUPPORTED_TOKEN_AUTH_METHODS:
        auth_method = "client_secret_post"
    return {
        "id": DEFAULT_CLIENT_ID,
        "name": DEFAULT_CLIENT_NAME,
        "registration_mode": "legacy_env",
        "allowed_redirect_uris": _csv_env("MCP_OAUTH_CHATGPT_REDIRECT_URIS"),
        "allowed_redirect_uri_prefixes": (
            [CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX] if DEFAULT_CLIENT_ID in PUBLIC_CHATGPT_CLIENT_IDS else []
        ),
        "allowed_resources": [MCP_RESOURCE_URL],
        "allowed_scopes": SUPPORTED_SCOPES,
        "token_endpoint_auth_method": auth_method,
        "client_secret_hash": secret_hash
        or (hash_secret(secret) if secret and auth_method == "client_secret_post" else ""),
        "disabled_at": None,
    }


def _public_redirect_uris() -> list[str]:
    return _csv_env("MCP_OAUTH_PUBLIC_REDIRECT_URIS") or _csv_env("MCP_OAUTH_CHATGPT_REDIRECT_URIS")


def _default_public_client() -> Optional[dict]:
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


def _finalize_client(client: Optional[dict]) -> Optional[dict]:
    """Apply built-in provider defaults to configured and generated clients."""
    if not client:
        return None
    if client.get("id") not in PUBLIC_CHATGPT_CLIENT_IDS:
        return client
    prefixes = list(client.get("allowed_redirect_uri_prefixes") or [])
    if CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX not in prefixes:
        prefixes.append(CHATGPT_CONNECTOR_REDIRECT_URI_PREFIX)
    return {**client, "allowed_redirect_uri_prefixes": prefixes}


def get_client(client_id: str) -> Optional[dict]:
    client = None
    doc = db.collection("mcp_oauth_clients").document(client_id).get()
    if doc.exists:
        data = doc.to_dict() or {}
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
            client = _legacy_chatgpt_client()
            client["id"] = client_id
            client["token_endpoint_auth_method"] = "none"
            client["client_secret_hash"] = ""
        elif client_id == DEFAULT_PUBLIC_CLIENT_ID:
            client = _default_public_client()
    return _finalize_client(client)


def verify_client_secret(client: dict, client_secret: Optional[str]) -> bool:
    if client.get("token_endpoint_auth_method") != "client_secret_post":
        return False
    expected_hash = client.get("client_secret_hash") or ""
    if not expected_hash or not client_secret:
        return False
    return hmac.compare_digest(expected_hash, hash_secret(client_secret))


def verify_client_auth(client: dict, client_secret: Optional[str]) -> bool:
    auth_method = client.get("token_endpoint_auth_method") or "client_secret_post"
    if auth_method == "none":
        return not client_secret
    if auth_method == "client_secret_post":
        return verify_client_secret(client, client_secret)
    return False


def token_endpoint_auth_methods_supported() -> list[str]:
    return list(SUPPORTED_TOKEN_AUTH_METHODS)


def validate_redirect_uri(client: dict, redirect_uri: str) -> bool:
    parsed = urlsplit(redirect_uri)
    if parsed.fragment or parsed.query:
        return False
    if redirect_uri in set(client.get("allowed_redirect_uris") or []):
        return True

    for prefix in client.get("allowed_redirect_uri_prefixes") or []:
        if not redirect_uri.startswith(prefix):
            continue
        prefix_parsed = urlsplit(prefix)
        if parsed.scheme != "https" or parsed.scheme != prefix_parsed.scheme or parsed.netloc != prefix_parsed.netloc:
            continue
        if not parsed.path.startswith(prefix_parsed.path):
            continue
        segments = parsed.path.split("/")
        decoded_segments = [unquote(segment) for segment in segments]
        if any(segment in {".", ".."} for segment in segments + decoded_segments):
            continue
        return True
    return False


def validate_resource(client: dict, resource: str) -> bool:
    return resource in set(client.get("allowed_resources") or [])


def normalize_scopes(scope: Optional[str], client: Optional[dict] = None) -> list[str]:
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


def create_or_update_grant(uid: str, client_id: str, resource: str, scopes: list[str]) -> dict:
    deterministic_grant_id = f"{uid}:{client_id}:{hash_secret(resource)[:16]}"
    now = _now()
    ref = db.collection("mcp_oauth_grants").document(deterministic_grant_id)
    doc = ref.get()
    existing = doc.to_dict() if doc.exists else {}
    if existing and (existing.get("revoked_at") or existing.get("status") == "revoked"):
        ref = db.collection("mcp_oauth_grants").document(f"{deterministic_grant_id}:{uuid.uuid4()}")
        doc = ref.get()
        existing = {}
    existing_scopes = set(existing.get("scopes") or [])
    merged_scopes = sorted(existing_scopes.union(scopes))
    data = {
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
    if not doc.exists:
        data["created_at"] = now
    ref.set(data, merge=True)
    return {**existing, **data}


def issue_authorization_code(
    uid: str,
    grant_id: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scopes: list[str],
    code_challenge: str,
) -> str:
    raw_code = "omi_code_" + secrets.token_urlsafe(32)
    now = _now()
    db.collection("mcp_oauth_authorization_codes").document(hash_secret(raw_code)).set(
        {
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
    )
    return raw_code


def consume_authorization_code(
    code: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    code_verifier: str,
) -> Optional[dict]:
    ref = db.collection("mcp_oauth_authorization_codes").document(hash_secret(code))
    transaction = db.transaction()

    @firestore.transactional
    def _consume(transaction):
        doc = ref.get(transaction=transaction)
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
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
) -> Optional[dict]:
    code_ref = db.collection("mcp_oauth_authorization_codes").document(hash_secret(code))
    transaction = db.transaction()

    @firestore.transactional
    def _exchange(transaction):
        code_doc = code_ref.get(transaction=transaction)
        if not code_doc.exists:
            return None
        code_data = code_doc.to_dict() or {}
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
        grant = grant_doc.to_dict() if grant_doc.exists else None
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


def issue_token_pair(grant: dict, scopes: Optional[list[str]] = None, token_family_id: Optional[str] = None) -> dict:
    access_token, refresh_token, access_ref, access_data, refresh_ref, refresh_data, grant_ref = (
        _build_token_pair_writes(grant, scopes, token_family_id)
    )
    access_ref.set(access_data)
    refresh_ref.set(refresh_data)
    grant_ref.set({"last_used_at": _now()}, merge=True)
    return _token_pair_response(access_token, refresh_token, access_data["scopes"])


def _build_token_pair_writes(grant: dict, scopes: Optional[list[str]] = None, token_family_id: Optional[str] = None):
    now = _now()
    issued_scopes = sorted(set(scopes or grant.get("scopes") or []))
    access_token = _new_access_token()
    refresh_token = _new_refresh_token()
    access_id = str(uuid.uuid4())
    refresh_id = str(uuid.uuid4())
    family_id = token_family_id or str(uuid.uuid4())
    access_ref = db.collection("mcp_oauth_access_tokens").document(hash_secret(access_token))
    refresh_ref = db.collection("mcp_oauth_refresh_tokens").document(hash_secret(refresh_token))
    grant_ref = db.collection("mcp_oauth_grants").document(grant["id"])
    access_data = {
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
    refresh_data = {
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


def _token_pair_response(access_token: str, refresh_token: str, scopes: list[str]) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
        "scope": " ".join(scopes),
    }


def get_active_grant(grant_id: str) -> Optional[dict]:
    doc = db.collection("mcp_oauth_grants").document(grant_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if data.get("revoked_at") or data.get("status") == "revoked":
        return None
    data.setdefault("id", grant_id)
    return data


def validate_access_token(access_token: str, resource: str = MCP_RESOURCE_URL) -> Optional[dict]:
    doc = db.collection("mcp_oauth_access_tokens").document(hash_secret(access_token)).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    expires_at = data.get("expires_at")
    if data.get("revoked_at") or data.get("resource") != resource or (expires_at and expires_at <= _now()):
        return None
    grant = get_active_grant(data.get("grant_id"))
    if not grant:
        return None
    db.collection("mcp_oauth_grants").document(data["grant_id"]).set({"last_used_at": _now()}, merge=True)
    return {
        "uid": data.get("uid"),
        "auth_type": "oauth",
        "client_id": data.get("client_id"),
        "resource": data.get("resource"),
        "scopes": data.get("scopes") or [],
        "grant_id": data.get("grant_id"),
    }


def rotate_refresh_token(
    refresh_token: str, client_id: str, resource: str, scope: Optional[str] = None
) -> Optional[dict]:
    ref = db.collection("mcp_oauth_refresh_tokens").document(hash_secret(refresh_token))
    transaction = db.transaction()
    replay_grant_id = None

    @firestore.transactional
    def _rotate(transaction):
        nonlocal replay_grant_id
        doc = ref.get(transaction=transaction)
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        now = _now()
        expires_at = data.get("expires_at")
        grant_ref = db.collection("mcp_oauth_grants").document(data.get("grant_id"))
        grant_doc = grant_ref.get(transaction=transaction)
        grant = grant_doc.to_dict() if grant_doc.exists else None
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
            requested_scopes = (
                normalize_scopes(scope, {"allowed_scopes": data.get("scopes")}) if scope else data.get("scopes") or []
            )
        except ValueError:
            return None
        if not set(requested_scopes).issubset(set(data.get("scopes") or [])):
            return None
        access_token, new_refresh_token, access_ref, access_data, refresh_ref, refresh_data, _ = (
            _build_token_pair_writes(grant, requested_scopes, data.get("token_family_id"))
        )
        transaction.set(access_ref, access_data)
        transaction.set(refresh_ref, refresh_data)
        transaction.update(ref, {"used_at": now, "replaced_by": hash_secret(new_refresh_token)})
        transaction.set(grant_ref, {"last_used_at": now}, merge=True)
        return _token_pair_response(access_token, new_refresh_token, requested_scopes)

    token_pair = _rotate(transaction)
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


def list_user_grants(uid: str) -> list[dict]:
    docs = db.collection("mcp_oauth_grants").where("uid", "==", uid).stream()
    grants = []
    for doc in docs:
        data = doc.to_dict() or {}
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
    data = doc.to_dict() or {}
    if data.get("uid") != uid:
        return False
    revoke_grant(grant_id)
    return True
