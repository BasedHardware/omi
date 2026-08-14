"""Regression test for reporting a non-existent chat message.

database.chat.get_message returns None (not a tuple) when the message id does not
exist. The report handlers used to unpack it unconditionally
(`message, msg_doc_id = get_message(...)`), which raised TypeError -> HTTP 500 on a
missing id instead of the intended 404 (the following `if message is None` guard was
unreachable). They now check the result before unpacking.

routers.chat has a heavy import graph (typesense/pinecone/langchain/etc.). It is
imported under a stub finder that auto-mocks those namespaces (fastapi/pydantic stay
real). The stubbing lives inside a module-scoped fixture (not at module scope) so it
does not pollute global import state, and its cost stays out of the test call phase.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'multipart',
)


def _is_stubbed(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


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
        return importlib.machinery.ModuleSpec(name, self, is_package=True) if _is_stubbed(name) else None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


@pytest.fixture(scope="module")
def chat_router():
    """Import routers.chat under a stub finder, restoring sys.modules afterwards.

    Kept inside a fixture (function scope, not module scope) so it never leaves global
    import state mutated for other test files.
    """
    finder = _Finder()
    saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
    for n in list(sys.modules):
        if _is_stubbed(n):
            sys.modules.pop(n, None)
    sys.meta_path.insert(0, finder)
    try:
        from routers import chat as mod
    finally:
        sys.meta_path.remove(finder)
        for n in list(sys.modules):
            if _is_stubbed(n) and n not in saved:
                sys.modules.pop(n, None)
        sys.modules.update(saved)
    return mod


def test_report_missing_message_returns_404_not_500(chat_router):
    # get_message returns None for an unknown id; the handler must translate that into a
    # 404, not crash trying to unpack None into (message, doc_id).
    with patch.object(chat_router.chat_db, "get_message", return_value=None):
        with pytest.raises(HTTPException) as exc:
            chat_router.report_message(message_id="does-not-exist", uid="u1")

    assert exc.value.status_code == 404
