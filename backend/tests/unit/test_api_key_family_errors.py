"""An Omi API key used on the wrong endpoint family must say so in the 401.

Regression for #7506: an MCP key on /v1/conversations only answered "Invalid authorization
token", which reads as a broken key rather than a key/endpoint mismatch.
"""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator, Optional

import pytest
from fastapi import HTTPException

from testing.import_isolation import load_module_fresh, stub_modules
from utils.other.endpoints import get_current_user_uid

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _ProductAuthorizationContext:
    def __init__(self, **values: Any):
        self.__dict__.update(values)


@dataclass(frozen=True)
class _McpVerifiedAuth:
    uid: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()


class _KeyLookupSpy:
    """Stands in for the Firestore key lookup so we can assert it is never reached."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, token: str) -> SimpleNamespace:
        self.calls.append(token)
        return SimpleNamespace(context=None, repairs=frozenset())


@contextmanager
def _loaded_dependencies() -> Iterator[tuple[ModuleType, _KeyLookupSpy, _KeyLookupSpy]]:
    mcp_lookup = _KeyLookupSpy()
    dev_lookup = _KeyLookupSpy()

    with stub_modules(
        {
            'firebase_admin.auth': _module('firebase_admin.auth', verify_id_token=lambda _token: {'uid': 'user-1'}),
            'database.mcp_api_key': _module('database.mcp_api_key', get_api_key_auth_result=mcp_lookup),
            'database.dev_api_key': _module('database.dev_api_key', get_api_key_auth_result=dev_lookup),
            'utils.other.endpoints': _module('utils.other.endpoints', check_api_key_rate_limit=lambda **_kwargs: None),
            'utils.mcp_memories': _module(
                'utils.mcp_memories',
                McpVerifiedAuth=_McpVerifiedAuth,
                build_mcp_default_memory_read_context=lambda auth: _ProductAuthorizationContext(uid=auth.uid),
                build_mcp_default_memory_write_context=lambda auth: _ProductAuthorizationContext(uid=auth.uid),
            ),
            'utils.memory.product_authorization': _module(
                'utils.memory.product_authorization',
                ProductAuthorizationContext=_ProductAuthorizationContext,
            ),
        }
    ):
        dependencies = load_module_fresh('dependencies', str(BACKEND_DIR / 'dependencies.py'))
        yield dependencies, mcp_lookup, dev_lookup


def test_developer_key_on_an_mcp_endpoint_names_both_endpoint_families() -> None:
    with _loaded_dependencies() as (dependencies, mcp_lookup, _dev_lookup):
        with pytest.raises(HTTPException) as raised:
            asyncio.run(dependencies.get_uid_from_mcp_api_key('Bearer omi_dev_secret'))

        assert raised.value.status_code == 401
        assert '/v1/dev/' in raised.value.detail
        assert 'MCP API key' in raised.value.detail
        assert mcp_lookup.calls == []


def test_mcp_key_on_a_developer_endpoint_names_both_endpoint_families() -> None:
    with _loaded_dependencies() as (dependencies, _mcp_lookup, dev_lookup):
        with pytest.raises(HTTPException) as raised:
            asyncio.run(dependencies.get_api_key_auth('Bearer omi_mcp_secret'))

        assert raised.value.status_code == 401
        assert '/v1/mcp/' in raised.value.detail
        assert 'Developer API key' in raised.value.detail
        assert dev_lookup.calls == []


def test_matching_key_family_still_reaches_its_own_key_lookup() -> None:
    with _loaded_dependencies() as (dependencies, _mcp_lookup, dev_lookup):
        with pytest.raises(HTTPException) as raised:
            asyncio.run(dependencies.get_api_key_auth('Bearer omi_dev_secret'))

        # The stubbed lookup rejects every key; what matters is that the prefix guard
        # let a developer key through to the developer-key lookup.
        assert raised.value.detail == 'Invalid API Key'
        assert dev_lookup.calls == ['omi_dev_secret']


def test_mcp_key_on_a_firebase_endpoint_points_at_the_mcp_endpoints() -> None:
    with pytest.raises(HTTPException) as raised:
        get_current_user_uid(authorization='Bearer omi_mcp_secret')

    assert raised.value.status_code == 401
    assert '/v1/mcp/' in raised.value.detail
    assert 'Firebase ID token' in raised.value.detail
