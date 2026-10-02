"""Deterministic fake provider for lifecycle and consumer conformance tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from utils.external_oauth.contracts import ProviderPrincipal, TokenGrant


class FakeOAuthProvider:
    def __init__(self, *, scopes: frozenset[str], subject: str = 'provider-subject-1'):
        self.scopes = scopes
        self.subject = subject
        self.exchange_count = 0
        self.refresh_count = 0
        self.revoke_count = 0
        self.error: Optional[Exception] = None

    def authorization_url(self, *, state: str, code_challenge: str, nonce: str) -> str:
        return 'https://provider.invalid/authorize?' + urlencode(
            {'state': state, 'code_challenge': code_challenge, 'code_challenge_method': 'S256', 'nonce': nonce}
        )

    def _grant(self, refresh_token: Optional[bytes]) -> TokenGrant:
        if self.error:
            raise self.error
        return TokenGrant(
            access_token=b'fake-access-token',
            refresh_token=refresh_token,
            effective_scopes=self.scopes,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            principal=ProviderPrincipal(subject=self.subject, masked_identity='u***@example.invalid'),
        )

    async def exchange_code(self, *, code: str, code_verifier: str, expected_nonce: str) -> TokenGrant:
        self.exchange_count += 1
        return self._grant(b'fake-refresh-token')

    async def refresh(self, *, refresh_token: bytes) -> TokenGrant:
        self.refresh_count += 1
        return self._grant(None)

    async def revoke(self, *, token: bytes) -> None:
        if self.error:
            raise self.error
        self.revoke_count += 1
