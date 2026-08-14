"""cubic PR 10887 C2/C3: the Twitter-ownership route must recognize federated Google/Apple sign-in on
BOTH auth backends (Firebase provider ids and Keycloak IdP aliases), and must not block the event loop
loading the profile. Exercises the route with the auth-provider lookup mocked."""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import asyncio  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from types import SimpleNamespace  # noqa: E402

import routers.apps as apps  # noqa: E402


def _run(providers, persona_id=None):
    with patch.object(apps, 'get_user_from_uid', return_value={'uid': 'u1'}), patch.object(
        apps.auth, 'get_user', return_value=SimpleNamespace(providers=providers)
    ), patch.object(apps, 'verify_latest_tweet', new=AsyncMock(return_value={'verified': True})), patch.object(
        apps, 'upsert_persona_from_twitter_profile', new=AsyncMock(return_value={'id': 'p-new', 'username': 'n'})
    ) as up, patch.object(
        apps, 'add_twitter_to_persona', new=AsyncMock(return_value={'id': 'p-existing', 'username': 'e'})
    ) as add:
        asyncio.run(apps.verify_twitter_ownership_tweet(username='user', handle='user', uid='u1', persona_id=persona_id))
        return up, add


def test_oidc_google_alias_is_treated_as_federated():
    # Keycloak emits the alias 'google' (not Firebase's 'google.com'); the user must take the federated
    # branch (attach to persona_id), NOT get a new persona created.
    up, add = _run(['google'], persona_id='persona-123')
    up.assert_not_called()
    add.assert_awaited_once()


def test_firebase_google_com_is_treated_as_federated():
    up, add = _run(['google.com'], persona_id='persona-123')
    up.assert_not_called()
    add.assert_awaited_once()


def test_non_federated_user_creates_persona():
    # No federated social provider -> the route creates a persona from the Twitter profile.
    up, add = _run([], persona_id=None)
    up.assert_awaited_once()
    add.assert_not_called()
