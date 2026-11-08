"""Static guard: deletion feedback must never create an account-deletion marker.

Parses database/users.py with ast and checks the writer's calls. Importing the
module needs Firestore, so this test does not import it.
"""

import ast
from pathlib import Path

USERS_PATH = Path(__file__).resolve().parents[2] / 'database' / 'users.py'


def _feedback_function() -> ast.FunctionDef:
    tree = ast.parse(USERS_PATH.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'set_user_deletion_feedback':
            return node
    raise AssertionError('set_user_deletion_feedback not found')


def _method_calls(function: ast.FunctionDef) -> list[str]:
    names = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


def _is_account_deletion_document_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'account_deletion_document'
    )


def test_feedback_writer_uses_update_and_never_set():
    calls = _method_calls(_feedback_function())
    assert 'update' in calls
    assert 'set' not in calls, 'a set() here can create a marker with no wipe_status'


def test_feedback_update_targets_the_marker_document():
    # Method name alone is not enough: the update must go to the marker doc itself.
    updates_marker = [
        node
        for node in ast.walk(_feedback_function())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'update'
        and _is_account_deletion_document_call(node.func.value)
    ]
    assert updates_marker, 'feedback must call .update() on account_deletion_document(uid)'


def test_feedback_writer_has_no_merge_true_write():
    for node in ast.walk(_feedback_function()):
        if isinstance(node, ast.keyword) and node.arg == 'merge':
            raise AssertionError('merge write would allow creating a marker')
