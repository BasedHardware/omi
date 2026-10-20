"""Authoritative, fenced refresh claims for OAuth-backed external MCP apps."""

import hashlib
import json
import time
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from models.mcp_client import McpCredentialError, RefreshClaim

REFRESH_LEASE_SECONDS = 60
_BINDING_FIELDS = ('token_endpoint', 'client_id', 'client_secret', 'redirect_uri', 'code_verifier')


def _run(client: Any, operation: Any) -> Any:
    return run_with_transaction_contention_retry(
        client.transaction,
        lambda transaction: run_transactional(client, operation, initial_transaction=transaction),
        operation_name='mcp_client_oauth_refresh',
    )


def _fingerprint(tokens: dict[str, Any]) -> str:
    fields = (*_BINDING_FIELDS, 'access_token', 'refresh_token')
    value = json.dumps({key: tokens.get(key) for key in fields}, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


def _connection(
    row: dict[str, Any], server_url: str, expected: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    ext = row.get('external_integration') or {}
    tokens = ext.get('mcp_oauth_tokens') or {}
    if ext.get('mcp_server_url') != server_url or any(tokens.get(key) != expected.get(key) for key in _BINDING_FIELDS):
        raise McpCredentialError('MCP connection changed. Reconnect the integration and try again.')
    if not all(
        isinstance(tokens.get(key), str) and tokens[key]
        for key in ('access_token', 'refresh_token', 'token_endpoint', 'client_id')
    ):
        raise McpCredentialError('MCP authorization is unavailable. Reconnect the integration.')
    return ext, tokens


def claim_refresh(
    app_id: str,
    server_url: str,
    expected: dict[str, Any],
    rejected_access_token: str | None,
    owner: str,
    *,
    now: float | None = None,
    firestore_client: Any = None,
) -> RefreshClaim:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('plugins_data').document(app_id)

    @firestore.transactional
    def claim(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise McpCredentialError('MCP integration was removed.')
        row = snapshot.to_dict()
        _, tokens = _connection(row, server_url, expected)
        timestamp = time.time() if now is None else now
        expires_at = tokens.get('expires_at')
        expired = isinstance(expires_at, (int, float)) and expires_at <= timestamp
        if tokens['access_token'] != rejected_access_token and not expired:
            return RefreshClaim('current', dict(tokens))
        lease = row.get('mcp_oauth_refresh') or {}
        fingerprint = _fingerprint(tokens)
        if lease.get('fingerprint') == fingerprint and lease.get('expires_at', 0) > timestamp:
            return RefreshClaim('busy', {})
        transaction.update(
            ref,
            {
                'mcp_oauth_refresh': {
                    'owner': owner,
                    'fingerprint': fingerprint,
                    'expires_at': timestamp + REFRESH_LEASE_SECONDS,
                }
            },
        )
        return RefreshClaim('claimed', dict(tokens))

    return _run(client, claim)


def complete_refresh(
    app_id: str,
    server_url: str,
    expected: dict[str, Any],
    owner: str,
    updated: dict[str, Any],
    *,
    now: float | None = None,
    firestore_client: Any = None,
) -> None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('plugins_data').document(app_id)

    @firestore.transactional
    def complete(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise McpCredentialError('MCP integration was removed during refresh.')
        row = snapshot.to_dict()
        ext, tokens = _connection(row, server_url, expected)
        lease = row.get('mcp_oauth_refresh') or {}
        timestamp = time.time() if now is None else now
        if (
            lease.get('owner') != owner
            or lease.get('fingerprint') != _fingerprint(tokens)
            or _fingerprint(tokens) != _fingerprint(expected)
            or lease.get('expires_at', 0) <= timestamp
        ):
            raise McpCredentialError('MCP authorization changed during refresh. Please try again.')
        transaction.update(
            ref, {'external_integration': {**ext, 'mcp_oauth_tokens': updated}, 'mcp_oauth_refresh': None}
        )

    _run(client, complete)


def release_refresh(app_id: str, expected: dict[str, Any], owner: str, *, firestore_client: Any = None) -> None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('plugins_data').document(app_id)

    @firestore.transactional
    def release(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return
        lease = (snapshot.to_dict() or {}).get('mcp_oauth_refresh') or {}
        if lease.get('owner') == owner and lease.get('fingerprint') == _fingerprint(expected):
            transaction.update(ref, {'mcp_oauth_refresh': None})

    _run(client, release)
