"""GET /v1/conversations/{id}/photos must skip a base64-less photo, not 500 the whole list.

The route declares ``response_model=List[ConversationPhoto]`` and ``ConversationPhoto.base64`` is a
required ``str``. ``database.conversations.get_conversation_photos`` returned raw Firestore dicts, so a
single legacy/partial photo missing ``base64`` made FastAPI raise ResponseValidationError -> HTTP 500
for the entire list. The fix drops the malformed record (mirroring the data-protection migration's
existing base64-less skip) and keeps the rest.

We import the REAL ``database.conversations`` under a stub finder that auto-mocks the heavy leaf
dependencies (utils.*, firebase_admin, google, ...) while keeping ``models`` real -- the real
``ConversationPhoto`` is what raises ValidationError on a malformed record. ``database._client.db`` is a
stub whose photos sub-collection ``.stream()`` is driven to return one valid + one base64-less doc, then
``get_conversation_photos`` is called directly and its output validated through ``ConversationPhoto`` to
reproduce the route's response_model enforcement.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub the heavy leaves that database.conversations imports, but NOT the 'database' package itself
# (we need the real database.conversations) and NOT 'models' (we need the real ConversationPhoto).
_STUB = (
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'httpx',
    'database._client',
    'database.users',
    'database.helpers',
    'database.vector_db',
)


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for _n in list(sys.modules):
    if _is(_n):
        sys.modules.pop(_n, None)
# database.helpers provides decorators (set_data_protection_level, prepare_for_write, ...) applied at
# import time as @decorator -- a bare MagicMock attribute isn't usable as a decorator, so pre-register
# a helpers stub whose decorators return the function unchanged before the real module imports it.
_helpers_stub = _AM('database.helpers')
_helpers_stub.set_data_protection_level = lambda *a, **k: (lambda fn: fn)
_helpers_stub.prepare_for_write = lambda *a, **k: (lambda fn: fn)
_helpers_stub.prepare_for_read = lambda *a, **k: (lambda fn: fn)
_helpers_stub.with_photos = lambda *a, **k: (lambda fn: fn)
sys.modules['database.helpers'] = _helpers_stub
sys.meta_path.insert(0, _f)
try:
    import database.conversations as conversations_db  # noqa: E402  (the REAL module under test)
    from models.conversation_photo import ConversationPhoto  # noqa: E402  (real Pydantic model)
finally:
    sys.meta_path.remove(_f)
    for _n in list(sys.modules):
        if _is(_n) and _n not in _sav:
            sys.modules.pop(_n, None)
    sys.modules.update(_sav)


def _photo_doc(data):
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def _drive_db_with(docs):
    """Point conversations_db.db at a stub whose photos sub-collection .stream() yields ``docs``."""
    photos_ref = MagicMock()
    photos_ref.stream.return_value = list(docs)

    conversation_ref = MagicMock()
    conversation_ref.collection.return_value = photos_ref

    conversations_subcoll = MagicMock()
    conversations_subcoll.document.return_value = conversation_ref

    user_ref = MagicMock()
    user_ref.collection.return_value = conversations_subcoll

    users_coll = MagicMock()
    users_coll.document.return_value = user_ref

    conversations_db.db.collection = MagicMock(return_value=users_coll)


_VALID = {'id': 'good', 'base64': 'aGVsbG8=', 'description': 'a photo'}
_MALFORMED = {'id': 'bad', 'description': 'legacy photo with no base64'}  # missing required base64


def test_malformed_photo_is_skipped_not_returned():
    _drive_db_with([_photo_doc(_VALID), _photo_doc(_MALFORMED)])

    photos = conversations_db.get_conversation_photos('uid1', 'conv1')

    # Only the valid photo survives the getter.
    assert [p['id'] for p in photos] == ['good']
    # And the surviving list validates cleanly against the route's response_model -- no 500.
    validated = [ConversationPhoto(**p) for p in photos]
    assert validated[0].base64 == 'aGVsbG8='


def test_raw_malformed_photo_would_have_500ed_response_model():
    # Guard the premise: a base64-less dict really does fail ConversationPhoto validation, which is
    # exactly what response_model=List[ConversationPhoto] raises (ResponseValidationError -> 500).
    with pytest.raises(ValidationError):
        ConversationPhoto(**_MALFORMED)


def test_all_malformed_returns_empty():
    _drive_db_with([_photo_doc({'id': 'b1'}), _photo_doc({'id': 'b2'})])

    photos = conversations_db.get_conversation_photos('uid1', 'conv1')

    assert photos == []


def test_all_valid_photos_pass_through_unchanged():
    second = {'id': 'good2', 'base64': 'd29ybGQ=', 'description': None}
    _drive_db_with([_photo_doc(_VALID), _photo_doc(second)])

    photos = conversations_db.get_conversation_photos('uid1', 'conv1')

    assert [p['id'] for p in photos] == ['good', 'good2']
    assert [ConversationPhoto(**p).base64 for p in photos] == ['aGVsbG8=', 'd29ybGQ=']
