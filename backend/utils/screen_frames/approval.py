"""Approval minting and verification — the boundary in front of the writer.

Structured behind one `ScreenFrameSigner` interface so switching from HMAC to
Cloud KMS is a config change (set `SCREEN_FRAME_KMS_KEY`), not a rewrite
(contract §5). The approval object this module produces is a compact,
signed, base64url token; `ScreenFrameApprovalClaims` itself never appears in
any response model and never leaves the process.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from uuid import uuid4

from models.screen_frame import ScreenFrameApprovalClaims, ScreenFrameJudgement

logger = logging.getLogger(__name__)

_HMAC_ALG = "HS256-screen-frame"
_KMS_ALG = "KMS-EC256-screen-frame"

APPROVAL_MAX_TTL_SECONDS = 600  # <= 10 minutes, per contract §5
_CLOCK_SKEW_SLACK_SECONDS = 30


class ApprovalSignatureError(Exception):
    """The approval token is missing, malformed, expired, or fails signature verification.

    The writer (utils/screen_frames/writer.py) treats any of these as an
    unusable approval — it must never write bytes when this is raised.
    """


@runtime_checkable
class ScreenFrameSigner(Protocol):
    alg: str

    def sign(self, signing_input: bytes) -> bytes: ...

    def verify(self, signing_input: bytes, signature: bytes) -> bool: ...


class HmacSigner:
    """HMAC-SHA256 signer — the default, used whenever SCREEN_FRAME_KMS_KEY is unset."""

    alg = _HMAC_ALG

    def __init__(self, secret: str):
        if not secret:
            raise ApprovalSignatureError("SCREEN_FRAME_SIGNING_SECRET is not configured")
        self._key = secret.encode("utf-8")

    def sign(self, signing_input: bytes) -> bytes:
        return hmac.new(self._key, signing_input, hashlib.sha256).digest()

    def verify(self, signing_input: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(signing_input), signature)


class KmsSigner:
    """Cloud KMS asymmetric-signing backend (EC_SIGN_P256_SHA256), used when
    SCREEN_FRAME_KMS_KEY is set.

    DEPLOY PREREQUISITE (contract §5): the writer must run under a separate
    service account with write access to BUCKET_SCREEN_FRAMES only, granted
    only to that writer identity — distinct from whatever identity mints
    approvals. This class does not and cannot provision that IAM split; it
    is infrastructure that must exist before this signer is used for real
    traffic, not something this PR can create.

    UNTESTED in this change: the `google-cloud-kms` client library is not
    installed in the environment this was built in (no package, no
    credentials). The HMAC-vs-KMS *dispatch* (`get_signer()` picking this
    class when the env var is set) is unit-tested with the KMS client
    mocked; the actual sign/verify RPCs against a real Cloud KMS key are
    not exercised anywhere in this test suite.
    """

    alg = _KMS_ALG

    def __init__(self, key_resource_name: str):
        self._key_resource_name = key_resource_name
        self._client = None
        self._public_key_pem: str | None = None
        self._lock = threading.Lock()

    def _get_client(self):
        if self._client is None:
            # google-cloud-kms is an optional dependency: only the KMS path needs
            # it, and it is not installed in every environment (e.g. this repo's
            # hermetic test env), so pyright cannot resolve the symbol there.
            from google.cloud import kms_v1  # type: ignore[reportAttributeAccessIssue]

            self._client = kms_v1.KeyManagementServiceClient()
        return self._client

    def sign(self, signing_input: bytes) -> bytes:
        client = self._get_client()
        digest = hashlib.sha256(signing_input).digest()
        response = client.asymmetric_sign(request={"name": self._key_resource_name, "digest": {"sha256": digest}})
        return bytes(response.signature)

    def _get_public_key_pem(self) -> str:
        if self._public_key_pem is None:
            with self._lock:
                if self._public_key_pem is None:
                    client = self._get_client()
                    response = client.get_public_key(request={"name": self._key_resource_name})
                    self._public_key_pem = str(response.pem)
        return self._public_key_pem

    def verify(self, signing_input: bytes, signature: bytes) -> bool:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

        public_key = serialization.load_pem_public_key(self._get_public_key_pem().encode("utf-8"))
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            # Our own keys are always EC_SIGN_P256_SHA256; anything else means
            # SCREEN_FRAME_KMS_KEY points at the wrong kind of key. Fail closed
            # rather than guess at a different verify() signature.
            logger.error("screen_frame KMS public key is not an EC key: %s", type(public_key).__name__)
            return False
        digest = hashlib.sha256(signing_input).digest()
        try:
            public_key.verify(signature, digest, ec.ECDSA(asym_utils.Prehashed(hashes.SHA256())))
        except InvalidSignature:
            return False
        return True


_signer_lock = threading.Lock()
_signer_instance: ScreenFrameSigner | None = None


def _build_signer() -> ScreenFrameSigner:
    kms_key = (os.getenv("SCREEN_FRAME_KMS_KEY") or "").strip()
    if kms_key:
        return KmsSigner(kms_key)
    secret = (os.getenv("SCREEN_FRAME_SIGNING_SECRET") or "").strip()
    return HmacSigner(secret)


def get_signer() -> ScreenFrameSigner:
    global _signer_instance
    if _signer_instance is None:
        with _signer_lock:
            if _signer_instance is None:
                _signer_instance = _build_signer()
    return _signer_instance


def reset_signer_cache() -> None:
    """Test-only: force the next get_signer() call to rebuild from current env."""
    global _signer_instance
    _signer_instance = None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")


def mint_approval(claims: ScreenFrameApprovalClaims, *, signer: ScreenFrameSigner | None = None) -> str:
    """Sign an already-built claims object into a compact approval token."""
    active_signer = signer or get_signer()
    header_b64 = _b64url_encode(_canonical_json({"alg": active_signer.alg}))
    claims_b64 = _b64url_encode(_canonical_json(json.loads(claims.model_dump_json())))
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    signature_b64 = _b64url_encode(active_signer.sign(signing_input))
    return f"{header_b64}.{claims_b64}.{signature_b64}"


def verify_approval(token: str, *, signer: ScreenFrameSigner | None = None) -> ScreenFrameApprovalClaims:
    """Verify signature, structure, and expiry. Does NOT check jti consumption —
    that is the writer's job (atomic Redis SETNX), kept out of this pure
    verification step so it can be unit-tested without Redis.
    """
    active_signer = signer or get_signer()
    try:
        header_b64, claims_b64, signature_b64 = token.split(".")
    except ValueError as error:
        raise ApprovalSignatureError("malformed_token") from error

    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception as error:
        raise ApprovalSignatureError("malformed_token") from error
    if not isinstance(header, dict) or header.get("alg") != active_signer.alg:
        raise ApprovalSignatureError("alg_mismatch")

    try:
        signature = _b64url_decode(signature_b64)
    except Exception as error:
        raise ApprovalSignatureError("malformed_token") from error

    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    if not active_signer.verify(signing_input, signature):
        raise ApprovalSignatureError("bad_signature")

    try:
        claims_dict = json.loads(_b64url_decode(claims_b64))
        claims = ScreenFrameApprovalClaims.model_validate(claims_dict)
    except Exception as error:
        raise ApprovalSignatureError("malformed_claims") from error

    now = datetime.now(timezone.utc)
    if claims.expires_at <= now:
        raise ApprovalSignatureError("expired")
    if claims.issued_at > now + timedelta(seconds=_CLOCK_SKEW_SLACK_SECONDS):
        raise ApprovalSignatureError("not_yet_valid")

    return claims


def build_approval_claims(
    *,
    uid: str,
    purpose: str,
    subject_id: str,
    canonical_sha256: str,
    model: str,
    policy_version: str,
    prompt_version: str,
    retention: str,
    judgement: ScreenFrameJudgement,
) -> ScreenFrameApprovalClaims:
    """Build claims for an approved_clean judgement. Refuses anything else.

    This is the enforcement point for "only approved_clean may mint an
    approval" (contract §4) — it is not merely documented, it is the only
    code path that constructs a ScreenFrameApprovalClaims object.
    """
    if judgement.outcome != "approved_clean":
        raise ValueError(f"cannot mint an approval for outcome={judgement.outcome!r}")

    now = datetime.now(timezone.utc)
    labels_digest = hashlib.sha256(_canonical_json(judgement.labels)).hexdigest()
    return ScreenFrameApprovalClaims(
        iss="omi-screen-frame-adjudicator",
        aud="omi-screen-frame-writer",
        jti=uuid4(),
        uid=uid,
        purpose=purpose,
        subject_kind="conversation",
        subject_id=subject_id,
        canonical_sha256=canonical_sha256,
        model=model,
        policy_version=policy_version,
        prompt_version=prompt_version,
        retention=retention,
        decision="approved_clean",
        labels_digest=labels_digest,
        issued_at=now,
        expires_at=now + timedelta(seconds=APPROVAL_MAX_TTL_SECONDS),
    )
