"""Static tripwire: the enrichment callback and its frozen legacy copy stay identical.

C2 moved the ``sr-`` callback to ``utils/enrichment/callback.py``. ``utils/sync/pipeline.py`` is frozen
(#21932/#20662) and keeps its copy for the non-coalescing direct path, so a change to either body must be
mirrored until the legacy copy is deleted (C11). Log calls are excluded: the new copy logs no conversation id.
This compares source structure only; behaviour is covered by the callback tests that drive the legacy copy
and by the batch enrichment tests that drive this one.
"""

import ast
from pathlib import Path

from utils.enrichment import callback

BACKEND = Path(__file__).resolve().parents[2]


def _function(path: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((BACKEND / path).read_text())
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


class _DropLogsAndDocstrings(ast.NodeTransformer):
    def visit_Expr(self, node: ast.Expr):
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return None
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == 'logger'
        ):
            return None
        return node


def _shape(node: ast.FunctionDef) -> str:
    body = ast.Module(body=[_DropLogsAndDocstrings().visit(statement) for statement in node.body], type_ignores=[])
    return ast.dump(ast.fix_missing_locations(body), include_attributes=False)


def test_callback_body_matches_the_legacy_copy():
    legacy = _function('utils/sync/pipeline.py', '_reprocess_conversation_after_update')
    moved = _function('utils/enrichment/callback.py', 'enrich_conversation')
    assert ast.dump(legacy.args) == ast.dump(moved.args)
    assert _shape(legacy) == _shape(moved)


def test_callback_helpers_match_the_legacy_copy():
    for legacy_name, moved_name in (
        ('_run_conversation_created_webhook', '_run_conversation_created_webhook'),
        ('_require_current_conversation_persistence', '_require_current_conversation_persistence'),
    ):
        legacy = _function('utils/sync/pipeline.py', legacy_name)
        moved = _function('utils/enrichment/callback.py', moved_name)
        assert _shape(legacy) == _shape(moved), legacy_name


def test_lineage_retry_language_matches_the_legacy_sentinel():
    legacy = ast.parse((BACKEND / 'utils/sync/pipeline.py').read_text())
    values = [
        node.value.value
        for node in legacy.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == '_LINEAGE_RETRY_LANGUAGE' for target in node.targets)
    ]
    assert values == [callback._LINEAGE_RETRY_LANGUAGE]
