"""A new or changed People writer cannot silently inherit a prior audit."""

import ast
import importlib.util
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    'people_inventory', ROOT / 'backend/scripts/people_generation_inventory.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_current_people_scopes_match_the_reviewed_writer_enumeration():
    expected = json.loads((ROOT / audit.INVENTORY).read_text())
    delta = audit.changes(expected, audit.inventory(ROOT))
    assert not any(delta.values()), f'People writer scope needs generation re-audit: {delta}'


def test_new_writer_without_generation_bump_is_not_covered_by_an_old_audit():
    source = '''
def new_writer(client):
    client.collection('users').document('owner').collection('people').document('p').update({'name': 'changed'})
'''
    delta = audit.changes({}, audit.fingerprints(source))
    assert delta['new'] == ['new_writer']


def test_removing_a_real_writers_generation_bump_invalidates_its_audit():
    source = (ROOT / 'backend/database/people.py').read_text()
    expected = audit.fingerprints(source)

    class RemoveBump(ast.NodeTransformer):
        def visit_Call(self, node):
            if audit._name(node) == 'bump_people_generation':
                return ast.copy_location(ast.Constant(None), node)
            return self.generic_visit(node)

    tree = ast.fix_missing_locations(RemoveBump().visit(ast.parse(source)))
    delta = audit.changes(expected, audit.fingerprints(ast.unparse(tree)))
    assert delta['changed'] or delta['removed']


def test_repeat_counter_and_paid_generation_grade_metrics_leave_both_gmp_profiles():
    metrics = (
        'omi_people_scan_dedupe_total',
        'omi_firestore_billed_reads_by_caller_total',
        'omi_firestore_billed_reads_by_origin_total',
        'omi_fsr_leader_lease_total',
    )
    for name in ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'):
        profile = yaml.safe_load((ROOT / 'backend/deploy' / name).read_text())
        rules = profile['spec']['endpoints'][0]['metricRelabeling']
        keep = [rule['regex'] for rule in rules if rule['action'] == 'keep' and rule['sourceLabels'] == ['__name__']]
        assert all(any(re.fullmatch(pattern, metric) for pattern in keep) for metric in metrics)


def test_read_only_people_reader_changes_also_require_reaudit():
    source = """
def reader(client):
    return client.collection('people').document('p').get(field_paths=['name'])
"""
    reviewed = audit.fingerprints(source)
    assert audit.changes({}, reviewed)['new'] == ['reader']
    changed = audit.fingerprints(source.replace("['name']", "['name', 'is_dismissed']"))
    assert audit.changes(reviewed, changed)['changed'] == ['reader']
