"""Durable claim and encrypted result for one keyed, non-streaming completion."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from database import _client as firestore_clients
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.idempotency_request import canonical_request

CLAIMS = 'llm_gateway_idempotency_claims'
RESULTS = 'llm_gateway_idempotency_results'
CLAIM_TTL = timedelta(days=30)
RESULT_TTL = timedelta(hours=24)
PENDING_WINDOW = timedelta(minutes=5)
MAX_RESULT_BYTES = 256 * 1024
DATA_PLANE_ENV = 'LLM_GATEWAY_IDEMPOTENCY_CUSTOMER_PROJECT'
ACTIVE_SECRET_ENV = 'LLM_GATEWAY_IDEMPOTENCY_ENCRYPTION_SECRET'
SECONDARY_SECRET_ENV = 'LLM_GATEWAY_IDEMPOTENCY_SECONDARY_ENCRYPTION_SECRET'


class IdempotencyError(Exception):
    """A bounded client-facing failure for the idempotency protocol."""

    def __init__(self, status: int, code: str, retry_after: str | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class Operation:
    owner: str
    document_id: str
    environment: str

    @classmethod
    def for_caller(cls, caller: ServiceCaller, key: str, environment: str) -> 'Operation':
        owner = caller.user_uid
        if owner is None or owner in {'.', '..'} or '/' in owner or owner.startswith('__') and owner.endswith('__'):
            raise IdempotencyError(400, 'idempotency_owner_required')
        scope = json.dumps([environment, caller.name, owner, caller.tenant_id, key], separators=(',', ':'))
        return cls(owner, hashlib.sha256(scope.encode()).hexdigest(), environment)

    @staticmethod
    def canonical_request(body: dict[str, Any], credentials: CredentialContext) -> bytes:
        # The provider keys and request body live only in memory. A keyed digest
        # keeps anyone reading the claim from testing candidate prompt text.
        try:
            return canonical_request(body, credentials.source.value, credentials.forwarded_provider_keys)
        except (ValueError, RecursionError) as exc:
            raise IdempotencyError(400, 'idempotency_invalid_body') from exc


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: bytes


def _customer_firestore_client() -> Any:
    project = os.getenv(DATA_PLANE_ENV, '').strip()
    if not project:
        raise IdempotencyError(503, 'idempotency_store_unavailable')
    client = firestore_clients.get_pinned_data_plane_firestore_client(project)
    if client.project != project:
        raise IdempotencyError(503, 'idempotency_store_unavailable')
    return client


def _version(secret: bytes) -> str:
    return hmac.digest(secret, b'llm-gateway-idempotency-v1/key-version', 'sha256')[:16].hex()


class _KeyRing:
    def __init__(self, owner: str):
        active = os.getenv(ACTIVE_SECRET_ENV, os.getenv('ENCRYPTION_SECRET', '')).encode()
        secondary = os.getenv(SECONDARY_SECRET_ENV, '').encode()
        if len(active) < 32 or (secondary and len(secondary) < 32):
            raise IdempotencyError(503, 'idempotency_store_unavailable')
        self.owner = owner
        self.active_version = _version(active)
        self._secrets = {self.active_version: active}
        if secondary:
            self._secrets[_version(secondary)] = secondary

    def key(self, version: str, purpose: bytes) -> bytes:
        secret = self._secrets.get(version)
        if secret is None:
            raise IdempotencyError(503, 'idempotency_store_unavailable')
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.owner.encode(),
            info=b'llm-gateway-idempotency-v1/' + purpose,
        ).derive(secret)

    def fingerprint(self, version: str, canonical: bytes) -> str:
        return hmac.digest(self.key(version, b'fingerprint'), canonical, 'sha256').hex()


class Store:
    def __init__(self, operation: Operation, *, client: Any = None):
        self.operation = operation
        self.claim_token = uuid4().hex
        self.client = client if client is not None else _customer_firestore_client()
        self.keys = _KeyRing(operation.owner)
        user = self.client.collection('users').document(operation.owner)
        self.claim = user.collection(CLAIMS).document(operation.document_id)
        self.result = user.collection(RESULTS).document(operation.document_id)
        self.marker = account_deletion_document(operation.owner, firestore_client=self.client)

    def _fence(self, transaction: Any) -> None:
        snapshot = self.marker.get(transaction=transaction, timeout=5)
        status = normalize_account_deletion_status(
            marker_exists=snapshot.exists, raw_status=(snapshot.to_dict() or {}).get('wipe_status')
        )
        if account_deletion_blocks_access(status):
            raise IdempotencyError(403, 'idempotency_owner_unavailable')

    def _read(self, transaction: Any, canonical: bytes | None, *, create: bool = False) -> StoredResponse | None:
        self._fence(transaction)
        snapshot = self.claim.get(transaction=transaction, timeout=5)
        now = datetime.now(timezone.utc)
        if not snapshot.exists:
            if not create or canonical is None:
                raise IdempotencyError(404, 'idempotency_not_found')
            transaction.create(
                self.claim,
                {
                    'fingerprint': self.keys.fingerprint(self.keys.active_version, canonical),
                    'key_version': self.keys.active_version,
                    'claim_token': self.claim_token,
                    'state': 'pending',
                    'environment': self.operation.environment,
                    'started_at': now,
                    'expires_at': now + CLAIM_TTL,
                },
            )
            return None

        claim = snapshot.to_dict() or {}
        if claim.get('environment') != self.operation.environment:
            raise IdempotencyError(503, 'idempotency_store_unavailable')
        if now >= claim['expires_at']:
            raise IdempotencyError(410, 'idempotency_expired')
        version = claim['key_version']
        if canonical is not None and not hmac.compare_digest(
            claim['fingerprint'], self.keys.fingerprint(version, canonical)
        ):
            raise IdempotencyError(409, 'idempotency_conflict')
        if claim['state'] == 'pending' and now < claim['started_at'] + PENDING_WINDOW:
            raise IdempotencyError(409, 'idempotency_pending', retry_after='2')
        if claim['state'] != 'committed':
            raise IdempotencyError(409, 'idempotency_indeterminate')
        if now >= claim['result_expires_at']:
            raise IdempotencyError(410, 'idempotency_expired')

        response = self.result.get(transaction=transaction, timeout=5).to_dict()
        if response is None or response.get('environment') != self.operation.environment:
            raise IdempotencyError(503, 'idempotency_store_unavailable')
        packed = response['sealed']
        plaintext = AESGCM(self.keys.key(version, b'result')).decrypt(
            packed[:12], packed[12:], self.operation.document_id.encode()
        )
        return StoredResponse(int.from_bytes(plaintext[:2], 'big'), plaintext[2:])

    def claim_or_replay(self, canonical: bytes) -> StoredResponse | None:
        run = firestore.transactional(self._read)
        try:
            return run(self.client.transaction(), canonical, create=True)
        except AlreadyExists:
            # A concurrently created claim can surface as a failed create precondition.
            return run(self.client.transaction(read_only=True), canonical)

    def lookup(self) -> StoredResponse:
        run = firestore.transactional(self._read)
        response = run(self.client.transaction(read_only=True), None)
        if response is None:
            raise IdempotencyError(404, 'idempotency_not_found')
        return response

    def finish(self, response: StoredResponse | None) -> None:
        oversized = response is not None and len(response.body) > MAX_RESULT_BYTES

        @firestore.transactional
        def settle(transaction: Any) -> None:
            self._fence(transaction)
            claim = self.claim.get(transaction=transaction, timeout=5).to_dict()
            now = datetime.now(timezone.utc)
            if not claim or claim['state'] != 'pending' or claim['claim_token'] != self.claim_token:
                raise IdempotencyError(409, 'idempotency_indeterminate')
            if claim.get('environment') != self.operation.environment:
                raise IdempotencyError(503, 'idempotency_store_unavailable')
            if now >= claim['expires_at']:
                raise IdempotencyError(410, 'idempotency_expired')
            if response is None or oversized:
                transaction.update(self.claim, {'state': 'indeterminate'})
                return
            nonce = os.urandom(12)
            plaintext = response.status.to_bytes(2, 'big') + response.body
            sealed = nonce + AESGCM(self.keys.key(claim['key_version'], b'result')).encrypt(
                nonce, plaintext, self.operation.document_id.encode()
            )
            expires_at = min(now + RESULT_TTL, claim['expires_at'])
            transaction.create(
                self.result, {'sealed': sealed, 'expires_at': expires_at, 'environment': self.operation.environment}
            )
            transaction.update(self.claim, {'state': 'committed', 'result_expires_at': expires_at})

        settle(self.client.transaction())
        if oversized:
            raise IdempotencyError(409, 'idempotency_indeterminate')
