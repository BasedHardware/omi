"""Hermetic unit tests for safe persona deserialization in get_or_create_user_persona.

Verifies that get_or_create_user_persona in routers.apps uses _safe_app_from_dict
instead of returning raw unvalidated dicts from Firestore, preventing unhandled
ResponseValidationError (HTTP 500) crashes when an existing persona document is
missing required schema fields or corrupted.
"""

from __future__ import annotations

import asyncio
import inspect
from types import ModuleType
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import pytest


class _AutoMockModule(ModuleType):
    """Dynamic stub module providing mock attributes on access."""

    def __getattr__(self, name: str) -> Any:
        val = MagicMock()
        setattr(self, name, val)
        return val


class _AutoFinder:
    """Hermetic import interceptor for external and database services."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        from importlib.machinery import ModuleSpec

        prefixes = (
            'database.',
            'utils.cloud_tasks',
            'utils.other.storage',
            'utils.social',
            'utils.mcp_client',
            'utils.http_client',
            'utils.llm',
            'langchain_',
            'firebase_admin',
            'google.',
            'redis',
            'pycountry',
            'stripe',
            'anthropic',
            'openai',
        )
        if any(fullname.startswith(p) for p in prefixes):
            return ModuleSpec(fullname, self)
        return None

    def create_module(self, spec: Any) -> Any:
        return _AutoMockModule(spec.name)

    def exec_module(self, module: Any) -> None:
        pass


apps_mod = None


def _setup_stubs_and_import() -> Any:
    global apps_mod
    if apps_mod is not None:
        return apps_mod
    import sys

    sys.meta_path.insert(0, _AutoFinder())
    import routers.apps as _apps

    apps_mod = _apps
    return apps_mod


@pytest.fixture(autouse=True, scope='module')
def _ensure_module_stubs() -> None:
    _setup_stubs_and_import()


def _valid_persona_dict(persona_id: str = 'persona_123', uid: str = 'user_1') -> Dict[str, Any]:
    return {
        'id': persona_id,
        'name': 'Ada Persona',
        'category': 'personality-emulation',
        'author': 'Ada Lovelace',
        'description': 'AI clone of Ada',
        'image': 'https://example.com/avatar.png',
        'capabilities': ['persona'],
        'approved': True,
        'uid': uid,
    }


def test_safe_app_from_dict_validation() -> None:
    """_safe_app_from_dict must return App for valid dict and None for corrupted dicts."""
    mod = _setup_stubs_and_import()
    app = mod._safe_app_from_dict(_valid_persona_dict())
    assert app is not None and app.id == 'persona_123' and app.name == 'Ada Persona'

    for bad in ({'id': 'bad_1'}, {'name': 'Missing fields'}, None, 'invalid', []):
        assert mod._safe_app_from_dict(bad) is None


def test_get_or_create_user_persona_returns_safe_app_when_existing_is_valid() -> None:
    """Existing valid persona in DB must be safely deserialized and returned as App."""
    mod = _setup_stubs_and_import()
    valid = _valid_persona_dict()

    async def fake_run_blocking(executor: Any, func: Any, *args: Any) -> Any:
        return valid if func is mod.get_user_persona_by_uid else MagicMock()

    with patch.object(mod, 'run_blocking', side_effect=fake_run_blocking):
        result = asyncio.run(mod.get_or_create_user_persona(uid='user_1'))
        assert result is not None and result.id == 'persona_123' and result.name == 'Ada Persona'


def test_get_or_create_user_persona_regenerates_when_existing_is_malformed() -> None:
    """Malformed persona doc in DB must not crash with 500; it must warn and generate clean persona."""
    mod = _setup_stubs_and_import()
    corrupt_doc = {'id': 'corrupt_doc_without_mandatory_fields'}

    async def fake_run_blocking(executor: Any, func: Any, *args: Any) -> Any:
        if func is mod.get_user_persona_by_uid:
            return corrupt_doc
        if func is mod.get_user_from_uid:
            return {'display_name': 'Grace Hopper', 'email': 'grace@navy.mil'}
        if func is mod.increment_username:
            return 'gracehopper'
        return MagicMock()

    async def fake_generate_persona_prompt(u: Any, d: Any) -> str:
        return 'Test Prompt'

    warn_mock = MagicMock()
    with patch.object(mod, 'run_blocking', side_effect=fake_run_blocking), patch.object(
        mod, 'generate_persona_prompt', side_effect=fake_generate_persona_prompt
    ), patch.object(mod.logger, 'warning', warn_mock):
        result = asyncio.run(mod.get_or_create_user_persona(uid='user_2'))
        assert result is not None and isinstance(result, dict)
        assert result['name'] == 'Grace Hopper' and result['category'] == 'personality-emulation'
        assert warn_mock.called


def test_ast_uses_safe_app_from_dict() -> None:
    """Verify via AST that get_or_create_user_persona calls _safe_app_from_dict."""
    mod = _setup_stubs_and_import()
    assert '_safe_app_from_dict' in inspect.getsource(mod.get_or_create_user_persona)
