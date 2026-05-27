"""Shared fixtures for unit tests.

Sets up database mocks and clears BYOK caches between tests to prevent
cross-test contamination when multiple test files are collected together.

The key invariant: sys.modules['database'].X MUST be the same object as
sys.modules['database.X'].  Otherwise @patch('database.X.func') patches
the auto-attribute on the parent MagicMock instead of the child entry.
"""

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('DEEPGRAM_API_KEY', 'dg-test-fake-for-unit-tests')
os.environ.setdefault('GOOGLE_API_KEY', 'goog-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_DB_SUBMODULES = [
    '_client',
    'action_items',
    'advice',
    'announcements',
    'app_review_config',
    'apps',
    'auth',
    'cache',
    'calendar_meetings',
    'chat',
    'conversations',
    'daily_summaries',
    'dev_api_key',
    'fair_use',
    'focus_sessions',
    'folders',
    'goals',
    'import_jobs',
    'llm_usage',
    'mcp_api_key',
    'memories',
    'notifications',
    'phone_call_config',
    'phone_calls',
    'phone_call_usage',
    'redis_db',
    'screen_activity',
    'staged_tasks',
    'sync_jobs',
    'tasks',
    'trends',
    'users',
    'user_usage',
    'vector_db',
    'wrapped',
]

if 'database' not in sys.modules:
    sys.modules['database'] = MagicMock()

_db_parent = sys.modules['database']

for _sub in _DB_SUBMODULES:
    _full = f'database.{_sub}'
    if _full not in sys.modules:
        sys.modules[_full] = MagicMock()
    setattr(_db_parent, _sub, sys.modules[_full])

sys.modules.setdefault('utils.other.storage', MagicMock())

# firebase_admin mock — needed because auth_middleware.py imports
# InvalidIdTokenError at module level, and router files import auth_middleware.
if 'firebase_admin' not in sys.modules:
    _firebase_mock = MagicMock()

    class _InvalidIdTokenError(Exception):
        pass

    _firebase_auth_mock = MagicMock()
    _firebase_auth_mock.InvalidIdTokenError = _InvalidIdTokenError
    _firebase_mock.auth = _firebase_auth_mock
    sys.modules['firebase_admin'] = _firebase_mock
    sys.modules['firebase_admin.auth'] = _firebase_auth_mock
    sys.modules['firebase_admin.credentials'] = MagicMock()


def pytest_runtest_setup(item):
    """Clear BYOK state cache before every test to prevent stale cache hits."""
    try:
        from utils.byok import _byok_state_cache

        _byok_state_cache.clear()
    except (ImportError, AttributeError):
        pass
