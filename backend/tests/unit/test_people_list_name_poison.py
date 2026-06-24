"""Regression test for the /v1/users/people poison-page bug.

get_all_people returned raw Firestore dicts for FastAPI to coerce against
response_model=List[Person]. A single legacy/malformed person doc (e.g. one
missing the required 'name' field) made response_model validation 500 the
ENTIRE list, hiding every other valid person from the user.

The fix validates each doc into a Person inside the handler with a per-record
try/except, skipping malformed docs and returning only the valid ones.

Red (pre-fix): get_all_people returns the raw list including the name-less dict.
Green (post-fix): only the one valid Person is returned; the malformed doc is
dropped instead of poisoning the page.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Heavy / unavailable packages that routers.users pulls in transitively. Stub
# them so importing the router is cheap. models.* and pydantic/fastapi are NOT
# stubbed: we want real Pydantic validation of Person to exercise the guard.
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
    'langchain_core',
    'langchain_openai',
    'langchain_google_genai',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'twilio',
    'scipy',
    'tiktoken',
    'pycountry',
    'PIL',
    'websockets',
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


_f = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
for n in list(sys.modules):
    if _is_stubbed(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from routers import users as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)


from models.other import Person


def test_get_all_people_skips_name_less_doc():
    """One name-less (malformed) person doc must not poison the whole list."""
    valid = {'id': 'p-valid', 'name': 'Alice'}
    malformed = {'id': 'p-bad'}  # missing required 'name'

    # get_people enters routers.users via `from database.users import *`; under
    # the stub-finder database.* is mocked, so create=True binds it for the call.
    with patch.object(mod, 'get_people', return_value=[valid, malformed], create=True):
        result = mod.get_all_people(include_speech_samples=False, uid='u1')

    # Only the valid person survives, returned as a validated Person model.
    assert len(result) == 1
    assert all(isinstance(p, Person) for p in result)
    assert result[0].id == 'p-valid'
    assert result[0].name == 'Alice'
    assert all(getattr(p, 'id', None) != 'p-bad' for p in result)


def test_get_all_people_returns_all_valid():
    """All well-formed docs are returned as Person models."""
    people = [
        {'id': 'p1', 'name': 'Alice'},
        {'id': 'p2', 'name': 'Bob'},
    ]
    with patch.object(mod, 'get_people', return_value=people, create=True):
        result = mod.get_all_people(include_speech_samples=False, uid='u1')

    assert len(result) == 2
    assert all(isinstance(p, Person) for p in result)
    assert {p.id for p in result} == {'p1', 'p2'}
