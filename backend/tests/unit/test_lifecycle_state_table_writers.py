"""Conservative AST guard against an undeclared lifecycle payload builder.

Dictionary construction counts even before it reaches a storage helper. This
intentionally over-approximates writes (including a few query/response maps),
and sees nested transaction functions without importing any serving module.
"""

import ast
import runpy
from functools import lru_cache
from pathlib import Path

import pytest

from tests.support.lifecycle_state_table import FIELD_BUILDERS, STATES

BACKEND = Path(__file__).resolve().parents[2]
UNIQUE_FIELDS = frozenset(
    {
        'record_audio_closed',
        'record_upload_sessions',
        'record_upload_failed',
        'record_audio_partial',
        'summary_first_pending_at',
        'summary_due_at',
        'summary_completed_at',
        'finalization_status',
        'wrap_up_requested_at',
        'composed_fingerprint',
        'recorded_merged_into',
        'sync_bridge_pending',
        'projection_state',
    }
)
STATUS_MODULES = frozenset(
    {
        'utils/conversations/lifecycle.py',
        'database/conversations.py',
        'database/conversation_finalization_jobs.py',
        'database/conversation_terminal_title.py',
        'database/episodes.py',
        'database/episode_timeline.py',
    }
)


def field_scope(module):
    fields = set(UNIQUE_FIELDS)
    if module.startswith('database/') or module in STATUS_MODULES or module == 'utils/episodes/service.py':
        fields.add('status')
    if (
        module.startswith(('utils/batch_pipeline/', 'database/batch_pipeline_'))
        or module == 'database/record_partial.py'
    ):
        fields.add('state')
    if module in {'utils/fair_use.py', 'database/fair_use.py'}:
        fields.add('stage')
    return fields


def field_builders(source):
    """Find literal dict keys, item writes, dict/update kwargs and setdefault.

    A read such as row.get('status') is not a write. Function paths include
    classes and nested transaction closures, so moving a write changes its owner.
    Dynamic-key storage wrappers remain the existing ownership guard's concern;
    this inventory is not whole-program dataflow analysis.
    """
    found = {}
    tree = ast.parse(source)
    constants = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants.setdefault(target.id, set()).add(node.value.value)

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = visit_ClassDef
        visit_AsyncFunctionDef = visit_ClassDef

        def add(self, key):
            if isinstance(key, ast.Name):
                for value in constants.get(key.id, ()):
                    self.add(ast.Constant(value))
            if (
                isinstance(key, ast.Attribute)
                and isinstance(key.value, ast.Name)
                and key.value.id == 'bridge_pending'
                and key.attr == 'FIELD'
            ):
                key = ast.Constant('sync_bridge_pending')
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.setdefault(key.value, set()).add('.'.join(self.stack) or '<module>')

        def visit_Dict(self, node):
            for key in node.keys:
                self.add(key)
            self.generic_visit(node)

        def visit_Subscript(self, node):
            if isinstance(node.ctx, ast.Store):
                self.add(node.slice)
            self.generic_visit(node)

        def visit_Call(self, node):
            constructor = isinstance(node.func, ast.Name) and node.func.id == 'dict'
            update = isinstance(node.func, ast.Attribute) and node.func.attr in {'update', 'set', 'setdefault'}
            if constructor or update:
                for keyword in node.keywords:
                    self.add(ast.Constant(keyword.arg))
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'setdefault' and node.args:
                    self.add(node.args[0])
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def candidate_modules():
    found = set(FIELD_BUILDERS)
    for directory in ('database', 'utils'):
        for path in sorted((BACKEND / directory).rglob('*.py')):
            module = path.relative_to(BACKEND).as_posix()
            source = path.read_text()
            if any(field in source for field in field_scope(module)):
                found.add(module)
    return sorted(found)


@lru_cache(maxsize=None)
def module_builders(module):
    fields = field_scope(module)
    source = (BACKEND / module).read_text()
    return {key: sorted(owners) for key, owners in field_builders(source).items() if key in fields}


@pytest.mark.parametrize('module', candidate_modules())
def test_no_undeclared_or_stale_lifecycle_field_builder(module):
    assert module_builders(module) == FIELD_BUILDERS.get(
        module, {}
    ), f'Review new/moved/removed lifecycle writers in {module} and update the declared table'


@pytest.mark.parametrize('row', STATES, ids=lambda row: row.key)
def test_every_state_names_existing_entry_field_builders(row):
    assert row.entered_by, f'{row.key} has no declared entry payload builder'
    assert set(row.fields) <= {field for fields in FIELD_BUILDERS.values() for field in fields}
    for writer in row.entered_by:
        assert any(writer.function in module_builders(writer.module).get(field, ()) for field in row.fields)


@pytest.mark.parametrize(
    'statement',
    [
        "row['record_audio_closed'] = True",
        "row.update(record_audio_closed=True)",
        "row.setdefault('record_audio_closed', True)",
        "tx.update(ref, {'record_audio_closed': True})",
        "tx.set(ref, dict(record_audio_closed=True))",
    ],
)
def test_scanner_detects_new_writer_forms(statement):
    source = 'def fourth_writer():\n    ' + statement + '\n'
    assert field_builders(source)['record_audio_closed'] == {'fourth_writer'}


def test_scanner_distinguishes_nested_owners_and_reads():
    source = (
        "class Store:\n    def write(self):\n        def commit(tx):\n"
        "            tx.update(ref, {'record_audio_closed': True})\n"
        "        return row.get('record_upload_failed')\n"
    )
    assert field_builders(source) == {'record_audio_closed': {'Store.write.commit'}}


def test_new_unique_field_writer_in_an_unlisted_module_is_in_scope():
    module = 'database/fourth_writer.py'
    discovered = field_builders("def surprise():\n    row['record_upload_failed'] = True\n")
    assert 'record_upload_failed' in field_scope(module)
    assert discovered['record_upload_failed'] == {'surprise'}
    assert module not in FIELD_BUILDERS


def test_literal_alias_cannot_hide_a_fourth_writer():
    source = "FIELD = 'record_upload_failed'\ndef fourth_writer(row):\n    row[FIELD] = True\n"
    assert field_builders(source)['record_upload_failed'] == {'fourth_writer'}


def literal_states(source, field):
    """Literal state entries, including conditional writes and enum values."""
    values = set()

    def add(value):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
        elif isinstance(value, ast.IfExp):
            add(value.body)
            add(value.orelse)
        elif isinstance(value, ast.Attribute) and value.attr == 'value':
            if isinstance(value.value, ast.Attribute) and isinstance(value.value.value, ast.Name):
                if value.value.value.id == 'ConversationStatus':
                    values.add(value.value.attr)

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == field:
                    add(value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == field
                ):
                    add(node.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            if name in {'dict', 'update'}:
                for keyword in node.keywords:
                    if keyword.arg == field:
                        add(keyword.value)
    return values


@pytest.mark.parametrize(
    'module',
    [
        'utils/batch_pipeline/scheduler.py',
        'utils/batch_pipeline/live.py',
        'utils/batch_pipeline/retry_policy.py',
        'database/record_partial.py',
    ],
)
def test_new_batch_job_state_needs_a_table_row_even_inside_an_existing_writer(module):
    actual = literal_states((BACKEND / module).read_text(), 'state')
    assert actual <= {row.state for row in STATES if row.machine == 'batch'}


def test_new_finalization_status_needs_a_table_row():
    tree = ast.parse((BACKEND / 'database/conversation_finalization_jobs.py').read_text())
    declaration = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'FinalizationJobStatus' for target in node.targets)
    )
    assert isinstance(declaration.value, ast.Subscript)
    assert set(ast.literal_eval(declaration.value.slice)) == {
        row.state for row in STATES if row.machine == 'finalization'
    }


def test_state_probe_detects_a_fourth_state_in_the_same_writer():
    assert literal_states("def enter(row):\n    row.update(state='new_unowned_state')\n", 'state') == {
        'new_unowned_state'
    }


@pytest.mark.parametrize(
    'path',
    [
        'backend/utils/conversations/lifecycle.py',
        'backend/utils/batch_pipeline/live.py',
        'backend/database/record_audio.py',
        'backend/database/conversation_finalization_jobs.py',
        'backend/database/episodes.py',
        'backend/utils/fair_use.py',
        'backend/utils/observability/fair_use.py',
        'backend/utils/sync/assignment.py',
        'backend/utils/previously_unrelated.py',
    ],
)
def test_changed_source_selects_both_lifecycle_guards(path):
    selector = runpy.run_path(str(BACKEND / 'scripts/select_backend_unit_tests.py'))
    expected = set(selector['LIFECYCLE_INVARIANT_TESTS'])
    selected, _ = selector['tests_for_changed_paths']([path], sorted(expected))
    assert expected <= set(selected)
