"""memory_summary rating endpoints are write-no-ops.

Importing `routers.users` pulls the full app graph; these tests assert the
function bodies so they stay runnable in a slim unit venv.
"""

from pathlib import Path
import ast

USERS_PY = Path(__file__).resolve().parents[2] / 'routers' / 'users.py'


def _function_source(name: str) -> str:
    tree = ast.parse(USERS_PY.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(f'{name} not found in routers/users.py')


def test_memory_summary_post_is_noop():
    src = _function_source('set_memory_summary_rating')
    assert "return {'status': 'ok'}" in src or 'return {"status": "ok"}' in src
    assert 'set_memory_summary_rating_score' not in src
    assert 'set_chat_message_rating_score' not in src


def test_memory_summary_get_never_has_rating():
    src = _function_source('get_memory_summary_rating')
    assert "'has_rating': False" in src or '"has_rating": False' in src
