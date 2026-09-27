"""Provider-neutral contracts for delegated external authorization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable, Mapping, Optional, Protocol, Sequence, TypeVar


class Connector(str, Enum):
    GOOGLE_CALENDAR = 'google_calendar'
    GMAIL = 'gmail'


class Capability(str, Enum):
    CALENDAR_EVENTS_READ = 'calendar.events.read'
    MAIL_MESSAGES_READ = 'mail.messages.read'


class ConnectionState(str, Enum):
    PENDING_CONSENT = 'pending_consent'
    ACTIVE = 'active'
    REAUTH_REQUIRED = 'reauth_required'
    BLOCKED_BY_ADMIN = 'blocked_by_admin'
    REVOKE_PENDING = 'revoke_pending'
    REVOCATION_FAILED = 'revocation_failed'
    DELETION_PENDING = 'deletion_pending'
    REVOKED = 'revoked'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'


class RevocationDisposition(str, Enum):
    PROVIDER_CONFIRMED_REVOKE = 'provider_confirmed_revoke'
    PROVIDER_ALREADY_INVALID = 'provider_already_invalid'
    SECURITY_APPROVED_DECOMMISSION = 'security_approved_decommission'
    DELETION_DEADLINE_DESTROYED = 'upstream_revoke_unconfirmed_credentials_destroyed'


class SecretPurpose(str, Enum):
    CALLBACK_EXCHANGE = 'callback_exchange'
    READ = 'read'
    REFRESH = 'refresh'
    REVOKE = 'revoke'
    REWRAP = 'rewrap'


class ProviderErrorKind(str, Enum):
    RETRYABLE = 'retryable'
    INVALID_GRANT = 'invalid_grant'
    ADMIN_POLICY = 'admin_policy_enforced'
    ACCESS_DENIED = 'access_denied'
    SCOPE_MISMATCH = 'scope_mismatch'
    ACCOUNT_MISMATCH = 'provider_account_mismatch'
    CONFIGURATION = 'configuration_error'


class ExternalOAuthError(RuntimeError):
    """Typed, content-free failure safe to classify and count."""

    def __init__(self, kind: ProviderErrorKind, safe_code: str):
        self.kind = kind
        self.safe_code = safe_code
        super().__init__(safe_code)


@dataclass(frozen=True)
class ProviderPrincipal:
    subject: str
    masked_identity: str


@dataclass(frozen=True)
class TokenGrant:
    access_token: bytes
    refresh_token: Optional[bytes]
    effective_scopes: frozenset[str]
    expires_at: Optional[datetime]
    principal: ProviderPrincipal


@dataclass(frozen=True)
class Connection:
    connection_id: str
    external_owner_id: str
    connector: Connector
    grant_family: str
    provider: str
    client_alias: str
    state: ConnectionState
    generation: int
    scope_registry_revision: str
    effective_scope_digest: Optional[str] = None
    provider_subject: Optional[str] = None
    masked_identity: Optional[str] = None
    deletion_epoch: int = 0
    reauth_reason: Optional[str] = None


@dataclass(frozen=True)
class ConsentAttempt:
    attempt_id: str
    connection_id: str
    external_owner_id: str
    state_hash: str
    connector: Connector
    client_alias: str
    requested_scope_digest: str
    generation: int
    fixed_return_target_id: str
    expires_at: datetime
    encrypted_pkce_verifier_ref: str
    consumed_at: Optional[datetime] = None
    terminal_result: Optional[str] = None


@dataclass(frozen=True)
class AttemptConsumeResult:
    attempt: ConsentAttempt
    claimed: bool


@dataclass(frozen=True)
class SecretBinding:
    external_owner_id: str
    connection_id: str
    provider: str
    client_alias: str
    generation: int
    secret_version: int


@dataclass(frozen=True)
class SecretLeaseContext:
    connection_id: str
    generation: int
    deletion_epoch: int
    operation_id: str
    purpose: SecretPurpose


@dataclass(frozen=True)
class EncryptedSecretVersion:
    secret_id: str
    binding: SecretBinding
    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    kms_key_version: str
    aad_digest: str
    status: str = 'active'


@dataclass(frozen=True)
class AuthorizationStart:
    authorization_url: str
    attempt_id: str
    expires_at: datetime


@dataclass(frozen=True)
class ConnectionStatus:
    connector: Connector
    connected: bool
    state: Optional[ConnectionState]
    reauth_required: bool = False


@dataclass(frozen=True)
class MailMessage:
    message_id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    received_at: datetime


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    calendar_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    attendee_count: int = 0


class OAuthProviderPort(Protocol):
    def authorization_url(self, *, state: str, code_challenge: str, nonce: str) -> str: ...

    async def exchange_code(self, *, code: str, code_verifier: str, expected_nonce: str) -> TokenGrant: ...

    async def refresh(self, *, refresh_token: bytes) -> TokenGrant: ...

    async def revoke(self, *, token: bytes) -> None: ...


class ExternalConnectionRepository(Protocol):
    async def create_pending(self, connection: Connection, attempt: ConsentAttempt) -> None: ...

    async def consume_attempt(self, *, state_hash: str, now: datetime) -> AttemptConsumeResult: ...

    async def finish_attempt(self, state_hash: str, result: str) -> None: ...

    async def activate(
        self, *, attempt: ConsentAttempt, grant: TokenGrant, effective_scope_digest: str, secret_id: str
    ) -> Connection: ...

    async def get(self, *, external_owner_id: str, connector: Connector) -> Optional[Connection]: ...

    async def transition(
        self,
        *,
        connection_id: str,
        generation: int,
        target: ConnectionState,
        reason: Optional[str] = None,
        disposition: Optional[RevocationDisposition] = None,
        admin_clearance: bool = False,
    ) -> Connection: ...


T = TypeVar('T')
SecretOperation = Callable[[memoryview], Awaitable[T]]


class ExternalSecretExecutor(Protocol):
    async def create(self, *, binding: SecretBinding, plaintext: bytes) -> EncryptedSecretVersion: ...

    async def with_secret_lease(
        self, *, secret_id: str, context: SecretLeaseContext, operation: SecretOperation[T]
    ) -> T: ...

    async def destroy(self, *, secret_id: str, context: SecretLeaseContext) -> None: ...


class ExternalAuthorizationComposer(Protocol):
    async def authorize(
        self, *, external_owner_id: str, connector: Connector, capability: Capability, operation_id: str
    ) -> SecretLeaseContext: ...


class MailReadPort(Protocol):
    async def list_messages(self, *, external_owner_id: str, limit: int = 25) -> Sequence[MailMessage]: ...


class CalendarReadPort(Protocol):
    async def list_events(
        self, *, external_owner_id: str, starts_after: datetime, ends_before: datetime, limit: int = 100
    ) -> Sequence[CalendarEvent]: ...


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    connection_id: str
    generation: int
    operation_id: str
    occurred_at: datetime
    attributes: Mapping[str, str] = field(default_factory=dict)
