"""Repository fake that executes the production CAS/cardinality contract."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from typing import Dict, Optional

from utils.external_oauth.contracts import (
    AttemptConsumeResult,
    Connection,
    ConnectionState,
    Connector,
    ConsentAttempt,
    RevocationDisposition,
    TokenGrant,
)
from utils.external_oauth.lifecycle import TERMINAL_STATES, transition_decision


class InMemoryExternalConnectionRepository:
    """Concurrency-capable fake. Firestore implementation must preserve these CAS rules."""

    def __init__(self):
        self.connections: Dict[str, Connection] = {}
        self.attempts: Dict[str, ConsentAttempt] = {}
        self.secret_ids: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_pending(self, connection: Connection, attempt: ConsentAttempt) -> None:
        async with self._lock:
            key = (connection.external_owner_id, connection.connector, connection.grant_family)
            for existing in self.connections.values():
                existing_key = (existing.external_owner_id, existing.connector, existing.grant_family)
                if existing_key == key and existing.state not in TERMINAL_STATES:
                    raise ValueError('non-terminal external connection already exists')
            self.connections[connection.connection_id] = connection
            self.attempts[attempt.state_hash] = attempt

    async def consume_attempt(self, *, state_hash: str, now: datetime) -> AttemptConsumeResult:
        async with self._lock:
            attempt = self.attempts.get(state_hash)
            if attempt is None or attempt.expires_at <= now:
                raise ValueError('oauth attempt unavailable')
            if attempt.consumed_at is not None:
                return AttemptConsumeResult(attempt=attempt, claimed=False)
            consumed = replace(attempt, consumed_at=now, terminal_result='exchange_claimed')
            self.attempts[state_hash] = consumed
            return AttemptConsumeResult(attempt=consumed, claimed=True)

    async def finish_attempt(self, state_hash: str, result: str) -> None:
        async with self._lock:
            self.attempts[state_hash] = replace(self.attempts[state_hash], terminal_result=result)

    async def activate(
        self, *, attempt: ConsentAttempt, grant: TokenGrant, effective_scope_digest: str, secret_id: str
    ) -> Connection:
        async with self._lock:
            current = self.connections[attempt.connection_id]
            if current.state != ConnectionState.PENDING_CONSENT or current.generation != attempt.generation:
                raise ValueError('oauth activation lost generation CAS')
            if current.provider_subject and current.provider_subject != grant.principal.subject:
                raise ValueError('provider_account_mismatch')
            active = replace(
                current,
                state=ConnectionState.ACTIVE,
                provider_subject=grant.principal.subject,
                masked_identity=grant.principal.masked_identity,
                effective_scope_digest=effective_scope_digest,
                reauth_reason=None,
            )
            self.connections[current.connection_id] = active
            self.secret_ids[current.connection_id] = secret_id
            return active

    async def get(self, *, external_owner_id: str, connector: Connector) -> Optional[Connection]:
        async with self._lock:
            matches = [
                connection
                for connection in self.connections.values()
                if connection.external_owner_id == external_owner_id
                and connection.connector == connector
                and connection.state not in TERMINAL_STATES
            ]
            if len(matches) > 1:
                raise RuntimeError('external connection cardinality violated')
            return matches[0] if matches else None

    async def transition(
        self,
        *,
        connection_id: str,
        generation: int,
        target: ConnectionState,
        reason: Optional[str] = None,
        disposition: Optional[RevocationDisposition] = None,
        admin_clearance: bool = False,
    ) -> Connection:
        async with self._lock:
            current = self.connections[connection_id]
            if current.generation != generation:
                raise ValueError('external connection generation CAS failed')
            decision = transition_decision(
                current.state,
                target,
                disposition=disposition,
                admin_clearance=admin_clearance,
            )
            updated = replace(
                current,
                state=target,
                generation=current.generation + int(decision.increments_generation),
                reauth_reason=reason,
            )
            self.connections[connection_id] = updated
            return updated

    async def active_secret_id(self, *, connection_id: str, generation: int) -> str:
        async with self._lock:
            connection = self.connections[connection_id]
            if connection.state != ConnectionState.ACTIVE or connection.generation != generation:
                raise PermissionError('external connection is not active at requested generation')
            return self.secret_ids[connection_id]
