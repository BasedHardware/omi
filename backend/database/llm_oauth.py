from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from ._client import get_firestore_client

LLM_OAUTH_PROVIDERS = frozenset({'chatgpt', 'grok'})


def save_credential(uid: str, provider: str, credential: dict[str, Any], *, firestore_client: Any = None) -> None:
    if provider not in LLM_OAUTH_PROVIDERS:
        raise ValueError(f'Unsupported LLM OAuth provider: {provider}')
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
    stored = {
        'access_token': encryption.encrypt(access_token, uid),
        'refresh_token': encryption.encrypt(refresh_token, uid),
        'expires_at': credential.get('expires_at'),
        'account_id': credential.get('account_id'),
        'updated_at': datetime.now(timezone.utc),
    }
    client = firestore_client or get_firestore_client()
    client.collection('users').document(uid).set(
        {
            'llm_oauth': {provider: stored},
            'llm_oauth_provider': provider,
            'byok': {'active': True, 'last_seen_at': datetime.now(timezone.utc)},
        },
        merge=True,
    )


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
    }


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
    data = user_ref.get().to_dict() or {}
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
    user_ref.update(update)
