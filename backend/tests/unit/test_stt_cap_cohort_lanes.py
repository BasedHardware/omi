"""Shared rollout decisions: explicit scope, stable widening and manifest safety."""

import ast
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from config import rollout_cohorts as cohorts, stt_cap_dispatch as policy


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for key in (
        'STT_CAP_DISPATCH_ENFORCEMENT',
        'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED',
        'STT_CAP_DISPATCH_COHORT',
        'STT_CAP_DISPATCH_LANES',
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize('dispatch,ladder', [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize('uid', ['chosen', 'other'])
@pytest.mark.parametrize('lane', ['live', 'sync', 'batch'])
@pytest.mark.parametrize(
    'lanes', [None, '', ' \t ', 'live', 'sync', 'batch', 'live,sync', 'live,batch', 'live,sync,batch', 'live,typo']
)
@pytest.mark.parametrize('cohort', [None, '', 'uid:chosen', 'uid:chosen,pct:0', 'all', 'pct:100', 'uid:chosen,typo'])
def test_execution_scope_matrix(monkeypatch, dispatch, ladder, uid, lane, lanes, cohort):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    if lanes is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    if cohort is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', cohort)
    owner_selected = cohort in {'all', 'pct:100'} or uid == 'chosen' and cohort in {'uid:chosen', 'uid:chosen,pct:0'}
    configured = {'live'} if lanes is None or not lanes.strip() else set(lanes.split(','))
    lane_selected = configured <= {'live', 'sync', 'batch'} and lane in configured and lane != 'batch'
    assert policy.selected(uid, lane) is bool(owner_selected and lane_selected)
    assert policy.execution_admission_enabled(uid, lane) is bool(
        (dispatch or ladder) and owner_selected and lane_selected
    )
    assert policy.enabled_for(uid, lane) is bool(dispatch and owner_selected and lane_selected)


@pytest.mark.parametrize(
    'raw,expected',
    [
        (None, {'live'}),
        ('', {'live'}),
        (' \t\n ', {'live'}),
        ('live', {'live'}),
        ('live,batch', {'live'}),
        ('batch', set()),
        ('live,sync', {'live', 'sync'}),
        (' SYNC , Live , batch ', {'live', 'sync'}),
        ('live,typo', set()),
        ('live,', set()),
        (',live', set()),
        ('live,,sync', set()),
        (',', set()),
    ],
)
def test_lane_defaults_and_batch_readiness_fence(monkeypatch, raw, expected):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    if raw is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_LANES', raw)
    assert policy._BATCH_LANE_READY is False
    assert {lane for lane in policy.LANES if policy.selected('synthetic', lane)} == expected


def test_batch_configuration_warns_once_across_subjects_lanes_and_threads(monkeypatch, caplog):
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,sync,batch')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setattr(policy, '_batch_warning_emitted', False)
    caplog.set_level(logging.WARNING, logger=policy.__name__)
    subjects = [(f'synthetic-{i}', lane) for i in range(20) for lane in policy.LANES]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda subject: policy.selected(*subject), subjects))
    assert results == [lane != 'batch' for _, lane in subjects]
    warnings = [record for record in caplog.records if record.name == policy.__name__]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == ('STT cap batch lane remains disabled pending batch admission readiness')
    assert not warnings[0].args


@pytest.mark.parametrize('raw', [None, '', ' \t ', 'live', 'live,sync', 'live,batch,unknown', 'batch,'])
def test_no_batch_warning_without_valid_batch_configuration(monkeypatch, caplog, raw):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    if raw is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_LANES', raw)
    monkeypatch.setattr(policy, '_batch_warning_emitted', False)
    caplog.set_level(logging.WARNING, logger=policy.__name__)
    for uid in ('synthetic-a', 'synthetic-b'):
        for lane in policy.LANES:
            policy.selected(uid, lane)
    assert not [record for record in caplog.records if record.name == policy.__name__]


@pytest.mark.parametrize(
    'raw',
    [
        '',
        'all,pct:1',
        'uid:a,',
        ',uid:a',
        'uid:a,,pct:1',
        'pct:101',
        'pct:-1',
        'pct:nan',
        'pct:1.5',
        'pct:1,pct:2',
        'pct:١',
        'uid:',
        'uid:a/b',
    ],
)
def test_malformed_cohort_is_wholly_denied(raw):
    assert cohorts.parse_cohort(raw) is None
    assert not cohorts.cohort_admits('a', raw)


def test_percentage_matches_retired_parser_and_widens_monotonically(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    previous = set()
    owners = [f'synthetic-{i}' for i in range(500)]
    for percent in (0, 1, 5, 25, 100):
        monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', f'uid:coordinator,pct:{percent}')
        expected = {
            uid
            for uid in owners
            if int(hashlib.sha256(('free-tier-cohort:' + uid).encode()).hexdigest()[:8], 16) % 100 < percent
        }
        actual = {uid for uid in owners if policy.execution_admission_enabled(uid, 'live')}
        assert actual == expected
        assert previous <= actual
        assert policy.execution_admission_enabled('coordinator', 'live')
        previous = actual
    assert previous == set(owners)


@pytest.mark.parametrize('lane', ['', 'unknown', 'fresh', 'backfill', 'LIVE', None])
def test_unknown_callsite_lane_and_missing_owner_never_select(monkeypatch, lane):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    assert not policy.execution_admission_enabled('chosen', lane)
    assert not policy.execution_admission_enabled('', 'live')


@pytest.mark.parametrize(
    'meta,lane',
    [
        ({}, 'sync'),
        ({'source': 'desktop', 'sync_lane': 'backfill'}, 'sync'),
        ({'origin': 'live', 'sync_lane': 'fresh'}, 'live'),
        ({'origin': 'sync'}, 'sync'),
        ({'origin': 'batch'}, 'batch'),
        ({'origin': None}, None),
        ({'origin': 'unknown'}, None),
    ],
)
def test_original_hold_mapping(meta, lane):
    assert policy.hold_lane(meta) == lane


def test_both_runtime_manifests_are_dark_and_live_only():
    root = Path(__file__).parents[2]
    manifest = yaml.load((root / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for env in ('dev', 'prod'):
        config = manifest['environments'][env]
        hosts = [
            config['gke']['backend-listen'],
            config['gke']['pusher'],
            config['desktop_backend'],
            *config['cloud_run']['services'].values(),
        ]
        for host in hosts:
            values = host['env']
            assert values['STT_CAP_DISPATCH_ENFORCEMENT']['value'] == 'false'
            assert values['STT_CAP_DISPATCH_COHORT']['value'] == ''
            assert values['STT_CAP_DISPATCH_LANES']['value'] == 'live'


SCOPED_GATE_FILES = [
    path
    for folder in ('config', 'database', 'utils', 'routers', 'diarizer')
    for path in (Path(__file__).parents[2] / folder).rglob('*.py')
    if 'config.stt_cap_dispatch import' in path.read_text()
]


@pytest.mark.parametrize('path', SCOPED_GATE_FILES, ids=lambda path: str(path.relative_to(Path(__file__).parents[2])))
def test_every_scoped_production_gate_supplies_its_subject(path):
    # Reusable guard for FC-cohort-gate-consulted-without-its-subject. Aliased
    # imports are included; runtime setup predicates deliberately have no UID.
    tree = ast.parse(path.read_text())
    scoped = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'config.stt_cap_dispatch':
            for name in node.names:
                if name.name in {
                    'execution_admission_enabled',
                    'recovery_admission_enabled',
                    'enabled_for',
                    'selected',
                }:
                    scoped[name.asname or name.name] = 2
                elif name.name in {
                    'any_execution_admission_enabled',
                    'any_legacy_admission_enabled',
                    'any_recovery_admission_enabled',
                    'recovery_cohort_admits',
                }:
                    scoped[name.asname or name.name] = 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in scoped:
            assert len(node.args) + len(node.keywords) >= scoped[node.func.id], f'{path}:{node.lineno}'


def test_untrusted_cohort_tokens_are_total_and_do_not_truncate():
    assert cohorts.parse_cohort('pct:' + '9' * 5000) is None
    assert cohorts.parse_cohort('pct:' + '0' * 5000 + '1') == (frozenset(), 1)
    assert cohorts.parse_cohort('uid:\ud800') is None
    assert not cohorts.cohort_admits('\ud800', 'all')
    assert policy.hold_lane([]) is None
