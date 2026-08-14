from datetime import datetime, timezone
from typing import Any, Callable, TypeVar, cast
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import transactional  # type: ignore[reportUnknownVariableType]

from ._client import get_firestore_client

LLM_OAUTH_PROVIDERS = frozenset({'chatgpt', 'grok'})
_T = TypeVar('_T')


def _typed_transactional(function: Callable[..., _T]) -> Callable[..., _T]:
    return cast(Callable[..., _T], transactional(function))


def _stored_credential(uid: str, credential: dict[str, Any], generation: str) -> dict[str, Any]:
    from utils import encryption

    access_token = credential.get('access_token')
    refresh_token = credential.get('refresh_token')
    if (
        not isinstance(access_token, str)
        or not access_token.strip()
        or not isinstance(refresh_token, str)
        or not refresh_token.strip()
    ):
        raise ValueError('LLM OAuth credential requires access and refresh tokens')
    return {
        'access_token': encryption.encrypt(access_token, uid),
        'refresh_token': encryption.encrypt(refresh_token, uid),
        'expires_at': credential.get('expires_at'),
        'account_id': credential.get('account_id'),
        'model': credential.get('model'),
        'generation': generation,
        'updated_at': datetime.now(timezone.utc),
    }


def save_credential(uid: str, provider: str, credential: dict[str, Any], *, firestore_client: Any = None) -> None:
    if provider not in LLM_OAUTH_PROVIDERS:
        raise ValueError(f'Unsupported LLM OAuth provider: {provider}')
    stored = _stored_credential(uid, credential, uuid4().hex)
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    transaction = client.transaction()

    @_typed_transactional
    def apply(write_transaction):
        user_ref.get(transaction=write_transaction)
        write_transaction.set(
            user_ref,
            {
                'llm_oauth': {provider: stored},
                'llm_oauth_provider': provider,
                'byok': {'active': True, 'last_seen_at': datetime.now(timezone.utc)},
            },
            merge=True,
        )

    apply(transaction)


def get_credential(uid: str, provider: str | None = None, *, firestore_client: Any = None) -> dict[str, Any] | None:
    client = firestore_client or get_firestore_client()
    data = client.collection('users').document(uid).get().to_dict() or {}
    selected_provider = provider or data.get('llm_oauth_provider')
    if selected_provider not in LLM_OAUTH_PROVIDERS:
        return None
    stored = (data.get('llm_oauth') or {}).get(selected_provider)
    if not isinstance(stored, dict):
        return None
    access_token = stored.get('access_token')
    refresh_token = stored.get('refresh_token')
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        return None
    from utils import encryption

    return {
        'provider': selected_provider,
        'access_token': encryption.decrypt(access_token, uid),
        'refresh_token': encryption.decrypt(refresh_token, uid),
        'expires_at': stored.get('expires_at'),
        'account_id': stored.get('account_id'),
        'model': stored.get('model'),
        'generation': stored.get('generation'),
    }


def save_refreshed_credential(
    uid: str, provider: str, credential: dict[str, Any], generation: str, *, firestore_client: Any = None
) -> bool:
    if provider not in LLM_OAUTH_PROVIDERS:
        raise ValueError(f'Unsupported LLM OAuth provider: {provider}')
    if not generation:
        return False
    stored = _stored_credential(uid, credential, generation)
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    transaction = client.transaction()

    @_typed_transactional
    def apply(write_transaction):
        snapshot = user_ref.get(transaction=write_transaction)
        data = snapshot.to_dict() or {}
        current = (data.get('llm_oauth') or {}).get(provider)
        if not isinstance(current, dict) or current.get('generation') != generation:
            return False
        write_transaction.update(
            user_ref,
            {
                f'llm_oauth.{provider}': stored,
                'byok.last_seen_at': datetime.now(timezone.utc),
            },
        )
        return True

    return bool(apply(transaction))


def get_status(uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    client = firestore_client or get_firestore_client()
    data = client.collection('users').document(uid).get().to_dict() or {}
    credentials = data.get('llm_oauth') or {}
    connected = [provider for provider in LLM_OAUTH_PROVIDERS if isinstance(credentials.get(provider), dict)]
    selected_provider = data.get('llm_oauth_provider')
    return {
        'connected': sorted(connected),
        'selected_provider': selected_provider if selected_provider in connected else None,
    }


def delete_credential(uid: str, provider: str, *, firestore_client: Any = None) -> None:
    if provider not in LLM_OAUTH_PROVIDERS:
        raise ValueError(f'Unsupported LLM OAuth provider: {provider}')
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    transaction = client.transaction()

    @_typed_transactional
    def apply(write_transaction):
        data = user_ref.get(transaction=write_transaction).to_dict() or {}
        next_provider = next(
            (
                candidate
                for candidate in LLM_OAUTH_PROVIDERS
                if candidate != provider and isinstance((data.get('llm_oauth') or {}).get(candidate), dict)
            ),
            None,
        )
        update: dict[str, Any] = {f'llm_oauth.{provider}': firestore.DELETE_FIELD}
        if data.get('llm_oauth_provider') == provider:
            update['llm_oauth_provider'] = next_provider
        if next_provider is None and not (data.get('byok') or {}).get('fingerprints'):
            update['byok.active'] = False
            update['byok.last_seen_at'] = datetime.now(timezone.utc)
        write_transaction.update(user_ref, update)

    apply(transaction)
