"""search_google_contacts must not drop a found email when the contact has an empty 'names' list.

In the "Other Contacts" branch, the code read the display name with
``person.get('names', [{}])[0].get('displayName', query)``. The ``[{}]`` default is only used when
the ``'names'`` key is ABSENT; when the People API returns a contact that has an email but
``'names': []`` (an empty list), ``person.get('names', [{}])`` returns ``[]`` and ``[][0]`` raises
IndexError. That IndexError is swallowed by the broad ``except Exception`` around the block, so the
email that was already extracted is silently discarded and the function returns ``None`` -- the
contact is dropped.

The fix guards the index access (``names = person.get('names') or [{}]``; only index when truthy) so
the email is still returned. This test loads the real calendar_tools module under a stub finder
(its database/utils/langchain deps are stubbed) and drives search_google_contacts with a mocked
auth client whose otherContacts:search returns a contact with an email but ``'names': []``.
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

# The module under test lives at this path. We load it directly by file location (it uses only
# absolute imports) so its heavy database/utils/langchain dependencies can be stubbed out.
_TARGET_NAME = 'utils.retrieval.tools.calendar_tools'
_TARGET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'utils',
    'retrieval',
    'tools',
    'calendar_tools.py',
)

# Heavy deps to stub. We stub the whole ``utils`` and ``database`` trees so the parent package
# ``utils.retrieval.tools`` is replaced with an empty stub (its real __init__ pulls in every sibling
# tool, e.g. langchain_openai) -- the target leaf is loaded directly by file path and is the only
# real ``utils.*`` module. The ``_TARGET_NAME`` exclusion in ``_is`` / ``find_spec`` keeps it real.
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
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
)


def _is(name):
    if name == _TARGET_NAME:
        return False
    return any(name == p or name.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name == _TARGET_NAME:
            return importlib.util.spec_from_file_location(name, _TARGET_PATH)
        if _is(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AM(spec.name)

    def exec_module(self, module):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n) or n == _TARGET_NAME}
for n in list(sys.modules):
    if _is(n) or n == _TARGET_NAME:
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    mod = importlib.import_module(_TARGET_NAME)
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if (_is(n) or n == _TARGET_NAME) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


def _make_response(payload):
    """Build a fake httpx-style response returning the given JSON payload with status 200."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.text = ''
    return resp


def _make_client(other_contacts_payload):
    """Fake auth client: My Contacts returns no results; Other Contacts returns the payload."""
    client = MagicMock()

    async def _get(url, headers=None, params=None):
        if 'searchContacts' in url:
            # My Contacts: nothing found, so the code falls through to Other Contacts.
            return _make_response({'results': []})
        # otherContacts:search (both the warm-up empty query and the real query).
        return _make_response(other_contacts_payload)

    client.get = AsyncMock(side_effect=_get)
    return client


def test_email_returned_when_names_is_empty_list():
    """A contact with an email but 'names': [] must still yield the email, not be dropped."""
    payload = {'results': [{'person': {'emailAddresses': [{'value': 'a@b.com'}], 'names': []}}]}
    client = _make_client(payload)
    with patch.object(mod, 'get_auth_client', return_value=client), patch.object(mod.asyncio, 'sleep', AsyncMock()):
        result = asyncio.run(mod.search_google_contacts('token-123', 'Riddhi Gupta'))
    assert result == 'a@b.com'


def test_email_returned_when_names_present():
    """Sanity: a contact that has a name still returns the email (happy path unbroken)."""
    payload = {'results': [{'person': {'emailAddresses': [{'value': 'c@d.com'}], 'names': [{'displayName': 'Carol'}]}}]}
    client = _make_client(payload)
    with patch.object(mod, 'get_auth_client', return_value=client), patch.object(mod.asyncio, 'sleep', AsyncMock()):
        result = asyncio.run(mod.search_google_contacts('token-123', 'Carol'))
    assert result == 'c@d.com'
