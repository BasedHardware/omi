"""Offline qualification and the deliberate monthly-reader rollout boundary."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import runpy
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest
import yaml

from config.firestore_read_levers import lever_percent
from scripts import qualify_usage_month as check

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'backend/deploy/runtime_env'
PATCH = CONFIG / 'pending/usage-month-enable-5.patch'
NOW = datetime(2026, 11, 7, 6, tzinfo=timezone.utc)
WINDOW = {
    'started_at': '2026-11-07T03:00:00+00:00',
    'ended_at': '2026-11-07T05:00:00+00:00',
    'valid_until': '2026-11-07T07:00:00+00:00',
}


@pytest.fixture
def evidence(tmp_path):
    suite = ET.Element('testsuite')
    for suites in check.SUITES.values():
        for classname, names in suites.items():
            for name, count in names.items():
                for case in range(count):
                    ET.SubElement(suite, 'testcase', classname=classname, name=f'{name}[{case}]')
    ET.ElementTree(suite).write(tmp_path / 'proof.xml')
    sha, artifact = 'a' * 40, 'image@sha256:' + 'b' * 64
    soak = dict(
        WINDOW,
        artifact=artifact,
        ref='receipt:synthetic-loopback',
        origins_reviewed=True,
        fallback_rate_reviewed=True,
        mismatches=0,
        accounting_regressions=0,
        free_allowance_regressions=0,
        http_5xx_regressions=0,
        live_p95_regressions=0,
        contention_errors=0,
    )
    record = dict(
        WINDOW,
        artifact=artifact,
        source_sha=sha,
        ref='receipt:serving-traffic',
        traffic_verified=True,
        cache_freshness_accepted=True,
        epoch='qualified_epoch',
        soak=soak,
        equivalence={
            mode: {'source_sha': sha, 'ref': 'receipt:existing-tests', 'junit': 'proof.xml'} for mode in check.SUITES
        },
    )
    return {
        'common_epoch': 'qualified_epoch',
        'old_writers_since_initialization': False,
        'services': {name: deepcopy(record) for name in (*check.SERVICES, 'backend-sync')},
        'writers': {
            name: dict(
                WINDOW,
                artifact=artifact,
                ref='receipt:writer-and-drain',
                started_at='2026-11-07T02:00:00+00:00',
                ended_at='2026-11-07T03:00:00+00:00',
                maintains_totals=True,
                invalidates_cache=True,
                old_revisions_jobs_drained=True,
            )
            for name in check.WRITERS
        },
    }


def report(evidence, tmp_path):
    return check.qualify(evidence, now=NOW, base=tmp_path)


def test_missing_evidence_blocks_every_service_and_lever(tmp_path):
    result = report({}, tmp_path)
    assert set(result['services']) == set(check.SERVICES)
    for service in result['services'].values():
        assert set(service) == {'usage_month_cache', 'usage_month_total'}
        for mode in service.values():
            assert not mode['qualified'] and mode['blockers']
    assert check.main([]) == 1


def test_complete_evidence_is_qualified_but_never_authorizes_flip(evidence, tmp_path):
    result = report(evidence, tmp_path)
    assert 'HOLD: lead2' in result['authorization']
    assert all(m['qualified'] for s in result['services'].values() for m in s.values())


@pytest.mark.parametrize('writer', check.WRITERS)
@pytest.mark.parametrize('field', ['maintains_totals', 'old_revisions_jobs_drained', 'artifact', 'ref', 'valid_until'])
def test_every_writer_must_be_qualified(evidence, tmp_path, writer, field):
    del evidence['writers'][writer][field]
    for service in report(evidence, tmp_path)['services'].values():
        assert not service['usage_month_total']['qualified']
        assert any(writer in b for b in service['usage_month_total']['blockers'])


@pytest.mark.parametrize(
    'field',
    [
        'mismatches',
        'accounting_regressions',
        'free_allowance_regressions',
        'http_5xx_regressions',
        'live_p95_regressions',
        'contention_errors',
        'origins_reviewed',
        'fallback_rate_reviewed',
        'artifact',
        'ref',
    ],
)
def test_each_soak_gate_is_required_per_service(evidence, tmp_path, field):
    del evidence['services']['backend']['soak'][field]
    result = report(evidence, tmp_path)['services']
    assert all(not m['qualified'] for m in result['backend'].values())
    assert all(m['qualified'] for m in result['backend-integration'].values())


@pytest.mark.parametrize(
    'field,value',
    [
        ('started_at', '2026-11-07T04:59:59+00:00'),
        ('ended_at', '2026-11-07T08:00:00+00:00'),
        ('valid_until', '2026-11-07T06:00:00+00:00'),
        ('started_at', '2026-11-07T03:00:00'),
    ],
)
def test_short_future_expired_or_naive_soak_blocks(evidence, tmp_path, field, value):
    evidence['services']['backend']['soak'][field] = value
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']


@pytest.mark.parametrize('epoch', ['', 'v1', 'bad epoch', 'different_common_epoch'])
def test_epoch_blocks_total_independently(evidence, tmp_path, epoch):
    evidence['services']['backend']['epoch'] = epoch
    result = report(evidence, tmp_path)['services']['backend']
    assert result['usage_month_cache']['qualified']
    assert not result['usage_month_total']['qualified']


def test_old_or_unknown_writer_history_requires_new_common_epoch(evidence, tmp_path):
    for old in (True, None):
        evidence['old_writers_since_initialization'] = old
        assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']
        evidence['previous_epoch'] = 'qualified_epoch'
        assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']
        evidence['previous_epoch'] = 'previous_epoch'
        assert report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']
        del evidence['previous_epoch']


def test_cache_requires_invalidation_and_scope_freshness(evidence, tmp_path):
    evidence['writers']['operator']['invalidates_cache'] = False
    result = report(evidence, tmp_path)['services']['backend']
    assert not result['usage_month_cache']['qualified']
    assert result['usage_month_total']['qualified']
    evidence['writers']['operator']['invalidates_cache'] = True
    evidence['services']['backend']['cache_freshness_accepted'] = False
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_cache']['qualified']


@pytest.mark.parametrize('change', ['empty', 'missing', 'skip', 'failure', 'error', 'unreadable', 'source'])
def test_equivalence_must_reuse_existing_successful_checks(evidence, tmp_path, change):
    path = tmp_path / 'proof.xml'
    root = ET.parse(path).getroot()
    if change in {'empty', 'missing'}:
        root.remove(root[0])
        if change == 'empty':
            root.clear()
    elif change in {'skip', 'failure', 'error'}:
        ET.SubElement(root[0], 'skipped' if change == 'skip' else change)
    elif change == 'source':
        evidence['services']['backend']['equivalence']['cache']['source_sha'] = 'c' * 40
    ET.ElementTree(root).write(path)
    if change == 'unreadable':
        path.write_text('not XML')
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_cache']['qualified']


def read_yaml(path):
    return yaml.load(path.read_text(), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))


def monthly_config(document, path=''):
    """Snapshot every literal's entire lever map plus monthly epoch/TTL."""
    found = {}
    if isinstance(document, dict):
        if 'FIRESTORE_READ_LEVERS' in document:
            levers = json.loads(document['FIRESTORE_READ_LEVERS']['value'])
            found[path] = {
                'all_levers_sha256': hashlib.sha256(json.dumps(levers, sort_keys=True).encode()).hexdigest(),
                'usage_month_cache': levers['usage_month_cache'],
                'usage_month_total': levers['usage_month_total'],
                **{k: v for k, v in document.items() if k.startswith('FSR_USAGE_MONTH_')},
            }
        for key, value in document.items():
            found.update(monthly_config(value, f'{path}/{key}'))
    return found


def test_served_defaults_remain_unchanged(monkeypatch):
    # Pin all lever maps, not only the two monthly zeros. Pending files are not inputs.
    snapshot = json.loads((Path(__file__).parent / 'fixtures/usage_month_served_defaults.json').read_text())
    for filename, expected in snapshot.items():
        assert monthly_config(read_yaml(ROOT / filename)) == expected, filename
    for raw in (None, '', '{}'):
        if raw is None:
            monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
        else:
            monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
        assert lever_percent('usage_month_cache') == lever_percent('usage_month_total') == 0


def test_pending_patch_only_proposes_six_monthly_lever_changes(tmp_path):
    # Apply only to a disposable copy; the served tree stays byte-for-byte intact.
    destination = tmp_path / 'backend/deploy/runtime_env'
    shutil.copytree(CONFIG, destination)
    subprocess.run(['git', 'apply', str(PATCH)], cwd=tmp_path, check=True, capture_output=True)
    before = read_yaml(CONFIG / 'prod.overlay.yaml')
    after = read_yaml(destination / 'prod.overlay.yaml')
    services = after['overlay']['cloud_run']['services']
    for name in check.SERVICES:
        desc = services[name]['env']['FIRESTORE_READ_LEVERS']
        levers = json.loads(desc['value'])
        assert levers['usage_month_cache'] == levers['usage_month_total'] == 5
        expected_monthly = 0 if name == 'backend-sync-backfill' else 100
        levers.update(usage_month_cache=expected_monthly, usage_month_total=expected_monthly)
        original = before['overlay']['cloud_run']['services'][name]['env']['FIRESTORE_READ_LEVERS']['value']
        assert levers == json.loads(original)
        desc['value'] = original
    assert after == before  # sync, epochs and every other input are preserved


def test_pending_patch_composes_only_the_six_reviewed_values(tmp_path):
    destination = tmp_path / 'backend/deploy/runtime_env'
    shutil.copytree(CONFIG, destination)
    subprocess.run(['git', 'apply', str(PATCH)], cwd=tmp_path, check=True, capture_output=True)
    compose = runpy.run_path(str(ROOT / 'backend/deploy/compose_runtime_env.py'))['compose_manifest']
    before = compose()
    served = read_yaml(ROOT / 'backend/deploy/runtime_env.yaml')
    assert monthly_config(before) == monthly_config(served)  # pending patch is never a compose input
    after = compose(base_path=destination / '_base.yaml', runtime_env_dir=destination)
    for service in check.SERVICES:
        original = before['environments']['prod']['cloud_run']['services'][service]['env']['FIRESTORE_READ_LEVERS']
        candidate = after['environments']['prod']['cloud_run']['services'][service]['env']['FIRESTORE_READ_LEVERS']
        levers = json.loads(candidate['value'])
        assert levers['usage_month_cache'] == levers['usage_month_total'] == 5
        candidate['value'] = original['value']
    assert after == before


@pytest.mark.parametrize('value', [1, -1, False, '0', None])
def test_nonzero_or_unmeasured_soak_is_not_clean(evidence, tmp_path, value):
    evidence['services']['backend']['soak']['mismatches'] = value
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']


def test_writer_qualification_must_precede_soak(evidence, tmp_path):
    evidence['writers']['listen']['ended_at'] = '2026-11-07T04:00:00+00:00'
    result = report(evidence, tmp_path)['services']['backend']
    assert all(not mode['qualified'] for mode in result.values())
    assert any('precede the soak' in b for b in result['usage_month_total']['blockers'])


def test_serving_traffic_evidence_must_cover_entire_soak(evidence, tmp_path):
    evidence['services']['backend']['started_at'] = '2026-11-07T04:00:00+00:00'
    result = report(evidence, tmp_path)['services']['backend']
    assert all(not mode['qualified'] for mode in result.values())
    assert any('serving-traffic window' in b for b in result['usage_month_cache']['blockers'])


@pytest.mark.parametrize('previous', [True, {}, 'bad epoch', ''])
def test_epoch_rotation_requires_a_valid_previous_epoch(evidence, tmp_path, previous):
    evidence['old_writers_since_initialization'] = True
    evidence['previous_epoch'] = previous
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']


def test_file_isolated_existing_reports_can_qualify_together(evidence, tmp_path):
    proof = ET.parse(tmp_path / 'proof.xml').getroot()
    reports = []
    for number, suites in enumerate(check.SUITES.values()):
        report_root = ET.Element('testsuite')
        for case in proof:
            if case.get('classname') in suites:
                report_root.append(case)
        path = f'proof-{number}.xml'
        ET.ElementTree(report_root).write(tmp_path / path)
        reports.append(path)
    for record in evidence['services'].values():
        for mode in record['equivalence'].values():
            mode['junit'] = reports
    assert all(m['qualified'] for s in report(evidence, tmp_path)['services'].values() for m in s.values())
    (tmp_path / reports[-1]).unlink()
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']


@pytest.mark.parametrize('value', [True, {}, ' ', None])
@pytest.mark.parametrize('location', ['service', 'writer', 'soak', 'equivalence'])
def test_evidence_references_must_name_records(evidence, tmp_path, value, location):
    record = evidence['services']['backend']
    if location == 'service':
        record['ref'] = value
    elif location == 'writer':
        evidence['writers']['listen']['ref'] = value
    elif location == 'soak':
        record['soak']['ref'] = value
    else:
        record['equivalence']['total']['ref'] = value
    assert not report(evidence, tmp_path)['services']['backend']['usage_month_total']['qualified']


@pytest.mark.parametrize('missing', [False, True])
def test_common_epoch_includes_the_existing_enabled_reader(evidence, tmp_path, missing):
    if missing:
        del evidence['services']['backend-sync']
    else:
        evidence['services']['backend-sync']['epoch'] = 'other_epoch'
    for modes in report(evidence, tmp_path)['services'].values():
        assert modes['usage_month_cache']['qualified']
        assert not modes['usage_month_total']['qualified']
        assert any('backend-sync' in b for b in modes['usage_month_total']['blockers'])
