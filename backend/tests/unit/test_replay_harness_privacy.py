"""Lightweight deterministic corpus/wire checks; real readers belong in integration."""

import json
from pathlib import Path

import pytest

from testing.replay_harness.gen_privacy_timeline import FAULTS, KINDS, generate, write_case
from testing.replay_harness.manifest import load_case
from testing.replay_harness.stages.privacy_scenarios import validate_rows

FIXTURE = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures/privacy-transitions-smoke'


def test_smoke_is_byte_reproducible_and_covers_kinds_and_family_faults(tmp_path):
    write_case(tmp_path / FIXTURE.name, transitions=120)
    for name in ('corpus.json', 'manifest.json'):
        assert (tmp_path / FIXTURE.name / name).read_bytes() == (FIXTURE / name).read_bytes()
    case = load_case(FIXTURE)
    rows = validate_rows(case.corpus)
    assert case.manifest.schema_version == 1
    assert {(r['family'], r['kind']) for r in rows} == {(f, k) for f in KINDS for k in KINDS[f]}
    assert {(r['family'], r['fault']) for r in rows} == {(f, fault) for f in KINDS for fault in FAULTS}


def test_full_corpus_is_stable_bounded_and_has_no_identity_fields():
    first, second = generate(), generate()
    assert json.dumps(first) == json.dumps(second)
    rows = validate_rows(first)
    assert len(rows) == 1000
    assert generate(seed=7) != first
    assert all(set(r) == {'family', 'kind', 'fault'} for r in rows)


@pytest.mark.parametrize(
    'seed',
    [
        None,
        {},
        {'transitions': []},
        {'transitions': [{}]},
        {'transitions': [{'family': 'secret-uid', 'kind': 'create', 'fault': 'none'}]},
    ],
)
def test_bad_timeline_rejected_before_infrastructure(seed):
    with pytest.raises(ValueError):
        validate_rows({'privacy_cache': seed})


@pytest.mark.parametrize(
    'kwargs',
    [
        dict(transitions=0),
        dict(transitions=10001),
        dict(transitions=True),
        dict(mix={'unknown': 1}),
        dict(mix={'tombstone': 0}),
        dict(faults=['unknown']),
    ],
)
def test_generator_rejects_unbounded_or_unknown_controls(kwargs):
    with pytest.raises(ValueError):
        generate(**kwargs)


@pytest.mark.parametrize('bound', [0, -1, True, '60', None, float('nan'), float('inf'), 86401])
def test_manifest_rejects_invalid_privacy_bound(bound):
    from testing.replay_harness.manifest import validate_manifest

    value = load_case(FIXTURE).manifest.to_dict()
    value['stages']['privacy_cache']['bound_s'] = bound
    with pytest.raises(ValueError, match='bound_s'):
        validate_manifest(value)


def test_manifest_bound_remains_schema_v1_compatible():
    import jsonschema
    from testing.replay_harness.manifest import validate_manifest, JSON_SCHEMA

    value = load_case(FIXTURE).manifest.to_dict()
    value['stages']['privacy_cache']['bound_s'] = 59.5
    jsonschema.Draft202012Validator(JSON_SCHEMA).validate(value)
    assert validate_manifest(value).stages['privacy_cache']['bound_s'] == 59.5
    del value['stages']['privacy_cache']['bound_s']
    assert validate_manifest(value).schema_version == 1


def test_per_fault_per_offset_counters_and_actual_expiry_margin():
    from testing.replay_harness.privacy_report import summary, observe_probe, observe_expiry, table

    details = summary()
    row = {'family': 'subscription', 'fault': 'drop_invalidation'}
    for offset in (59, 60, 61, 300):
        observe_probe(details, row, offset, False, True, False)
    assert details['probes'] == 4 and details['mismatches'] == 3
    assert details['early_mismatches'] == 1
    cells = details['by_family_fault_offset']['subscription']['drop_invalidation']
    assert cells['59.0'] == {'probes': 1, 'stale': 1, 'mismatches': 0, 'errors': 0}
    assert cells['300.0']['mismatches'] == 1
    assert details['max_observed_staleness_seconds']['subscription'] == 300
    observe_expiry(details, 'subscription', 100, 155000)
    assert details['bound_margin_s'] == 5
    observe_expiry(details, 'deletion_marker', 100, 160000)
    assert details['bound_margin_s'] == 0
    assert details['bound_margin_s_by_family']['data_protection'] is None
    assert '| subscription | drop_invalidation | 1/0/1 | 1/1/1 | 1/1/1 | 1/1/1 |' in table(details)


def test_stage_continues_after_mismatches_and_transition_errors(monkeypatch):
    import asyncio
    from dataclasses import replace
    from testing.replay_harness.privacy_report import observe_probe
    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    rows = [
        {'family': 'subscription', 'kind': kind, 'fault': 'drop_invalidation'}
        for kind in ('byok_enable', 'byok_disable', 'upgrade')
    ]
    case = replace(load_case(FIXTURE), corpus={'privacy_cache': {'transitions': rows}})
    seen = []

    async def transition(self, row, details):
        seen.append(row['kind'])
        if row['kind'] == 'byok_disable':
            raise RuntimeError('private-identifier-must-not-escape')
        observe_probe(details, row, 60, False, True, False)
        observe_probe(details, row, 300, False, True, False)

    monkeypatch.setattr(PrivacyCacheDriver, 'transition', transition)
    result = asyncio.run(PrivacyCacheDriver().run(case))
    assert seen == ['byok_enable', 'byok_disable', 'upgrade']
    assert result.details['attempted_transitions'] == 3
    assert result.details['completed_transitions'] == 2
    assert result.details['mismatches'] == 4 and result.details['probes'] == 4
    assert len(result.details['errors']) == 1
    assert 'private-identifier' not in json.dumps(result.details)
    assert result.reason == 'privacy_cache:staleness_bound_exceeded'
