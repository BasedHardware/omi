"""GET /v1/task-integrations must never return provider credentials to the device.

The handler streamed the whole Firestore document per integration into a `Dict[str, Any]` response,
so every device fetch of the task-integration list handed out the raw provider `access_token` and
`refresh_token`. The handler now projects each document through an allowlist of non-secret display
fields, matching the shape of GET /v1/integrations/{app_key}, which only reports `connected`.

routers/task_integrations.py has a heavy import graph, so it is imported under a stub finder that
auto-mocks those namespaces (keeping models/fastapi/pydantic real), then the endpoint function is
called directly with the users_db reads patched.
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

_STUB = (
    'database',
    'utils',
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


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
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
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from routers import task_integrations as ti
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


STORED = {
    'asana': {
        'connected': True,
        'access_token': 'asana-access-secret',
        'refresh_token': 'asana-refresh-secret',
        'expires_at': '2030-01-01T00:00:00+00:00',
        'user_gid': 'gid-1',
        'workspace_gid': 'ws-1',
        'workspace_name': 'Acme',
        'project_gid': 'pr-1',
        'project_name': 'Roadmap',
        'some_future_provider_secret': 'do-not-leak',
    },
    'clickup': {
        'connected': True,
        'access_token': 'clickup-access-secret',
        'user_id': 'u-1',
        'team_id': 't-1',
        'team_name': 'Team',
        'space_id': 's-1',
        'space_name': 'Space',
        'list_id': 'l-1',
        'list_name': 'List',
    },
}


def _call():
    with patch.object(ti.users_db, 'get_task_integrations', return_value=STORED), patch.object(
        ti.users_db, 'get_default_task_integration', return_value='asana'
    ):
        return ti.get_task_integrations(uid='u1')


def test_response_contains_no_credentials():
    payload = _call().model_dump()
    serialized = repr(payload)

    for secret in ('asana-access-secret', 'asana-refresh-secret', 'clickup-access-secret', 'do-not-leak'):
        assert secret not in serialized

    for integration in payload['integrations'].values():
        assert 'access_token' not in integration
        assert 'refresh_token' not in integration


def test_response_keeps_non_secret_display_fields():
    payload = _call().model_dump()

    assert payload['default_app'] == 'asana'
    assert payload['integrations']['asana'] == {
        'connected': True,
        'expires_at': '2030-01-01T00:00:00+00:00',
        'user_gid': 'gid-1',
        'workspace_gid': 'ws-1',
        'workspace_name': 'Acme',
        'project_gid': 'pr-1',
        'project_name': 'Roadmap',
    }
    assert payload['integrations']['clickup']['team_name'] == 'Team'
    assert payload['integrations']['clickup']['list_id'] == 'l-1'


def test_projection_is_an_allowlist_without_credential_keys():
    assert 'access_token' not in ti.PUBLIC_TASK_INTEGRATION_FIELDS
    assert 'refresh_token' not in ti.PUBLIC_TASK_INTEGRATION_FIELDS
    assert ti.project_task_integration({'access_token': 'x'}) == {'connected': False}
