"""GET /v1/goals/{goal_id}/history must clamp days so a negative value cannot reach Firestore.

get_goal_history declared days as Query(default=30, le=365) with no lower bound, then passed it straight
into goals_db.get_goal_history, which uses it as a Firestore .limit(). A negative days reached .limit(-1)
and raised, surfacing as a 500. routers/goals.py has a heavy import graph, so we import it under a stub
finder and call the handler directly.
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

_STUB = ('database', 'utils', 'firebase_admin', 'google', 'pinecone', 'opuslib', 'pydub', 'redis', 'langchain')


def _is_stubbed(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


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
        if _is_stubbed(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
for n in list(sys.modules):
    if _is_stubbed(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _finder)
try:
    from routers import goals as goals_mod
finally:
    sys.meta_path.remove(_finder)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)


def test_negative_days_clamped_to_one():
    db = MagicMock(return_value=[])
    with patch.object(goals_mod.goals_db, 'get_goal_history', db):
        goals_mod.get_goal_history(goal_id='g1', days=-5, uid='u1')
    assert db.call_args.args[2] == 1


def test_oversized_days_clamped_to_365():
    db = MagicMock(return_value=[])
    with patch.object(goals_mod.goals_db, 'get_goal_history', db):
        goals_mod.get_goal_history(goal_id='g1', days=100000, uid='u1')
    assert db.call_args.args[2] == 365
