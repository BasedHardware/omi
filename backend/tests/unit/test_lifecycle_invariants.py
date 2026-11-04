"""Pure source/table contracts. Runtime reachability belongs to WP-B2.

Expected failures are enumerated independently in KNOWN_GAPS: never mark a
failure expected simply because an assertion failed. Each parameter receives
one strict xfail for exactly one broken clause. Fixes must update the reviewed
table; a removed gap that still fails, or an improved row left xfailed, fails CI.
"""

import ast
import json
from functools import lru_cache
from pathlib import Path

import pytest

from tests.support.lifecycle_state_table import CLAUSES, STATES
from utils.conversations.phase import ConversationPhase, EpisodePhase

BACKEND = Path(__file__).resolve().parents[2]
METRIC_MODULES = (
    'utils/metrics.py',
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


@lru_cache(maxsize=1)
def gauge_names():
    result = set()
    for module in METRIC_MODULES:
        tree = ast.parse((BACKEND / module).read_text())
        result.update(phase_metric_gauge_names(tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Gauge' and node.args:
                if isinstance(node.args[0], ast.Constant):
                    result.add(node.args[0].value)
    return result


def test_phase_metric_inventory_requires_declared_prefix_and_gauge_suffix():
    tree = ast.parse("PhaseMetrics('declared', []); Counter('made_up_prefix', [])")
    names = phase_metric_gauge_names(tree)
    assert 'declared_new_oldest_age_seconds' in names
    assert 'made_up_prefix_new_oldest_age_seconds' not in names
    assert 'declared_made_up_suffix' not in names


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


@lru_cache(maxsize=None)
def function_source(cite):
    module, _, function = cite.partition(':')
    source, node = module_source(module)
    if not function:
        return source
    for part in function.split('.'):
        node = next(
            (
                child
                for child in node.body
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == part
            ),
            None,
        )
        if node is None:
            return ''
    return ast.get_source_segment(source, node) or ''


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


def assert_clause(row, clause):
    if row.derived:
        # Compatibility reader vocabulary has no state entry side effect.
        assert row.machine == 'conversation_phase' and row.note.startswith('Read-only')
        return
    if clause == 'automatic_exit':
        if row.terminal:
            assert (
                row.owner and (BACKEND / row.owner.removeprefix('backend/')).is_file()
            ), 'terminal owner/triage missing'
        else:
            assert row.exit.kind in {'sweeper', 'decay', 'lease'}, row.exit.cite
            assert function_source(row.exit.cite), row.exit.cite
    elif clause == 'entry_deadline':
        if not row.terminal:
            assert row.deadline_field and row.deadline_stamped_at_entry, 'deadline is absent or only computed on read'
            # Validate a stamped field against source payload builders, rather
            # than accepting a plausible but misspelled field declaration.
            sources = [function_source(f'{writer.module}:{writer.function}') for writer in row.entered_by]
            assert any(row.deadline_field in assigned_fields(source) for source in sources), row.deadline_field
    elif clause == 'dwell_metric':
        assert row.dwell_metric in gauge_names(), 'authoritative age/stock Gauge missing (a counter is insufficient)'
    elif clause == 'dwell_alert':
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
    ('batch:committed', 'dwell_alert'): 'batch:committed: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
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
    ('batch:quarantined', 'entry_deadline'): 'batch:quarantined: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:ready', 'entry_deadline'): 'batch:ready: missing deadline stamped at entry; phase contract follow-up; no '
    'fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:record_pending', 'dwell_alert'): 'batch:record_pending: missing committed dwell/stock alert; PR #24587 '
    'addresses drain contention; available_at is a defer, not an admission '
    'budget; ANX lcinv-lifecycle-invariants',
    ('batch:record_pending', 'dwell_metric'): 'batch:record_pending: missing authoritative dwell/stock gauge; PR '
    '#24587 addresses drain contention; available_at is a defer, not an '
    'admission budget; ANX lcinv-lifecycle-invariants',
    ('batch:record_pending', 'entry_deadline'): 'batch:record_pending: missing deadline stamped at entry; PR #24587 '
    'addresses drain contention; available_at is a defer, not an '
    'admission budget; ANX lcinv-lifecycle-invariants',
    ('batch:result_ready', 'entry_deadline'): 'batch:result_ready: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:retry', 'entry_deadline'): 'batch:retry: missing deadline stamped at entry; phase contract follow-up; no '
    'fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch:vendor_held', 'entry_deadline'): 'batch:vendor_held: missing deadline stamped at entry; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch_projection:completed', 'dwell_alert'): 'batch_projection:completed: missing committed dwell/stock alert; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:completed', 'dwell_metric'): 'batch_projection:completed: missing authoritative dwell/stock '
    'gauge; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:erased', 'dwell_alert'): 'batch_projection:erased: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('batch_projection:erased', 'dwell_metric'): 'batch_projection:erased: missing authoritative dwell/stock gauge; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:pending', 'entry_deadline'): 'batch_projection:pending: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:persisted', 'entry_deadline'): 'batch_projection:persisted: missing deadline stamped at '
    'entry; phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('batch_projection:quarantine_held', 'entry_deadline'): 'batch_projection:quarantine_held: missing deadline '
    'stamped at entry; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('batch_projection:ready', 'entry_deadline'): 'batch_projection:ready: missing deadline stamped at entry; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('conversation:completed', 'dwell_alert'): 'conversation:completed: missing committed dwell/stock alert; phase '
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
    ('episode:composed', 'dwell_alert'): 'episode:composed: missing committed dwell/stock alert; phase contract '
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
    ('episode:redirected', 'dwell_alert'): 'episode:redirected: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('episode:redirected', 'dwell_metric'): 'episode:redirected: missing authoritative dwell/stock gauge; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:none', 'dwell_alert'): 'fair_use:none: missing committed dwell/stock alert; phase contract follow-up; '
    'no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:none', 'dwell_metric'): 'fair_use:none: missing authoritative dwell/stock gauge; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:restrict', 'dwell_alert'): 'fair_use:restrict: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:throttle', 'dwell_alert'): 'fair_use:throttle: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('fair_use:warning', 'dwell_alert'): 'fair_use:warning: missing committed dwell/stock alert; phase contract '
    'follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('finalization:blocked_byok', 'entry_deadline'): 'finalization:blocked_byok: missing deadline stamped at entry; '
    'phase contract follow-up; no fix PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('finalization:completed', 'dwell_alert'): 'finalization:completed: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:capturing', 'automatic_exit'): 'record_audio:capturing: missing independent automatic exit; '
    'freshtitles open-producer-token fix, no PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('record_audio:capturing', 'dwell_alert'): 'record_audio:capturing: missing committed dwell/stock alert; '
    'freshtitles open-producer-token fix, no PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('record_audio:capturing', 'dwell_metric'): 'record_audio:capturing: missing authoritative dwell/stock gauge; '
    'freshtitles open-producer-token fix, no PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('record_audio:capturing', 'entry_deadline'): 'record_audio:capturing: missing deadline stamped at entry; '
    'freshtitles open-producer-token fix, no PR yet; ANX '
    'lcinv-lifecycle-invariants',
    ('record_audio:record_audio_partial', 'dwell_alert'): 'record_audio:record_audio_partial: missing committed '
    'dwell/stock alert; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_audio_partial', 'dwell_metric'): 'record_audio:record_audio_partial: missing authoritative '
    'dwell/stock gauge; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_audio_partial', 'entry_deadline'): 'record_audio:record_audio_partial: missing deadline '
    'stamped at entry; phase contract follow-up; no fix PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'automatic_exit'): 'record_audio:record_upload_failed: missing independent '
    'automatic exit; Sticky bit; full-proof repair exists, '
    'but reconnect is not retry; freshtitles fix, no PR '
    'yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'dwell_alert'): 'record_audio:record_upload_failed: missing committed '
    'dwell/stock alert; Sticky bit; full-proof repair exists, '
    'but reconnect is not retry; freshtitles fix, no PR yet; '
    'ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'dwell_metric'): 'record_audio:record_upload_failed: missing authoritative '
    'dwell/stock gauge; Sticky bit; full-proof repair exists, '
    'but reconnect is not retry; freshtitles fix, no PR yet; '
    'ANX lcinv-lifecycle-invariants',
    ('record_audio:record_upload_failed', 'entry_deadline'): 'record_audio:record_upload_failed: missing deadline '
    'stamped at entry; Sticky bit; full-proof repair '
    'exists, but reconnect is not retry; freshtitles fix, '
    'no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:sealed', 'automatic_exit'): 'record_audio:sealed: missing independent automatic exit; No job: '
    'manual digest-gated nojob recovery is not an automatic exit; '
    'freshtitles fix, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:sealed', 'dwell_alert'): 'record_audio:sealed: missing committed dwell/stock alert; No job: '
    'manual digest-gated nojob recovery is not an automatic exit; '
    'freshtitles fix, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:sealed', 'dwell_metric'): 'record_audio:sealed: missing authoritative dwell/stock gauge; No job: '
    'manual digest-gated nojob recovery is not an automatic exit; '
    'freshtitles fix, no PR yet; ANX lcinv-lifecycle-invariants',
    ('record_audio:sealed', 'entry_deadline'): 'record_audio:sealed: missing deadline stamped at entry; No job: '
    'manual digest-gated nojob recovery is not an automatic exit; '
    'freshtitles fix, no PR yet; ANX lcinv-lifecycle-invariants',
    ('summary_debt:completed', 'dwell_alert'): 'summary_debt:completed: missing committed dwell/stock alert; phase '
    'contract follow-up; no fix PR yet; ANX lcinv-lifecycle-invariants',
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


def parameters():
    for row in STATES:
        for clause in CLAUSES:
            reason = KNOWN_GAPS.get((row.key, clause))
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
            yield pytest.param(row, clause, id=f'{row.key}/{clause}', marks=marks)


@pytest.mark.parametrize('row,clause', list(parameters()))
def test_latch_clause(row, clause):
    assert_clause(row, clause)


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
        'record_audio': {'capturing', 'sealed', 'record_upload_failed', 'record_audio_partial'},
        'summary_debt': {'pending', 'completed'},
        'fair_use': {'warning', 'throttle', 'restrict'},
        'visibility': {'bridge_pending', 'settling_hold'},
    }
    for machine, states in required.items():
        assert states <= {row.state for row in STATES if row.machine == machine}


def test_resolved_plan_gaps_do_not_regress():
    rows = {row.key: row for row in STATES}
    for key, clause in (
        ('fair_use:throttle', 'automatic_exit'),
        ('finalization:blocked_byok', 'dwell_alert'),
        ('finalization:dead_letter', 'dwell_alert'),
        ('batch:leased', 'entry_deadline'),
        ('visibility:bridge_pending', 'entry_deadline'),
    ):
        assert (key, clause) not in KNOWN_GAPS
        assert_clause(rows[key], clause)


def test_deadline_probe_rejects_a_read_without_an_entry_write():
    assert 'deadline_at' not in assigned_fields("def read(row):\n    return row.get('deadline_at')\n")
    assert 'deadline_at' in assigned_fields("def enter(row):\n    row['deadline_at'] = now + 600\n")
