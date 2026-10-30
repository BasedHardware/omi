"""Provider-neutral authorization lifecycle orchestration."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from utils.external_oauth.contracts import (
    AuthorizationStart,
    Connection,
    ConnectionState,
    Connector,
    ConsentAttempt,
    ExternalConnectionRepository,
    ExternalSecretExecutor,
    OAuthProviderPort,
    SecretBinding,
    SecretLeaseContext,
    SecretPurpose,
    TokenGrant,
)
from utils.external_oauth.scopes import GRANT_FAMILIES, SCOPE_REGISTRY_REVISION, require_exact_scopes, scope_digest

CONSENT_TTL = timedelta(minutes=10)


def _state_hash(raw_state: str) -> str:
    return hashlib.sha256(raw_state.encode()).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


def _serialize_grant(grant: TokenGrant) -> bytes:
    return json.dumps(
        {
            'access_token': base64.b64encode(grant.access_token).decode(),
            'refresh_token': base64.b64encode(grant.refresh_token).decode() if grant.refresh_token else None,
            'expires_at': grant.expires_at.isoformat() if grant.expires_at else None,
        },
        separators=(',', ':'),
    ).encode()


class ExternalOAuthService:
    """Lifecycle logic independent of FastAPI, Firestore, Google, and KMS."""

    def __init__(
        self,
        *,
        repository: ExternalConnectionRepository,
        secrets_executor: ExternalSecretExecutor,
        providers: dict[Connector, OAuthProviderPort],
    ):
        self._repository = repository
        self._secrets = secrets_executor
        self._providers = providers

    async def start(
        self,
        *,
        external_owner_id: str,
        connector: Connector,
        fixed_return_target_id: str,
        now: datetime | None = None,
    ) -> AuthorizationStart:
        now = now or datetime.now(timezone.utc)
        raw_state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        nonce = secrets.token_urlsafe(32)
        connection_id = str(uuid.uuid4())
        attempt_id = str(uuid.uuid4())
        family = GRANT_FAMILIES[connector]
        connection = Connection(
            connection_id=connection_id,
            external_owner_id=external_owner_id,
            connector=connector,
            grant_family=family.grant_family,
            provider='google',
            client_alias=family.client_alias,
            state=ConnectionState.PENDING_CONSENT,
            generation=1,
            scope_registry_revision=SCOPE_REGISTRY_REVISION,
        )
        pkce_binding = SecretBinding(
            external_owner_id=external_owner_id,
            connection_id=connection_id,
            provider='google',
            client_alias=family.client_alias,
            generation=1,
            secret_version=0,
        )
        attempt_secret = json.dumps({'pkce_verifier': verifier, 'oidc_nonce': nonce}, separators=(',', ':')).encode()
        pkce_secret = await self._secrets.create(binding=pkce_binding, plaintext=attempt_secret)
        attempt = ConsentAttempt(
            attempt_id=attempt_id,
            connection_id=connection_id,
            external_owner_id=external_owner_id,
            state_hash=_state_hash(raw_state),
            connector=connector,
            client_alias=family.client_alias,
            requested_scope_digest=scope_digest(family.scopes),
            generation=1,
            fixed_return_target_id=fixed_return_target_id,
            expires_at=now + CONSENT_TTL,
            encrypted_pkce_verifier_ref=pkce_secret.secret_id,
        )
        try:
            await self._repository.create_pending(connection, attempt)
        except Exception:
            cleanup_context = SecretLeaseContext(
                connection_id=connection_id,
                generation=1,
                deletion_epoch=0,
                operation_id=attempt_id,
                purpose=SecretPurpose.REVOKE,
            )
            await self._secrets.destroy(secret_id=pkce_secret.secret_id, context=cleanup_context)
            raise
        url = self._providers[connector].authorization_url(
            state=raw_state, code_challenge=_pkce_challenge(verifier), nonce=nonce
        )
        return AuthorizationStart(authorization_url=url, attempt_id=attempt_id, expires_at=attempt.expires_at)

    async def callback(self, *, raw_state: str, code: str, now: datetime | None = None) -> str:
        """Consume once and return a sanitized completion class.

        Replays and concurrent losers never exchange a code. They receive the
        already-sanitized terminal result, or ``callback_already_claimed`` while
        the winner is still completing.
        """
        now = now or datetime.now(timezone.utc)
        consumed = await self._repository.consume_attempt(state_hash=_state_hash(raw_state), now=now)
        attempt = consumed.attempt
        if not consumed.claimed:
            return attempt.terminal_result or 'callback_already_claimed'
        context = SecretLeaseContext(
            connection_id=attempt.connection_id,
            generation=attempt.generation,
            deletion_epoch=0,
            operation_id=attempt.attempt_id,
            purpose=SecretPurpose.CALLBACK_EXCHANGE,
        )

        async def exchange(attempt_secret: memoryview) -> TokenGrant:
            ephemeral = json.loads(bytes(attempt_secret))
            return await self._providers[attempt.connector].exchange_code(
                code=code,
                code_verifier=ephemeral['pkce_verifier'],
                expected_nonce=ephemeral['oidc_nonce'],
            )

        cleanup_context = SecretLeaseContext(
            connection_id=attempt.connection_id,
            generation=attempt.generation,
            deletion_epoch=0,
            operation_id=attempt.attempt_id,
            purpose=SecretPurpose.REVOKE,
        )
        credential_id: str | None = None
        activated = False
        try:
            grant = await self._secrets.with_secret_lease(
                secret_id=attempt.encrypted_pkce_verifier_ref, context=context, operation=exchange
            )
            effective = require_exact_scopes(attempt.connector, grant.effective_scopes)
            if scope_digest(effective) != attempt.requested_scope_digest:
                raise ValueError('callback scope binding mismatch')
            secret_binding = SecretBinding(
                external_owner_id=attempt.external_owner_id,
                connection_id=attempt.connection_id,
                provider='google',
                client_alias=attempt.client_alias,
                generation=attempt.generation,
                secret_version=1,
            )
            credential = await self._secrets.create(binding=secret_binding, plaintext=_serialize_grant(grant))
            credential_id = credential.secret_id
            await self._repository.activate(
                attempt=attempt,
                grant=grant,
                effective_scope_digest=scope_digest(effective),
                secret_id=credential.secret_id,
            )
            activated = True
            await self._repository.finish_attempt(attempt.state_hash, 'connected')
            return 'connected'
        except Exception:
            await self._repository.finish_attempt(attempt.state_hash, 'callback_failed')
            raise
        finally:
            # Attempt material is always short-lived. A credential that lost the
            # activation CAS is also destroyed instead of becoming an orphan.
            await self._secrets.destroy(secret_id=attempt.encrypted_pkce_verifier_ref, context=cleanup_context)
            if credential_id is not None and not activated:
                await self._secrets.destroy(secret_id=credential_id, context=cleanup_context)
