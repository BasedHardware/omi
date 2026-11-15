"""Pure source/table contracts. Runtime reachability belongs to WP-B2.

Expected failures are enumerated independently in KNOWN_GAPS: never mark a
failure expected simply because an assertion failed. Each parameter receives
one strict xfail for exactly one broken clause. Fixes must update the reviewed
table; a removed gap that still fails, or an improved row left xfailed, fails CI.
"""

import ast
import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from tests.support.lifecycle_state_table import (
    ABANDON_RECORD_PRODUCER,
    CLAUSES,
    FIELD_BUILDERS,
    IMPORT_PAUSED_DWELL_ROWS,
    ORDERING_RULES,
    PATCH_CONTRACTS,
    STATES,
    ordering_holds,
)
from tests.support.lifecycle_ast import EntryPath, definition_fingerprint, entry_deadline_sites, function_node
from utils.conversations.phase import ConversationPhase, EpisodePhase

BACKEND = Path(__file__).resolve().parents[2]
METRIC_MODULES = (
    'utils/metrics.py',
    'database/record_token_lease_metrics.py',
    'utils/batch_pipeline/metrics.py',
    'utils/conversations/summary_delivery.py',
    'utils/observability/fair_use.py',
    'services/conversation_finalization.py',
)


def phase_metric_gauge_names(tree):
    """Expand literal instances using only Gauge suffixes in the real factory."""
    factory = ast.parse(function_source('utils/lifecycle_metrics.py:PhaseMetrics.__init__'))
    suffixes = set()
    for node in ast.walk(factory):
        if not (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Gauge' and node.args
        ):
            continue
        name = node.args[0]
        if (
            isinstance(name, ast.BinOp)
            and isinstance(name.op, ast.Add)
            and isinstance(name.left, ast.Name)
            and name.left.id == 'prefix'
            and isinstance(name.right, ast.Constant)
            and isinstance(name.right.value, str)
        ):
            suffixes.add(name.right.value)
    prefixes = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'PhaseMetrics'
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    return {prefix + suffix for prefix in prefixes for suffix in suffixes}


def literal_gauge_names(tree):
    """Include declared Gauge subclasses without treating counters as stock."""
    gauge_types = {'Gauge'} | {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == 'Gauge' for base in node.bases)
    }
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in gauge_types
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


@lru_cache(maxsize=1)
def gauge_names():
    result = set()
    for module in METRIC_MODULES:
        tree = ast.parse((BACKEND / module).read_text())
        result.update(phase_metric_gauge_names(tree))
        result.update(literal_gauge_names(tree))
    return result


def test_phase_metric_inventory_requires_declared_prefix_and_gauge_suffix():
    tree = ast.parse("PhaseMetrics('declared', []); Counter('made_up_prefix', [])")
    names = phase_metric_gauge_names(tree)
    assert 'declared_new_oldest_age_seconds' in names
    assert 'made_up_prefix_new_oldest_age_seconds' not in names
    assert 'declared_made_up_suffix' not in names


def test_gauge_inventory_recognizes_declared_subclasses_and_rejects_counters():
    tree = ast.parse(
        "class FreshGauge(Gauge): pass\n"
        "class Events(Counter): pass\n"
        "FreshGauge('stock'); Gauge('plain'); Counter('events'); Events('also_events')"
    )
    assert literal_gauge_names(tree) == {'stock', 'plain'}


@lru_cache(maxsize=1)
def alerts():
    result = {}
    for path in sorted((BACKEND / 'charts/monitoring/alerts').glob('*.json')):

        def visit(value):
            if isinstance(value, dict):
                if 'uid' in value and 'data' in value:
                    result[value['uid']] = value
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(json.loads(path.read_text()))
    return result


@lru_cache(maxsize=None)
def module_source(module):
    path = BACKEND / module
    if not path.is_file():
        return '', ast.Module(body=[], type_ignores=[])
    source = path.read_text()
    return source, ast.parse(source)


def scope_definitions(nodes):
    """Find definitions through control flow without entering another scope."""
    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node
        else:
            yield from scope_definitions(ast.iter_child_nodes(node))


@lru_cache(maxsize=None)
def function_source(cite):
    module, _, function = cite.partition(':')
    source, node = module_source(module)
    if not function:
        return source
    for part in function.split('.'):
        node = next(
            (child for child in scope_definitions(node.body) if child.name == part),
            None,
        )
        if node is None:
            return ''
    return ast.get_source_segment(source, node) or ''


def test_function_source_finds_loop_nested_transaction_without_crossing_scopes(monkeypatch):
    source = 'def outer():\n    for item in []:\n        def commit(tx):\n            return item\ndef other():\n    def hidden():\n        pass\n'
    monkeypatch.setitem(
        function_source.__wrapped__.__globals__, 'module_source', lambda path: (source, ast.parse(source))
    )
    read = function_source.__wrapped__
    assert 'return item' in read('synthetic.py:outer.commit')
    assert read('synthetic.py:outer.hidden') == ''
    assert read('synthetic.py:commit') == ''


def assigned_fields(source):
    fields = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            fields.update(
                key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )
        elif (
            isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and isinstance(node.slice, ast.Constant)
        ):
            fields.add(node.slice.value)
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == 'dict'
                or isinstance(node.func, ast.Attribute)
                and node.func.attr in {'update', 'setdefault'}
            ):
                fields.update(keyword.arg for keyword in node.keywords)
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'setdefault'
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    fields.add(node.args[0].value)
    return fields


def discovered_entry_functions(row):
    """All persisted entries in the machine's discovered field-writer scope.

    This census is independent of DEADLINE_ENTRIES. Builders that return a
    mapping without persisting it remain explicit inplace entry declarations;
    the per-entry stamp probe checks those separately.
    """
    from tests.support.lifecycle_state_table import writers

    actual = set()
    fields = {path.field for path in row.deadline_entries}
    probes = set()
    for writer in writers(row.machine, *fields):
        for prototype in row.deadline_entries:
            bindings = dict(prototype.bindings)
            if prototype.state is not None:
                bindings.setdefault(prototype.field, prototype.state)
            variants = (False, True) if row.machine == 'finalization' else (None,)
            for byok in variants:
                variant = dict(bindings)
                if byok is not None:
                    variant['requires_byok'] = byok
                probe = EntryPath(
                    writer.module, writer.function, prototype.field, prototype.state, tuple(sorted(variant.items()))
                )
                if probe in probes:
                    continue
                probes.add(probe)
                if entry_deadline_sites(module_source(writer.module)[0], probe, row.deadline_field):
                    actual.add((writer.module, writer.function))
    return actual


def assert_patch_contract(entry, deadline):
    for qualified in entry.patches:
        assert qualified in PATCH_CONTRACTS, f'unregistered patch contract: {qualified}'
        contract = PATCH_CONTRACTS[qualified]
        assert entry.field not in contract.keys and deadline not in contract.keys
        assert contract.sources
        writer, _fingerprint = contract.sources[0]
        assert qualified == writer.module.removesuffix('.py').replace('/', '.') + '.' + writer.function
        for writer, fingerprint in contract.sources:
            source = function_source(f'{writer.module}:{writer.function}')
            assert source, writer
            node = ast.parse(source).body[0]
            assert (
                definition_fingerprint(node) == fingerprint
            ), f'{qualified}: returned-key proof changed at {writer.module}:{writer.function}; re-audit contract'


def assert_clause(row, clause):
    if row.derived:
        if row.machine == 'record_token':
            # Per-token views derive from nested clocks, not a persisted phase.
            # Their process-local stock and custody-invariant page do not claim
            # an independent persisted-state deadline or backlog dwell alarm.
            assert row.state in {'capturing', 'lease_lapsed'}
            assert row.fields == ('record_upload_sessions',)
            assert row.deadline_field is None and not row.deadline_stamped_at_entry and not row.deadline_entries
            assert row.deadline_exemption
            assert function_source(row.exit.cite), row.exit.cite
            if clause == 'automatic_exit':
                assert row.exit.kind in {'lease', 'sweeper'}
                for writer in row.exit.automatic_writers:
                    assert function_source(f'{writer.module}:{writer.function}'), writer
                    assert writer.function in FIELD_BUILDERS.get(writer.module, {}).get('record_upload_sessions', ())
            elif clause == 'entry_deadline':
                assert function_source('config/record_seal_rules.py:token_lease_lapsed')
            elif clause == 'dwell_metric':
                assert row.dwell_metric == 'omi_record_token_lease_active' and row.dwell_metric in gauge_names()
            elif clause == 'dwell_alert':
                assert row.alert.uid == 'omi-record-token-lease-late-append' and row.alert.tier == 'page'
                rule = alerts()[row.alert.uid]
                assert rule.get('labels', {}).get('tier') == row.alert.tier and not rule.get('isPaused', False)
                assert any(
                    'omi_record_token_late_append_total' in item.get('model', {}).get('expr', '')
                    for item in rule['data']
                )
            else:
                raise AssertionError(clause)
        else:
            # Compatibility reader vocabulary has no state entry side effect.
            assert row.machine == 'conversation_phase' and row.note.startswith('Read-only')
        return
    if row.quiescent:
        assert (row.machine, row.state) == ('fair_use', 'none')
        return  # Base state carries no outstanding enforcement obligation.
    if clause == 'automatic_exit':
        for writer in row.exit.automatic_writers:
            assert function_source(f'{writer.module}:{writer.function}'), writer
            assert any(
                writer.function in FIELD_BUILDERS.get(writer.module, {}).get(field, ()) for field in row.fields
            ), f'{row.key}: automatic exit writer is outside the reviewed field inventory: {writer}'
        if row.exit_exemption:
            assert row.key == 'record_audio:capturing' and not row.terminal
            assert row.exit.kind == 'callback-only'
            assert row.exit.cite == 'database/record_audio.py:set_record_upload_pending'
            assert row.deadline_exemption and 'exact-token finish' in row.exit_exemption
            assert function_source(row.exit.cite)
            return
        if row.terminal:
            assert (
                row.owner and (BACKEND / row.owner.removeprefix('backend/')).is_file()
            ), 'terminal owner/triage missing'
        else:
            assert row.exit.kind in {'sweeper', 'decay', 'lease'}, row.exit.cite
            module, separator, function = row.exit.cite.partition(':')
            assert separator and function and function_node(module_source(module)[0], function), row.exit.cite
            assert function_source(row.exit.cite), row.exit.cite
    elif clause == 'entry_deadline':
        if not row.terminal:
            if row.deadline_exemption:
                if row.key == 'batch:allowance_held':
                    assert 'SCA-2195' in row.deadline_exemption and 'no recording expiry' in row.deadline_exemption
                    assert row.deadline_field is None and not row.deadline_stamped_at_entry
                    assert row.exit.cite == 'utils/batch_pipeline/allowance_hold.py:AllowanceHolds.tick'
                    return
                assert row.key in {'record_audio:capturing', 'record_audio_orphan:capturing'}
                assert row.fields == ('record_upload_sessions',)
                assert 'No producer TTL' in row.deadline_exemption and '9d457c' in row.deadline_exemption
                assert row.deadline_field is None and not row.deadline_stamped_at_entry and not row.deadline_entries
                return
            assert row.deadline_field and row.deadline_stamped_at_entry, 'deadline is absent or only computed on read'
            assert row.deadline_entries, 'every automatic entry path must be declared'
            declared = {(path.module, path.function) for path in row.deadline_entries}
            missing = discovered_entry_functions(row) - declared
            assert not missing, f'undeclared persisted deadline entry: {sorted(missing)}'
            assert {(path.module, path.function) for path in row.deadline_entries} == {
                (writer.module, writer.function) for writer in row.entered_by
            }
            for entry in row.deadline_entries:
                assert_patch_contract(entry, row.deadline_field)
                sites = entry_deadline_sites(module_source(entry.module)[0], entry, row.deadline_field)
                assert sites, f'{entry.module}:{entry.function}: no matching entry payload'
                assert all(
                    stamped for _line, stamped in sites
                ), f'{entry.module}:{entry.function}: unstamped entry sites {sites}'
    elif clause == 'dwell_metric':
        assert row.dwell_metric in gauge_names(), 'authoritative age/stock Gauge missing (a counter is insufficient)'
    elif clause == 'dwell_alert':
        if not row.alert_required:
            if row.key == 'batch:allowance_held':
                assert row.deadline_exemption and row.dwell_metric == 'omi_batch_allowance_held_units'
                assert not row.terminal  # A held recording still owes an eventual result.
                return
            assert row.terminal and row.state in {'completed', 'committed', 'erased', 'composed', 'redirected'}
            return  # Success stock needs an owner/gauge, not a debt alarm.
        rule = alerts().get(row.alert.uid)
        assert rule, 'no committed dwell/stock rule'
        assert rule.get('labels', {}).get('tier') == row.alert.tier
        expressions = [item.get('model', {}).get('expr', '') for item in rule['data']]
        assert row.dwell_metric and any(
            row.dwell_metric in expr for expr in expressions
        ), 'alert does not query the row metric'
        assert not rule.get('isPaused', False)
    else:
        raise AssertionError(clause)


# KNOWN_GAPS is a reviewed baseline, added below. It is not derived from the
# assertions at collection time; strict XPASS is a blocking improvement signal.
KNOWN_GAPS = {
    ('record_audio:seal_refused', 'automatic_exit'): 'Phase 1 preserves callback-only exact-token finish and seal; '
    'automatic requeue is phase 4; ANX lcphase1-first-refusal-clock',
    ('record_audio:seal_refused', 'entry_deadline'): 'First-refusal clock is an age anchor, not a custody deadline; '
    'phase 4 owns requeue; ANX lcphase1-first-refusal-clock',
    ('record_audio:seal_refused', 'dwell_metric'): 'Phase 1 emits bounded job-page age/count in the sweeper summary; '
    'authoritative fleet Gauge including no-job rows remains outside scope; ANX lcphase1-first-refusal-clock',
    ('record_audio:seal_refused', 'dwell_alert'): 'Phase 1 declares the agent alert identity; committed monitoring '
    'rule is outside named file scope; ANX lcphase1-first-refusal-clock',
    ('visibility:transcribing_hold', 'dwell_metric'): 'No dedicated transcription presentation dwell gauge; '
    'homegate phase 1; ANX lcinv-lifecycle-invariants',
    ('visibility:transcribing_hold', 'dwell_alert'): 'No dedicated transcription presentation stock alert; '
    'homegate phase 1; ANX lcinv-lifecycle-invariants',
    ('batch:committed', 'dwell_metric'): 'batch:committed: missing authoritative dwell/stock gauge; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:partial_retired', 'dwell_alert'): 'batch:partial_retired: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:partial_retired', 'dwell_metric'): 'batch:partial_retired: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch:privacy_blocked', 'dwell_alert'): 'batch:privacy_blocked: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:privacy_blocked', 'dwell_metric'): 'batch:privacy_blocked: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    (
        'batch:quarantined',
        'entry_deadline',
    ): 'GPU holds stamp a flag-gated held_deadline_at; provider-STT settle/terminal entries '
    'remain unstamped and cannot join the GPU requeue path. ANX omi-lifecycle phase 4a',
    ('batch:ready', 'entry_deadline'): 'batch:ready: missing deadline stamped at entry; phase contract follow-up; no '
    'fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:record_pending', 'entry_deadline'): 'batch:record_pending: total pending-dwell deadline is still '
    'unstamped after #24587 admission lease; phase contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:result_ready', 'entry_deadline'): 'batch:result_ready: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:retry', 'entry_deadline'): 'batch:retry: missing deadline stamped at entry; phase contract follow-up; no '
    'fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:vendor_held', 'entry_deadline'): 'batch:vendor_held: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch_projection:completed', 'dwell_metric'): 'batch_projection:completed: missing authoritative dwell/stock '
    'gauge; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:erased', 'dwell_metric'): 'batch_projection:erased: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:pending', 'entry_deadline'): 'batch_projection:pending: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:persisted', 'entry_deadline'): 'batch_projection:persisted: missing deadline stamped at '
    'entry; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:quarantine_held', 'entry_deadline'): 'Assignment holds stamp held_deadline_at; privacy holds '
    'remain explicitly outside phase 4b and must never age-expire. ANX lcinv-lifecycle-invariants',
    ('batch_projection:ready', 'entry_deadline'): 'batch_projection:ready: missing deadline stamped at entry; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:completed', 'dwell_metric'): 'conversation:completed: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('conversation:failed', 'dwell_alert'): 'conversation:failed: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:failed', 'dwell_metric'): 'conversation:failed: missing authoritative dwell/stock gauge; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:in_progress', 'dwell_alert'): 'conversation:in_progress: missing committed dwell/stock alert; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('conversation:in_progress', 'dwell_metric'): 'conversation:in_progress: missing authoritative dwell/stock '
    'gauge; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('conversation:in_progress', 'entry_deadline'): 'conversation:in_progress: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('conversation:merging', 'dwell_alert'): 'conversation:merging: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:merging', 'dwell_metric'): 'conversation:merging: missing authoritative dwell/stock gauge; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:merging', 'entry_deadline'): 'conversation:merging: missing deadline stamped at entry; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:processing', 'entry_deadline'): 'conversation:processing: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('episode:closed', 'automatic_exit'): 'episode:closed: missing independent automatic exit; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closed', 'dwell_alert'): 'episode:closed: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closed', 'dwell_metric'): 'episode:closed: missing authoritative dwell/stock gauge; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closed', 'entry_deadline'): 'episode:closed: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closing', 'automatic_exit'): 'episode:closing: missing independent automatic exit; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closing', 'dwell_alert'): 'episode:closing: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closing', 'dwell_metric'): 'episode:closing: missing authoritative dwell/stock gauge; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:closing', 'entry_deadline'): 'episode:closing: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:composed', 'dwell_metric'): 'episode:composed: missing authoritative dwell/stock gauge; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:live', 'automatic_exit'): 'episode:live: missing independent automatic exit; phase contract follow-up; '
    'no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:live', 'dwell_alert'): 'episode:live: missing committed dwell/stock alert; phase contract follow-up; '
    'no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:live', 'dwell_metric'): 'episode:live: missing authoritative dwell/stock gauge; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:live', 'entry_deadline'): 'episode:live: missing deadline stamped at entry; phase contract follow-up; '
    'no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:redirected', 'dwell_metric'): 'episode:redirected: missing authoritative dwell/stock gauge; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:restrict', 'dwell_alert'): 'fair_use:restrict: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:throttle', 'dwell_alert'): 'fair_use:throttle: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:warning', 'dwell_alert'): 'fair_use:warning: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('finalization:blocked_byok', 'entry_deadline'): 'finalization:blocked_byok: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('finalization:completed', 'dwell_metric'): 'finalization:completed: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('record_audio:capturing', 'dwell_alert'): 'Live producer custody needs a dwell alert despite no TTL; 4bf62d; '
    'capture monitoring follow-up, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:capturing', 'dwell_metric'): 'Live producer custody needs authoritative dwell visibility; 4bf62d; '
    'capture monitoring follow-up, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:abandoned', 'entry_deadline'): 'PR #24689 adds a conditional eviction exit, not a bounded '
    'repair deadline: abandoned_at records stopped-producer age; executor settlement, metadata admission retry '
    'and retained-tail durability can wait indefinitely; ANX lcinv-lifecycle-invariants',
    ('record_audio:abandoned', 'dwell_metric'): 'PR #24689 logs outcome=abandoned but supplies no authoritative '
    'abandoned-token age/stock gauge; ANX lcinv-lifecycle-invariants',
    ('record_audio:abandoned', 'dwell_alert'): 'PR #24689 supplies no abandoned-token dwell alert; '
    'ANX lcinv-lifecycle-invariants',
    (
        'record_audio_orphan:capturing',
        'dwell_metric',
    ): 'Proven-dead orphan recovery needs an authoritative dwell gauge; '
    '4bf62d; capture monitoring follow-up, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio_orphan:capturing', 'dwell_alert'): 'Proven-dead orphan recovery needs a dwell alert; 4bf62d; '
    'capture monitoring follow-up, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_audio_partial', 'dwell_alert'): 'record_audio:record_audio_partial: missing committed '
    'dwell/stock alert; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_audio_partial', 'dwell_metric'): 'record_audio:record_audio_partial: missing authoritative '
    'dwell/stock gauge; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_audio_partial', 'entry_deadline'): 'record_audio:record_audio_partial: missing deadline '
    'stamped at entry; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'dwell_alert'): 'record_audio:record_upload_failed: missing committed '
    'dwell/stock alert; Worker proof repair can clear the bit; '
    'reconnect-only retry remains a freshtitles fix, no PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'dwell_metric'): 'record_audio:record_upload_failed: missing authoritative '
    'dwell/stock gauge; Worker proof repair can clear the '
    'bit; reconnect-only retry remains a freshtitles fix, no '
    'PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'entry_deadline'): 'record_audio:record_upload_failed: missing deadline '
    'stamped at entry; Worker proof repair can clear the '
    'bit; reconnect-only retry remains a freshtitles fix, '
    'no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:sealed', 'automatic_exit'): 'record_audio:sealed: missing independent automatic exit; No job: '
    'manual digest-gated nojob recovery is not an automatic exit; '
    'freshtitles fix, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:sealed', 'entry_deadline'): 'record_audio:sealed: missing deadline stamped at entry; No job: '
    'manual digest-gated nojob recovery is not an automatic exit; '
    'freshtitles fix, no PR yet; ANX lcinv-lifecycle-invariants',
    ('summary_debt:completed', 'dwell_metric'): 'summary_debt:completed: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('summary_debt:pending', 'dwell_alert'): 'summary_debt:pending: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('visibility:bridge_pending', 'dwell_alert'): 'visibility:bridge_pending: missing committed dwell/stock alert; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('visibility:bridge_pending', 'dwell_metric'): 'visibility:bridge_pending: missing authoritative dwell/stock '
    'gauge; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('visibility:settling_hold', 'dwell_alert'): 'visibility:settling_hold: missing committed dwell/stock alert; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('visibility:settling_hold', 'dwell_metric'): 'visibility:settling_hold: missing authoritative dwell/stock '
    'gauge; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('visibility:settling_hold', 'entry_deadline'): 'visibility:settling_hold: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
}


# Ruling699300 reviewed the coverage loss explicitly. Never derive these gaps
# from isPaused or from assertion failures: only the fixed reviewed table may enter.
# Real unpause makes test_latch_clause XPASS strictly, forcing debt cleanup.
KNOWN_GAPS.update(
    {
        (key, 'dwell_alert'): (
            f'Lead2 ruling699300 (2026-11-08T15:13Z), PR #24938: {uid} paused for known '
            'backlog until #24731/#24893 ships and its written clean24h unpause criteria hold; '
            'active dwell protection is absent, not repaired. Owner: omi-pipeline/two-lane-lead.'
        )
        for key, uid in IMPORT_PAUSED_DWELL_ROWS.items()
    }
)


def parameters():
    for row in STATES:
        for clause in CLAUSES:
            reason = KNOWN_GAPS.get((row.key, clause))
            marks = [pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)] if reason else []
            yield pytest.param(row, clause, id=f'{row.key}/{clause}', marks=marks)


@pytest.mark.parametrize('row,clause', list(parameters()))
def test_latch_clause(row, clause):
    assert_clause(row, clause)


@pytest.mark.parametrize('clause', CLAUSES)
def test_derived_record_token_view_rejects_unknown_states_and_fields(clause):
    view = next(row for row in STATES if row.key == 'record_token:capturing')
    for changed in (replace(view, state='invented'), replace(view, fields=('status',))):
        with pytest.raises(AssertionError):
            assert_clause(changed, clause)


def test_declared_phase_vocabulary_matches_compatibility_reader():
    assert {row.state for row in STATES if row.machine == 'conversation_phase'} == {
        phase.value for phase in ConversationPhase
    }
    assert {row.state for row in STATES if row.machine == 'episode'} == {phase.value for phase in EpisodePhase}


def test_complete_and_unique_four_clause_matrix():
    assert len({row.key for row in STATES}) == len(STATES)
    assert len(list(parameters())) == 4 * len(STATES)
    assert set(KNOWN_GAPS) <= {(row.key, clause) for row in STATES for clause in CLAUSES}


def test_required_legacy_machines_are_present():
    required = {
        'conversation': {'in_progress', 'processing', 'merging', 'completed', 'failed'},
        'finalization': {'queued', 'leased', 'blocked_byok', 'dead_letter', 'completed'},
        'batch': {
            'record_pending',
            'ready',
            'leased',
            'retry',
            'result_ready',
            'vendor_held',
            'privacy_blocked',
            'partial_retired',
        },
        'batch_projection': {'pending', 'persisted', 'ready', 'quarantine_held', 'completed', 'erased'},
        'record_audio': {
            'capturing',
            'seal_refused',
            'abandoned',
            'sealed',
            'record_upload_failed',
            'record_audio_partial',
        },
        'summary_debt': {'pending', 'completed'},
        'fair_use': {'warning', 'throttle', 'restrict'},
        'visibility': {'bridge_pending', 'settling_hold', 'transcribing_hold'},
    }
    for machine, states in required.items():
        assert states <= {row.state for row in STATES if row.machine == machine}


def test_resolved_plan_gaps_do_not_regress():
    rows = {row.key: row for row in STATES}
    for key, clause in (
        ('fair_use:throttle', 'automatic_exit'),
        ('finalization:blocked_byok', 'dwell_alert'),
        ('finalization:blocked_byok', 'dwell_metric'),
        ('batch:record_pending', 'dwell_metric'),
        # record_pending dwell-alert coverage is now explicit reviewed import debt.
        ('finalization:dead_letter', 'dwell_alert'),
        ('batch:leased', 'entry_deadline'),
        ('visibility:bridge_pending', 'entry_deadline'),
        ('visibility:transcribing_hold', 'entry_deadline'),
        ('visibility:transcribing_hold', 'automatic_exit'),
    ):
        assert (key, clause) not in KNOWN_GAPS
        assert_clause(rows[key], clause)


@pytest.mark.parametrize('key,uid', IMPORT_PAUSED_DWELL_ROWS.items())
def test_reviewed_import_pauses_remain_real_dwell_coverage_gaps(key, uid):
    row = next(row for row in STATES if row.key == key)
    assert row.alert.uid == uid
    assert (key, 'dwell_alert') in KNOWN_GAPS
    rule = alerts()[uid]
    assert rule['isPaused'] is True
    assert '24h' in rule['annotations']['unpause_criteria']
    with pytest.raises(AssertionError):
        assert_clause(row, 'dwell_alert')


@pytest.mark.parametrize('key,uid', IMPORT_PAUSED_DWELL_ROWS.items())
def test_real_unpause_will_require_removing_the_strict_gap(key, uid, monkeypatch):
    row = next(row for row in STATES if row.key == key)
    monkeypatch.setitem(alerts(), uid, {**alerts()[uid], 'isPaused': False})
    assert_clause(row, 'dwell_alert')  # Real source unpause would make the strict xfail XPASS.


def test_unreviewed_pause_still_fails_the_active_dwell_contract(monkeypatch):
    row = next(row for row in STATES if row.key == 'finalization:queued')
    assert row.key not in IMPORT_PAUSED_DWELL_ROWS
    monkeypatch.setitem(alerts(), row.alert.uid, {**alerts()[row.alert.uid], 'isPaused': True})
    with pytest.raises(AssertionError):
        assert_clause(row, 'dwell_alert')


@pytest.mark.parametrize('key', ['record_audio:capturing', 'record_audio_orphan:capturing'])
def test_no_ttl_custody_keeps_exit_and_monitoring_obligations_separate(key):
    row = next(row for row in STATES if row.key == key)
    assert_clause(row, 'entry_deadline')
    assert_clause(row, 'automatic_exit')
    for clause in ('dwell_metric', 'dwell_alert'):
        assert (key, clause) in KNOWN_GAPS
        with pytest.raises(AssertionError):
            assert_clause(row, clause)


def test_automatic_state_cannot_borrow_interactive_capture_exemptions():
    custody = next(row for row in STATES if row.key == 'record_audio:capturing')
    leased = next(row for row in STATES if row.key == 'batch:leased')
    with pytest.raises(AssertionError):
        assert_clause(replace(leased, deadline_exemption=custody.deadline_exemption), 'entry_deadline')
    with pytest.raises(AssertionError):
        assert_clause(replace(leased, exit_exemption=custody.exit_exemption), 'automatic_exit')


def test_deadline_probe_rejects_a_read_without_an_entry_write():
    assert 'deadline_at' not in assigned_fields("def read(row):\n    return row.get('deadline_at')\n")
    assert 'deadline_at' in assigned_fields("def enter(row):\n    row['deadline_at'] = now + 600\n")


@pytest.mark.parametrize(
    'source',
    [
        "def enter(tx, ref):\n    tx.update(ref, {'status': 'queued', 'deadline_at': now + 10})\n    tx.update(ref, {'status': 'queued'})\n",
        "def enter(tx, ref, alternative):\n    if alternative:\n        updates = {'status': 'queued', 'deadline_at': now + 10}\n    else:\n        updates = {'status': 'queued'}\n    tx.update(ref, updates)\n",
    ],
)
def test_one_stamped_path_cannot_mask_another_unstamped_entry(source):
    sites = entry_deadline_sites(source, EntryPath('synthetic.py', 'enter', 'status', 'queued'), 'deadline_at')
    assert len(sites) == 2
    assert {stamped for _line, stamped in sites} == {True, False}


@pytest.mark.parametrize(
    'source',
    [
        "def enter(tx, ref):\n    job = {'status': 'queued'}\n    unrelated = {'deadline_at': now + 10}\n    tx.update(ref, job)\n",
        "def enter(tx, ref, optional):\n    job = {'status': 'queued'}\n    if optional:\n        job['deadline_at'] = now + 10\n    tx.update(ref, job)\n",
        "def enter(tx, ref):\n    job = {'status': 'queued'}\n    tx.update(ref, job)\n    job['deadline_at'] = now + 10\n",
        "def enter(tx, ref):\n    tx.update(ref, {'status': 'queued', 'deadline_at': None})\n",
        "def enter(tx, ref):\n    deadline = None\n    tx.update(ref, {'status': 'queued', 'deadline_at': deadline})\n",
        "def enter(tx, ref):\n    job = {'status': 'queued', 'deadline_at': now + 10}\n    job['deadline_at'] = None\n    tx.update(ref, job)\n",
        "def enter(tx, ref):\n    job = {'status': 'queued', 'deadline_at': now + 10}\n    job.pop('deadline_at')\n    tx.update(ref, job)\n",
        "def enter(tx, ref):\n    job = {'status': 'queued', 'deadline_at': now + 10}\n    del job['deadline_at']\n    tx.update(ref, job)\n",
        "def enter(tx, ref, optional):\n    job = {'status': 'queued', 'deadline_at': now + 10}\n    if optional:\n        job['deadline_at'] = None\n    tx.update(ref, job)\n",
    ],
)
def test_unrelated_conditional_late_or_null_stamps_do_not_prove_entry_deadline(source):
    sites = entry_deadline_sites(source, EntryPath('synthetic.py', 'enter', 'status', 'queued'), 'deadline_at')
    assert sites and all(not stamped for _line, stamped in sites)


def test_conditional_entry_stamp_needs_a_proven_binding():
    source = "def enter(tx, ref, byok):\n    job = {'status': 'queued'}\n    if not byok:\n        job['deadline_at'] = now + 10\n    tx.update(ref, job)\n"
    path = EntryPath('synthetic.py', 'enter', 'status', 'queued', (('byok', False),))
    assert all(stamped for _line, stamped in entry_deadline_sites(source, path, 'deadline_at'))
    unproven = EntryPath('synthetic.py', 'enter', 'status', 'queued')
    assert any(not stamped for _line, stamped in entry_deadline_sites(source, unproven, 'deadline_at'))


def test_r2_cleared_alias_payload_has_no_entry_deadline():
    source = (
        "def enter(tx, ref, queued_payload):\n"
        "    job = {'status': 'queued', 'deadline_at': now + 10}\n"
        "    job.clear()\n"
        "    job.update(queued_payload)\n"
        "    tx.update(ref, job)\n"
    )
    sites = entry_deadline_sites(source, EntryPath('synthetic.py', 'enter', 'status', 'queued'), 'deadline_at')
    assert sites and all(not stamped for _line, stamped in sites)


@pytest.mark.parametrize('patch', ["{'deadline_at': None}", 'opaque_patch'])
def test_r2_alias_patch_cannot_silently_erase_an_entry_deadline(patch):
    source = (
        "def enter(tx, ref, opaque_patch):\n"
        "    job = {'status': 'queued', 'deadline_at': now + 10}\n"
        f"    patch = {patch}\n"
        "    job.update(patch)\n"
        "    tx.update(ref, job)\n"
    )
    sites = entry_deadline_sites(source, EntryPath('synthetic.py', 'enter', 'status', 'queued'), 'deadline_at')
    assert sites and all(not stamped for _line, stamped in sites)


def test_r2_clear_then_alias_rebuild_with_a_fresh_deadline_is_valid():
    source = (
        "def enter(tx, ref):\n"
        "    job = {'status': 'queued', 'deadline_at': now + 10}\n"
        "    job.clear()\n"
        "    replacement = {'status': 'queued', 'deadline_at': now + 20}\n"
        "    job.update(replacement)\n"
        "    tx.update(ref, job)\n"
    )
    sites = entry_deadline_sites(source, EntryPath('synthetic.py', 'enter', 'status', 'queued'), 'deadline_at')
    assert sites and all(stamped for _line, stamped in sites)


def test_r2_source_alias_mutation_cannot_restore_a_stale_deadline():
    source = (
        "def enter(tx, ref):\n"
        "    job = {'status': 'queued', 'deadline_at': now + 10}\n"
        "    replacement = {'status': 'queued', 'deadline_at': now + 20}\n"
        "    replacement.clear()\n"
        "    replacement.update({'status': 'queued'})\n"
        "    job.clear()\n"
        "    job.update(replacement)\n"
        "    tx.update(ref, job)\n"
    )
    sites = entry_deadline_sites(source, EntryPath('synthetic.py', 'enter', 'status', 'queued'), 'deadline_at')
    assert sites and all(not stamped for _line, stamped in sites)


def test_r2_shadowed_patch_name_cannot_borrow_a_contract():
    source = (
        "from utils.conversations.recorded_time import write_span\n"
        "def enter(tx, ref):\n"
        "    job = {'status': 'queued', 'deadline_at': now + 10}\n"
        "    write_span = lambda row: {'deadline_at': None}\n"
        "    job.update(write_span(job))\n"
        "    tx.update(ref, job)\n"
    )
    path = EntryPath(
        'synthetic.py', 'enter', 'status', 'queued', patches=('utils.conversations.recorded_time.write_span',)
    )
    sites = entry_deadline_sites(source, path, 'deadline_at')
    assert sites and all(not stamped for _line, stamped in sites)


def test_r2_patch_contract_cannot_write_the_entry_field(monkeypatch):
    from dataclasses import replace

    row = next(row for row in STATES if row.key == 'visibility:bridge_pending')
    entry = row.deadline_entries[0]
    name = entry.patches[0]
    contract = PATCH_CONTRACTS[name]
    monkeypatch.setitem(PATCH_CONTRACTS, name, replace(contract, keys=(*contract.keys, entry.field)))
    with pytest.raises(AssertionError):
        assert_patch_contract(entry, row.deadline_field)


def test_r2_patch_contract_requires_a_new_audit_after_source_change(monkeypatch):
    row = next(row for row in STATES if row.key == 'visibility:bridge_pending')
    original_source = function_source
    monkeypatch.setitem(
        assert_patch_contract.__globals__,
        'function_source',
        lambda cite: (
            "def write_span(row):\n    return {'sync_bridge_pending': None}\n"
            if cite == 'utils/conversations/recorded_time.py:write_span'
            else original_source(cite)
        ),
    )
    with pytest.raises(AssertionError, match='returned-key proof changed'):
        assert_patch_contract(row.deadline_entries[0], row.deadline_field)


def test_r2_definition_fingerprint_is_portable_but_retains_real_generic_parameters():
    node = ast.parse('def stable():\n    return None\n').body[0]
    baseline = definition_fingerprint(node)
    if 'type_params' not in node._fields:
        node._fields = (*node._fields, 'type_params')
    node.type_params = []
    assert definition_fingerprint(node) == baseline
    node.type_params = [ast.Name(id='T', ctx=ast.Load())]
    assert definition_fingerprint(node) != baseline


def test_r2_clearing_debt_is_an_exit_not_an_unstamped_entry():
    source = "def complete(tx, ref):\n    tx.update(ref, {'summary_first_pending_at': None, 'summary_due_at': None})\n"
    path = EntryPath('synthetic.py', 'complete', 'summary_first_pending_at')
    assert entry_deadline_sites(source, path, 'summary_due_at') == []


@pytest.mark.parametrize('row', [row for row in STATES if row.deadline_entries], ids=lambda row: row.key)
def test_r2_new_persisted_entry_requires_a_declaration_after_inventory_refresh(row, monkeypatch):
    from tests.support.lifecycle_state_table import FIELD_BUILDERS

    prototype = row.deadline_entries[0]
    original_source = module_source
    entered_value = prototype.state if prototype.state is not None else 1
    source = original_source(prototype.module)[0] + (
        f"\ndef undeclared_entry(tx, ref):\n    tx.update(ref, {{{prototype.field!r}: {entered_value!r}}})\n"
    )
    replacement = (source, ast.parse(source))
    monkeypatch.setitem(
        assert_clause.__globals__,
        'module_source',
        lambda module: replacement if module == prototype.module else original_source(module),
    )
    refreshed = dict(FIELD_BUILDERS[prototype.module])
    refreshed[prototype.field] = sorted(set(refreshed[prototype.field]) | {'undeclared_entry'})
    monkeypatch.setitem(FIELD_BUILDERS, prototype.module, refreshed)
    with pytest.raises(AssertionError, match='undeclared.*entry'):
        assert_clause(row, 'entry_deadline')


def test_r2_declared_and_stamped_new_batch_entry_is_valid(monkeypatch):
    from dataclasses import replace
    from tests.support.lifecycle_state_table import FIELD_BUILDERS, Writer

    row = next(row for row in STATES if row.key == 'batch:leased')
    module = row.deadline_entries[0].module
    original_source = module_source
    source = original_source(module)[0] + (
        f"\ndef declared_entry(tx, ref):\n    tx.update(ref, {{'state': 'leased', {row.deadline_field!r}: now + 60}})\n"
    )
    replacement = (source, ast.parse(source))
    monkeypatch.setitem(
        assert_clause.__globals__,
        'module_source',
        lambda path: replacement if path == module else original_source(path),
    )
    refreshed = dict(FIELD_BUILDERS[module])
    refreshed['state'] = sorted(set(refreshed['state']) | {'declared_entry'})
    monkeypatch.setitem(FIELD_BUILDERS, module, refreshed)
    row = replace(
        row,
        entered_by=(*row.entered_by, Writer(module, 'declared_entry')),
        deadline_entries=(*row.deadline_entries, EntryPath(module, 'declared_entry', 'state', 'leased')),
    )
    assert_clause(row, 'entry_deadline')


def test_each_entry_function_is_checked_independently():
    source = "def first(tx, ref):\n    tx.update(ref, {'status': 'queued', 'deadline_at': now + 10})\ndef second(tx, ref):\n    tx.update(ref, {'status': 'queued'})\n"
    first = EntryPath('synthetic.py', 'first', 'status', 'queued')
    second = EntryPath('synthetic.py', 'second', 'status', 'queued')
    assert all(stamped for _line, stamped in entry_deadline_sites(source, first, 'deadline_at'))
    assert any(not stamped for _line, stamped in entry_deadline_sites(source, second, 'deadline_at'))


def test_terminal_success_alert_exemption_cannot_hide_debt():
    from dataclasses import replace

    row = next(row for row in STATES if row.key == 'finalization:blocked_byok')
    with pytest.raises(AssertionError):
        assert_clause(replace(row, alert_required=False), 'dwell_alert')


def test_automatic_upload_failure_repair_is_a_green_source_control():
    row = next(row for row in STATES if row.key == 'record_audio:record_upload_failed')
    assert_clause(row, 'automatic_exit')
    repair = function_source('utils/batch_pipeline/record_seal_cluster_repair.py:repair_one')
    assert 'repair_upload_failed=True' in repair


def test_capacity_abandonment_declares_conditional_exit_and_honest_repair_gaps():
    rows = {row.key: row for row in STATES}
    live, abandoned = rows['record_audio:capturing'], rows['record_audio:abandoned']
    assert live.exit.automatic_writers == (ABANDON_RECORD_PRODUCER,)
    assert abandoned.entered_by == (ABANDON_RECORD_PRODUCER,)
    assert abandoned.fields == ('record_upload_sessions',)
    assert_clause(live, 'automatic_exit')
    assert_clause(abandoned, 'automatic_exit')
    assert not abandoned.terminal and not abandoned.derived and not abandoned.deadline_exemption
    assert abandoned.deadline_field is None and not abandoned.deadline_stamped_at_entry
    assert abandoned.dwell_metric is None and abandoned.alert.uid is None
    assert {clause for key, clause in KNOWN_GAPS if key == abandoned.key} == {
        'entry_deadline',
        'dwell_metric',
        'dwell_alert',
    }


@pytest.mark.parametrize('state,deadline', [('queued', 'reconcile_after_at'), ('leased', 'lease_expires_at')])
def test_every_persisted_finalization_entry_function_is_declared(state, deadline):
    from tests.support.lifecycle_state_table import FIELD_BUILDERS

    module = 'database/conversation_finalization_jobs.py'
    source = module_source(module)[0]
    actual = set()
    for owner in FIELD_BUILDERS[module]['status']:
        path = EntryPath(module, owner, 'status', state, (('status', state), ('requires_byok', False)))
        if entry_deadline_sites(source, path, deadline):
            actual.add(owner)
    row = next(row for row in STATES if row.key == f'finalization:{state}')
    assert actual == {path.function for path in row.deadline_entries}


def warning_renewal_modules():
    return [
        path
        for directory in ('database', 'utils')
        for path in (BACKEND / directory).rglob('*.py')
        if 'renew_fair_use_warning' in path.read_text()
    ]


@pytest.mark.parametrize('path', warning_renewal_modules(), ids=lambda path: path.relative_to(BACKEND).as_posix())
def test_warning_reentry_callers_supply_the_deadline(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'renew_fair_use_warning'
        ):
            assert len(node.args) >= 2 and isinstance(node.args[1], ast.Dict)
            supplied = {
                key.value: item
                for key, item in zip(node.args[1].keys, node.args[1].values)
                if isinstance(key, ast.Constant)
            }
            assert 'warning_until' in supplied
            assert (
                not isinstance(supplied['warning_until'], ast.Constant) or supplied['warning_until'].value is not None
            )


ORDERING_COUNTEREXAMPLES = {
    'late_result_commit_rearms_titling': {
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'finalization_status': 'completed',
        'record_audio_closed': True,
    },
    'completed_capture_has_closed_audio': {
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'finalization_status': 'completed',
        'record_audio_closed': False,
        'record_upload_sessions': {'synthetic-producer': True},
    },
}


@pytest.mark.parametrize(
    'rule',
    [
        pytest.param(
            rule,
            id=rule.name,
            marks=pytest.mark.xfail(
                strict=True,
                raises=AssertionError,
                reason=f'{rule.waits_on}; synthetic counterexample; ANX lcinv-lifecycle-invariants',
            ),
        )
        for rule in ORDERING_RULES
        if rule.name != 'late_result_commit_rearms_titling'
    ],
)
def test_known_red_cross_store_ordering_clause(rule):
    # Minimal synthetic views encode only the failure class, never owner data.
    # This B1 pure assertion is not a reproduced write-path or simulator claim.
    assert ordering_holds(rule, ORDERING_COUNTEREXAMPLES[rule.name])


@pytest.mark.parametrize('early,results,rearm', [(False, 1, False), (True, 0, False), (True, 1, True)])
def test_ordering_accepts_normal_completion_and_rearmed_late_results(early, results, rearm):
    row = {'record_lane_owner': 'batch_live_v1', 'finalization_status': 'completed'}
    assert ordering_holds(
        ORDERING_RULES[0], row, batch_result_count=results, rearm_on_result_commit=rearm, completed_before_results=early
    )


@pytest.mark.parametrize('results,rearm,expected', [(0, False, True), (1, False, False), (1, True, True)])
def test_early_completion_is_checked_at_late_result_commit(results, rearm, expected):
    # A missing rearm after arrival is a negative predicate control, not a
    # claimed runtime bug. B2 proves main actually persists the outbox rearm.
    row = ORDERING_COUNTEREXAMPLES['late_result_commit_rearms_titling']
    assert (
        ordering_holds(
            ORDERING_RULES[0],
            row,
            batch_result_count=results,
            rearm_on_result_commit=rearm,
            completed_before_results=True,
        )
        is expected
    )


def test_queued_finalization_can_wait_for_results():
    assert ordering_holds(ORDERING_RULES[0], {'record_lane_owner': 'batch_live_v1', 'finalization_status': 'queued'})


def test_completed_capture_ordering_has_a_green_closed_control():
    row = {
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'record_audio_closed': True,
        'record_upload_sessions': {},
    }
    assert ordering_holds(ORDERING_RULES[1], row)
    assert not ordering_holds(ORDERING_RULES[1], {**row, 'record_audio_partial': {'version': 1}})


def test_record_ordering_does_not_impose_batch_protocol_on_other_lanes():
    for rule in ORDERING_RULES:
        assert ordering_holds(rule, {'status': 'completed', 'finalization_status': 'completed'})


def test_ordering_rule_sources_exist():
    for rule in ORDERING_RULES:
        assert rule.fields and rule.waits_on
        for writer in rule.source:
            assert function_source(f'{writer.module}:{writer.function}')
