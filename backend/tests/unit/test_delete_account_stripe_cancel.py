"""Regression test for issue #6750 — delete-account must cancel the active Stripe subscription.

Before the fix, DELETE /v1/users/delete-account revoked Firebase auth and wiped Firestore but never
canceled the user's Stripe subscription, so a paying user kept getting billed with no way to log back
in and cancel. The handler now cancels the subscription (best-effort) before the wipe.

routers/users.py has a heavy import graph (star imports, `from database import (...)`), so we install
a meta-path finder that auto-stubs the database/utils/external namespaces, then call delete_account()
directly with the relevant collaborators patched.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


class _AutoMockModule(types.ModuleType):
    __path__ = []  # behave as a package so submodule imports resolve to stubs

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUB_PREFIXES = (
    'database',
    'utils',
    'firebase_admin',
    'google.cloud',
    'google.api_core',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'pytz',
    'twilio',
)


def _should_stub(name: str) -> bool:
    if name == 'utils.other.endpoints':  # provided as a real shim below
        return False
    return any(name == p or name.startswith(p + '.') for p in _STUB_PREFIXES)


def _remove_module_tree(prefix: str) -> None:
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + '.'):
            sys.modules.pop(name, None)


for _prefix in _STUB_PREFIXES:
    _remove_module_tree(_prefix)


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self.created = set()

    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        self.created.add(spec.name)
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


# Install the stub finder only for the duration of importing routers.users, then remove it AND
# the stub modules it created. This keeps the finder/stubs from leaking into other tests when the
# whole suite runs in one process (pytest tests/unit/); routers.users keeps its own references.
_finder = _StubFinder()
sys.meta_path.insert(0, _finder)

# Real shim for the auth dependency module (used in route signatures + as auth.delete_account).
_endpoints = types.ModuleType('utils.other.endpoints')
_endpoints.get_current_user_uid = lambda: 'uid1'
_endpoints.with_rate_limit = lambda dependency, _policy: dependency
_endpoints.delete_account = MagicMock()
_endpoints.get_user = MagicMock()
sys.modules['utils.other.endpoints'] = _endpoints

try:
    import firebase_admin.auth as _fa_auth  # stubbed

    _fa_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
    from routers import users as users_router  # noqa: E402  (heavy import; deps stubbed above)
finally:
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)
    for _name in list(_finder.created) + ['utils.other.endpoints']:
        sys.modules.pop(_name, None)


def _sub(stripe_subscription_id):
    s = MagicMock()
    s.stripe_subscription_id = stripe_subscription_id
    return s


def test_paid_user_subscription_is_canceled_before_wipe():
    with patch.object(
        users_router.users_db, 'get_user_subscription', return_value=_sub('sub_123')
    ) as get_sub, patch.object(
        users_router.stripe_utils, 'cancel_subscription', return_value=MagicMock()
    ) as cancel, patch.object(
        users_router.auth, 'delete_account'
    ) as fb_delete, patch.object(
        users_router, '_background_wipe_user_data'
    ):
        resp = users_router.delete_account(uid='uid1')
    get_sub.assert_called_once_with('uid1')
    cancel.assert_called_once_with('sub_123')
    fb_delete.assert_called_once()  # deletion still proceeds
    assert resp['status'] == 'ok'


def test_free_user_does_not_call_stripe():
    with patch.object(users_router.users_db, 'get_user_subscription', return_value=_sub(None)), patch.object(
        users_router.stripe_utils, 'cancel_subscription'
    ) as cancel, patch.object(users_router.auth, 'delete_account'), patch.object(
        users_router, '_background_wipe_user_data'
    ):
        resp = users_router.delete_account(uid='uid1')
    cancel.assert_not_called()
    assert resp['status'] == 'ok'


def test_stripe_error_does_not_block_deletion():
    with patch.object(users_router.users_db, 'get_user_subscription', return_value=_sub('sub_123')), patch.object(
        users_router.stripe_utils, 'cancel_subscription', side_effect=Exception('stripe down')
    ), patch.object(users_router.auth, 'delete_account') as fb_delete, patch.object(
        users_router, '_background_wipe_user_data'
    ):
        resp = users_router.delete_account(uid='uid1')
    fb_delete.assert_called_once()  # best-effort: Stripe failure must not abort deletion
    assert resp['status'] == 'ok'
