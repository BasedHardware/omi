import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_private_key(value: str) -> Ed25519PrivateKey:
    if "BEGIN" in value:
        key = serialization.load_pem_private_key(value.encode("utf-8"), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("AMBIENT_POLICY_PRIVATE_KEY must be an Ed25519 private key")
        return key
    raw = base64.b64decode(value)
    if len(raw) == 32:
        return Ed25519PrivateKey.from_private_bytes(raw)
    key = serialization.load_der_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("AMBIENT_POLICY_PRIVATE_KEY must be an Ed25519 private key")
    return key


def _load_public_key(value: str) -> Ed25519PublicKey:
    if "BEGIN" in value:
        key = serialization.load_pem_public_key(value.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("AMBIENT_POLICY_PUBLIC_KEY must be an Ed25519 public key")
        return key
    raw = base64.b64decode(value)
    try:
        key = serialization.load_der_public_key(raw)
        if isinstance(key, Ed25519PublicKey):
            return key
    except ValueError:
        pass
    if len(raw) == 32:
        return Ed25519PublicKey.from_public_bytes(raw)
    raise ValueError("AMBIENT_POLICY_PUBLIC_KEY must be Ed25519 raw, PEM, or DER")


def public_key_der_b64(public_key: Ed25519PublicKey | None = None) -> str:
    key = public_key or get_private_key().public_key()
    der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def key_fingerprint(public_key_b64: str | None = None) -> str:
    public_b64 = public_key_b64 or public_key_der_b64()
    digest = hashlib.sha256(base64.b64decode(public_b64)).hexdigest()
    return ":".join(digest[i : i + 2] for i in range(0, 16, 2))


def get_private_key() -> Ed25519PrivateKey:
    configured = os.getenv("AMBIENT_POLICY_PRIVATE_KEY")
    if configured:
        return _load_private_key(configured)
    return _dev_private_key()


def get_public_key_b64() -> str:
    configured = os.getenv("AMBIENT_POLICY_PUBLIC_KEY")
    if configured:
        return public_key_der_b64(_load_public_key(configured))
    return public_key_der_b64()


def get_key_id() -> str:
    return os.getenv("AMBIENT_POLICY_KEY_ID", "dev-key-1")


def sign_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
    payload_json = canonical_json(payload)
    signature = get_private_key().sign(payload_json.encode("utf-8"))
    return payload_json, b64url(signature)


def verify_payload(payload_json: str, signature: str, public_key_b64: str | None = None) -> bool:
    public_key = _load_public_key(public_key_b64 or get_public_key_b64())
    public_key.verify(b64url_decode(signature), payload_json.encode("utf-8"))
    return True


def validate_signed_policy(
    payload_json: str,
    signature: str,
    public_key_b64: str | None = None,
    last_sequence: int = 0,
    now: datetime | None = None,
) -> Dict[str, Any]:
    try:
        verify_payload(payload_json, signature, public_key_b64)
    except Exception:
        return {"accepted": False, "reason": "signature_invalid"}
    payload = json.loads(payload_json)
    now = now or datetime.now(timezone.utc)
    valid_until = datetime.fromisoformat(payload["valid_until"].replace("Z", "+00:00"))
    issued_at = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00"))
    if valid_until <= now:
        return {"accepted": False, "reason": "expired"}
    if issued_at > now.replace(microsecond=0):
        return {"accepted": False, "reason": "issued_in_future"}
    if int(payload["sequence"]) <= last_sequence:
        return {"accepted": False, "reason": "replayed_sequence"}
    return {"accepted": True, "reason": "ok", "payload": payload}


def _dev_private_key() -> Ed25519PrivateKey:
    seed = hashlib.sha256(b"ambient-second-brain-controller-dev-key").digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def generate_key_pair() -> Dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "AMBIENT_POLICY_PRIVATE_KEY": base64.b64encode(private_raw).decode("ascii"),
        "AMBIENT_POLICY_PUBLIC_KEY": base64.b64encode(public_der).decode("ascii"),
    }
