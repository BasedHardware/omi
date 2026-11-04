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

from tests.support.lifecycle_ast import builders, constant_names, fields_for, literal_key, payload_sites
from tests.support.lifecycle_state_table import FIELD_BUILDERS, FIELD_SITES, STATES

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
    return fields_for(module)


def field_builders(source):
    return {field: set(owners) for field, owners in builders(payload_sites(source)).items()}


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
def module_sites(module):
    source = (BACKEND / module).read_text()
    return [site for site in payload_sites(source) if site[1] in field_scope(module)]


@lru_cache(maxsize=None)
def module_builders(module):
    return builders(module_sites(module))


@pytest.mark.parametrize('module', candidate_modules())
def test_no_undeclared_or_stale_lifecycle_field_builder(module):
    assert module_sites(module) == FIELD_SITES.get(
        module, []
    ), f'Review new/moved/removed lifecycle payload sites in {module}; values, sibling fields and duplicate sites are significant'
    assert module_builders(module) == FIELD_BUILDERS.get(module, {})


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


def literal_states(source, field, *, nested_fields=()):
    """Literal state entries, including conditional writes and enum values."""
    values = set()
    constants = constant_names(ast.parse(source))

    def add(value):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
        elif isinstance(value, ast.Name):
            values.update(constants.get(value.id, ()))
        elif isinstance(value, ast.IfExp):
            add(value.body)
            add(value.orelse)
        elif isinstance(value, ast.Attribute) and value.attr == 'value':
            if isinstance(value.value, ast.Attribute) and isinstance(value.value.value, ast.Name):
                if value.value.value.id == 'ConversationStatus':
                    values.add(value.value.attr)

    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            parent = parents.get(node)
            if isinstance(parent, ast.Assign) and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value in nested_fields
                for target in parent.targets
            ):
                continue
            for key, value in zip(node.keys, node.values):
                if field in literal_key(key, constants):
                    add(value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and field in literal_key(target.slice, constants):
                    add(node.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            if name in {'dict', 'update', 'set', 'setdefault'}:
                for keyword in node.keywords:
                    if keyword.arg == field:
                        add(keyword.value)
                if name == 'setdefault' and len(node.args) >= 2 and field in literal_key(node.args[0], constants):
                    add(node.args[1])
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
    # These three labels are helper return envelopes, never persisted job
    # statuses. A fourth literal still needs explicit review and a state row.
    response_statuses = {'missing', 'identity_mismatch', 'recorded'}
    allowed = {row.state for row in STATES if row.machine in {'conversation', 'finalization'}} | response_statuses
    assert literal_states((BACKEND / 'database/conversation_finalization_jobs.py').read_text(), 'status') <= allowed


def test_state_probe_detects_a_fourth_state_in_the_same_writer():
    assert literal_states("def enter(row):\n    row.update(state='new_unowned_state')\n", 'state') == {
        'new_unowned_state'
    }


@pytest.mark.parametrize(
    'source',
    [
        "def enter(job):\n    job.setdefault('state', 'new_unowned_state')\n",
        "FIELD = 'state'\ndef enter(job):\n    job.setdefault(FIELD, 'new_unowned_state')\n",
        "NEW = 'new_unowned_state'\ndef enter(job):\n    job.setdefault('state', NEW)\n",
    ],
)
def test_r2_positional_setdefault_values_require_state_rows(source):
    assert literal_states(source, 'state') == {'new_unowned_state'}


def test_r2_setdefault_on_another_field_does_not_invent_a_state():
    assert literal_states("def enter(job):\n    job.setdefault('other', 'new_unowned_state')\n", 'state') == set()


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


def test_status_writers_in_previously_unrelated_utils_are_in_scope():
    assert 'status' in field_scope('utils/previously_unrelated.py')
    assert field_builders("def enter(row):\n    row.update(status='archiving')\n") == {'status': {'enter'}}


def test_same_function_value_changes_and_duplicate_paths_change_the_inventory():
    before = "def enter(row):\n    row.update(status='processing')\n"
    changed = before.replace("'processing'", "'archiving'")
    extra = before + "    row.update(status='processing')\n"
    assert field_builders(before) == field_builders(changed) == field_builders(extra)
    assert payload_sites(before) != payload_sites(changed)
    assert payload_sites(before) != payload_sites(extra)


def test_changed_literal_value_alias_in_an_existing_writer_changes_the_inventory():
    before = "def enter(row):\n    status = 'processing'\n    row.update(status=status)\n"
    after = before.replace("'processing'", "'archiving'")
    assert field_builders(before) == field_builders(after)
    assert payload_sites(before) != payload_sites(after)


def test_conversation_status_enum_and_literal_writes_have_rows():
    source = (BACKEND / 'models/conversation_enums.py').read_text()
    model = next(
        node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == 'ConversationStatus'
    )
    declared = {
        node.value.value
        for node in model.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    }
    allowed = {row.state for row in STATES if row.machine == 'conversation'}
    assert declared == allowed
    for module in (
        'database/conversations.py',
        'database/conversation_terminal_title.py',
        'utils/conversations/lifecycle.py',
    ):
        # speaker_resolution.status is a nested independent lifecycle. Only
        # that exact dictionary is excluded; a top-level 'resolved' must fail.
        assert (
            literal_states((BACKEND / module).read_text(), 'status', nested_fields=('speaker_resolution',)) <= allowed
        )


def test_nested_speaker_status_does_not_exempt_a_conversation_status():
    source = "def enter(row):\n    row['speaker_resolution'] = {'status': 'resolved'}\n    row['status'] = 'resolved'\n"
    assert literal_states(source, 'status', nested_fields=('speaker_resolution',)) == {'resolved'}


@pytest.mark.parametrize(
    'module',
    sorted(module for module, sites in FIELD_SITES.items() if any(site[1] == 'projection_state' for site in sites)),
)
def test_every_projection_state_literal_has_a_row(module):
    assert literal_states((BACKEND / module).read_text(), 'projection_state') <= {
        row.state for row in STATES if row.machine == 'batch_projection'
    }


@pytest.mark.parametrize('field,machine', [('status', 'conversation'), ('projection_state', 'batch_projection')])
def test_unmodeled_state_in_an_existing_writer_is_rejected(field, machine):
    source = f"def existing_writer(row):\n    row['{field}'] = 'archiving'\n"
    assert not literal_states(source, field) <= {row.state for row in STATES if row.machine == machine}


def test_additive_area_does_not_narrow_scheduler_coverage(monkeypatch):
    selector = runpy.run_path(str(BACKEND / 'scripts/select_backend_unit_tests.py'))
    all_tests = selector['discover_all_tests']()
    select = selector['tests_for_changed_paths']
    selected, _ = select(['backend/utils/batch_pipeline/scheduler.py'], all_tests)
    assert 'tests/unit/test_batch_pipeline_scheduler.py' in selected
    globals_ = select.__globals__
    monkeypatch.setitem(
        globals_,
        'AREA_TESTS',
        tuple(area for area in globals_['AREA_TESTS'] if area[2] != selector['LIFECYCLE_INVARIANT_TESTS']),
    )
    monkeypatch.setitem(globals_, 'LIFECYCLE_SOURCE_REGRESSION_TESTS', {})
    without_guard_area, _ = select(['backend/utils/batch_pipeline/scheduler.py'], all_tests)
    assert set(without_guard_area) <= set(selected)


def test_new_unmapped_lifecycle_source_keeps_the_full_fallback(monkeypatch):
    selector = runpy.run_path(str(BACKEND / 'scripts/select_backend_unit_tests.py'))
    all_tests = selector['discover_all_tests']()
    select = selector['tests_for_changed_paths']
    globals_ = select.__globals__
    monkeypatch.setitem(
        globals_,
        'AREA_TESTS',
        tuple(area for area in globals_['AREA_TESTS'] if area[2] == selector['LIFECYCLE_INVARIANT_TESTS']),
    )
    monkeypatch.setitem(globals_, 'workflow_contract_matches_path', lambda path: False)
    monkeypatch.setitem(globals_, 'workflow_contract_tests_for_path', lambda path, tests: [])
    selected, _ = select(['backend/utils/conversations/new_unmapped_entry.py'], all_tests)
    assert set(selected) == set(all_tests)


@pytest.mark.parametrize('module', ['utils/fair_use.py', 'database/fair_use.py'])
def test_fair_use_state_literals_have_rows(module):
    assert literal_states((BACKEND / module).read_text(), 'stage') <= {
        row.state for row in STATES if row.machine == 'fair_use'
    }
