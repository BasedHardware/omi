"""Offline name/inventory and retained-shape documentation guard for #24736/#24745.

Read source, never import serving code or construct a cloud client. The shared
state inventory is a pure declaration; existing lifecycle tests audit writers.
Runtime CAS behavior belongs to the dedicated held-dead-letter tests.
"""

import ast
import re
from pathlib import Path

from tests.support.lifecycle_state_table import STATES

BACKEND = Path(__file__).resolve().parents[2]
CONTRACT = BACKEND / 'utils/batch_pipeline/CONTRACT.md'


def held_section():
    text = CONTRACT.read_text()
    heading = '## Held / dead-letter state table\n'
    assert text.count(heading) == 1, 'Keep one owned held/dead-letter contract'
    return text.split(heading, 1)[1].split('\n## ', 1)[0]


def test_state_inventory_is_documented():
    # Match table keys, not incidental prose; grouping/reflow of cells is fine.
    machines = {
        'batch',
        'batch_projection',
        'finalization',
        'record_audio',
        'record_audio_orphan',
        'record_token',
        'conversation',
    }
    documented = set(re.findall(r'^\| `([a-z_]+:[a-z_]+)`(?: \(computed\))? \|', held_section(), re.MULTILINE))
    expected = {row.key for row in STATES if row.machine in machines}
    assert documented == expected, f'Undocumented: {expected - documented}; stale: {documented - expected}'


def test_documented_flags_exist_in_runtime_and_registry():
    section = held_section()
    flags = set(re.findall(r'^\| `([A-Z][A-Z0-9_]+)` \|', section, re.MULTILINE))
    flags.update(re.findall(r'`([A-Z][A-Z0-9_]+(?:_ENABLED|_TOKENS))`', section))
    assert 'BATCH_HELD_DEAD_LETTER_ENABLED' in flags
    # Small, bounded source set: no tests or docs can satisfy runtime existence.
    paths = [
        'config/batch_pipeline.py',
        'database/conversations.py',
        'config/policy/kill_switches.py',
        'config/refactor_modes.py',  # new refactor switches are declared here (BATCH_INPUT_EXPIRING_ENABLED)
        'config/batch_pipeline_vendor_failover.py',
        'config/listen_finalization.py',
        'config/record_seal_rules.py',
        'config/record_partial.py',
        'services/conversation_finalization.py',
        'utils/pusher_record_finish.py',
    ]
    literals = {
        node.value
        for path in paths
        for node in ast.walk(ast.parse((BACKEND / path).read_text()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    registry = (BACKEND / 'docs/feature-flag-registry.md').read_text()
    assert flags <= literals, f'Flags absent from runtime declarations: {flags - literals}'
    assert all(f'`{flag}`' in registry for flag in flags), 'Documented flag missing from registry'


def test_documented_metrics_exist_and_expiry_alert_uses_them():
    metrics = set(re.findall(r'`((?:omi_|listen_)[a-z0-9_]+)`', held_section()))
    paths = [
        'database/record_token_lease_metrics.py',
        'utils/metrics.py',
        'utils/batch_pipeline/metrics.py',
        'utils/batch_pipeline/vendor_route_contracts.py',
        'utils/batch_pipeline/record_seal_sweeper.py',
        'services/conversation_finalization.py',
    ]
    trees = [ast.parse((BACKEND / path).read_text()) for path in paths]
    declared = {
        node.value
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    # PhaseMetrics builds names from a literal prefix and Gauge suffix. Derive
    # both sides from source so a spelling change cannot pass on a doc mention.
    factory = ast.parse((BACKEND / 'utils/lifecycle_metrics.py').read_text())
    suffixes = {
        node.args[0].right.value
        for node in ast.walk(factory)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'Gauge'
        and node.args
        and isinstance(node.args[0], ast.BinOp)
        and isinstance(node.args[0].op, ast.Add)
        and isinstance(node.args[0].left, ast.Name)
        and node.args[0].left.id == 'prefix'
        and isinstance(node.args[0].right, ast.Constant)
        and isinstance(node.args[0].right.value, str)
    }
    declared.update(
        node.args[0].value + suffix
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'PhaseMetrics'
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        for suffix in suffixes
    )
    assert metrics <= declared, f'Metrics absent from runtime source: {metrics - declared}'
    expiry = {
        'omi_batch_held_expired_total',
        'omi_batch_held_expired_units',
        'omi_batch_held_expired_observed_at_seconds',
    }
    assert expiry <= metrics, 'Keep all retained-expiry metric families in the contract'
    alert = (BACKEND / 'charts/monitoring/alerts/batch-held-dead-letter.json').read_text()
    assert all(re.search(rf'\b{metric}\b', alert) for metric in expiry)
    assert 'batch_held_dead_letter' in (BACKEND / 'utils/batch_pipeline/held_dead_letter.py').read_text()


def test_retained_shape_fields_stay_explicit():
    # Pin documentation spellings, not the whole prose or its line layout.
    # The runtime CAS itself is exercised by the dedicated 4a/4b suites.
    section = held_section()
    job, projection = section.split('Phase 4a,', 1)[1].split('Phase 4b,', 1)
    required = (
        (job, {'state=dead', 'dead_letter_reason=held_expired', 'held_expired_at=now', 'merge_pending=true'}),
        (
            projection,
            {
                'projection_state=quarantine_held',
                'held_expired_at=now',
                'held_expired_reason=held_expired',
                'held_expired_release_attempts',
                'projection_release_attempts=0',
            },
        ),
    )
    for text, fields in required:
        documented = set(re.findall(r'`([^`]+)`', text))
        assert fields <= documented, f'Retained rollback shape omitted: {fields - documented}'
