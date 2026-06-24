"""add_twitter_to_persona must not 500 with TypeError when the persona lookup returns None.

utils/social.py has a heavy import graph (utils.llm.persona, utils.conversations.memories,
database.apps, database.redis_db, ulid, ...), so we import it under a meta-path stub finder
that auto-mocks those namespaces (keeping fastapi/pydantic/httpx real). utils.social itself is
explicitly NOT stubbed so the real function under test loads, while its collaborators are mocked.

Without the fix, `persona = get_persona_by_id_db(persona_id)` is None and the line
`if 'twitter' not in persona['connected_accounts']:` raises
`TypeError: 'NoneType' object is not subscriptable` (-> unhandled 500). With the guard the
function raises a clean HTTPException(404) before subscripting.
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# The module under test is utils.social itself, so the real `utils` package (empty __init__)
# and utils.social must load. Only the heavy utils submodules that social.py imports
# (utils.llm.persona, utils.conversations.memories) and the external/database deps get stubbed.
_STUB = (
    'database',
    'utils.llm',
    'utils.conversations',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot_stubbed_modules():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore_stubbed_modules(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_stubbed_modules_snapshot = _snapshot_stubbed_modules()
_clear_stubbed_modules()
sys.meta_path.insert(0, _finder)
try:
    from utils import social as social_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)


def _run_add_twitter(persona_value):
    """Drive add_twitter_to_persona with get_persona_by_id_db returning ``persona_value``.

    get_twitter_profile is stubbed (AsyncMock) so the unfixed code path reaches the
    persona['connected_accounts'] subscript (and raises TypeError on None) instead of making a
    real network call; the rest of the collaborators are mocked so only the None-guard is tested.
    """
    fake_profile = MagicMock()
    fake_profile.profile = 'somehandle'
    fake_profile.avatar = 'http://img/avatar.png'

    fake_timeline = MagicMock()
    fake_timeline.timeline = []

    with patch.object(social_mod, 'get_persona_by_id_db', MagicMock(return_value=persona_value)), patch.object(
        social_mod, 'get_twitter_profile', AsyncMock(return_value=fake_profile)
    ), patch.object(social_mod, 'get_twitter_timeline', AsyncMock(return_value=fake_timeline)), patch.object(
        social_mod, 'update_app_in_db', MagicMock()
    ), patch.object(
        social_mod, 'delete_generic_cache', MagicMock()
    ), patch.object(
        social_mod, 'create_memories_from_twitter_tweets', MagicMock()
    ):
        return asyncio.run(social_mod.add_twitter_to_persona('somehandle', 'persona-id'))


def test_add_twitter_to_persona_missing_raises_404():
    """Persona lookup returning None must raise HTTPException(404), not TypeError (the bug)."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _run_add_twitter(None)
    assert exc.value.status_code == 404


def test_add_twitter_to_persona_existing_succeeds():
    """When the persona exists, it is updated and returned (no regression)."""
    persona = {'id': 'persona-id', 'uid': 'uid1', 'connected_accounts': ['omi']}
    result = _run_add_twitter(persona)
    assert isinstance(result, dict)
    assert result['id'] == 'persona-id'
    assert 'twitter' in result['connected_accounts']
    assert result['twitter']['username'] == 'somehandle'
