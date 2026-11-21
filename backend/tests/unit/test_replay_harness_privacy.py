"""Lightweight deterministic corpus/wire checks; real readers belong in integration."""

import json
from pathlib import Path

import pytest

from testing.replay_harness.gen_privacy_timeline import FAULTS, KINDS, generate, write_case
from testing.replay_harness.manifest import load_case
from testing.replay_harness.privacy_faults import not_applicable_reason, fault_applied
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
    assert {(r['family'], r['fault']) for r in rows} == {
        (f, fault) for f in KINDS for fault in FAULTS if not not_applicable_reason(f, fault)
    }


def test_full_corpus_is_stable_bounded_and_has_no_identity_fields():
    first, second = generate(), generate()
    assert json.dumps(first) == json.dumps(second)
    rows = validate_rows(first)
    assert len(rows) == 1400
    assert sum(row['fault'] != 'none' for row in rows) >= 1000
    assert all(not not_applicable_reason(row['family'], row['fault']) for row in rows)
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
    assert '| subscription | drop_invalidation | 0/0 | 1/0/1 | 1/1/1 | 1/1/1 | 1/1/1 |' in table(details)


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

    async def transition(self, row, details, record):
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


def test_applicability_and_fault_evidence_are_required():
    from testing.replay_harness.privacy_report import summary, table

    details = summary()
    cells = [c for family in details['fault_coverage'].values() for c in family.values()]
    assert sum(not c['applicable'] for c in cells) == 10
    assert '| batch_privacy | redis_down | N/A |' in table(details)
    assert not fault_applied('none', {})
    assert not fault_applied('redis_down', {'injected': {}})
    assert fault_applied('redis_down', {'injected': {'begin': 1}})
    assert not fault_applied('drop_invalidation', {'injected': {'begin': 1}})
    assert fault_applied('drop_invalidation', {'injected': {'begin': 1, 'end': 1}})
    assert not fault_applied('begin_loss', {'injected': {'begin': 1}})
    assert fault_applied('begin_loss', {'injected': {'begin': 1}, 'successful': {'end': 1}})
    assert not fault_applied('concurrent', {'synchronized_writers': 1, 'overlap_reads': 1})
    assert fault_applied('concurrent', {'synchronized_writers': 2, 'overlap_reads': 1})
    assert not fault_applied('request_memo', {'request_memo_warmed': True, 'request_memo_hit': True})


def test_deletion_request_scope_requires_redis_and_cross_request_visibility_evidence():
    evidence = {
        'request_memo_absent': True,
        'independent_writer_scope': True,
        'reader_scope_preserved': True,
        'request_redis_warm_reads': 2,
        'request_redis_probe_reads': [1] * 6,
        'request_deletion_observed': True,
    }
    assert fault_applied('request_memo', evidence, family='deletion_marker')
    for key in evidence:
        assert not fault_applied(
            'request_memo', {k: v for k, v in evidence.items() if k != key}, family='deletion_marker'
        )
    for key, value in (
        ('request_memo_absent', False),
        ('independent_writer_scope', False),
        ('reader_scope_preserved', False),
        ('request_redis_warm_reads', 1),
        ('request_redis_probe_reads', []),
        ('request_redis_probe_reads', [1, 0, 1, 1, 1, 1]),
        ('request_deletion_observed', False),
    ):
        assert not fault_applied('request_memo', {**evidence, key: value}, family='deletion_marker')
    # Subscription readers still have a memo and must prove its lifecycle.
    assert not fault_applied('request_memo', evidence, family='subscription')
    assert fault_applied(
        'request_memo',
        {'request_memo_warmed': True, 'request_memo_hit': True, 'request_memo_cleared': True},
        family='subscription',
    )


@pytest.mark.parametrize(
    'minimum,applied,reason', [(1000, True, 'insufficient_verified_transitions'), (0, False, 'unverified_fault')]
)
def test_gate_counts_only_verified_faults(monkeypatch, minimum, applied, reason):
    import asyncio
    from dataclasses import replace
    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    rows = [
        {'family': 'subscription', 'kind': 'upgrade', 'fault': 'none'},
        {'family': 'batch_privacy', 'kind': 'advance', 'fault': 'redis_down'},
        {'family': 'subscription', 'kind': 'byok_enable', 'fault': 'begin_loss'},
    ]
    case = load_case(FIXTURE)
    case = replace(
        case,
        corpus={'privacy_cache': {'transitions': rows}},
        manifest=replace(
            case.manifest, stages={'privacy_cache': {'expect': 'pass', 'min_verified_transitions': minimum}}
        ),
    )

    async def transition(self, row, details, record):
        record['fault_applied'] = applied and row['fault'] == 'begin_loss'

    monkeypatch.setattr(PrivacyCacheDriver, 'transition', transition)
    result = asyncio.run(PrivacyCacheDriver().run(case))
    assert result.reason == 'privacy_cache:' + reason
    assert result.details['verified_transitions'] == int(applied)
    assert result.details['verified_baselines'] == result.details['not_applicable_transitions'] == 1
    assert result.details['qualification_met'] is False
    assert [r['verification'] for r in result.details['transition_results']] == [
        'baseline',
        'not_applicable',
        'verified' if applied else 'unverified',
    ]


@pytest.mark.parametrize('minimum', [True, -1, 1, 999, 1001, '1000'])
def test_manifest_rejects_invalid_verification_gate(minimum):
    from testing.replay_harness.manifest import validate_manifest

    value = load_case(FIXTURE).manifest.to_dict()
    value['stages']['privacy_cache']['min_verified_transitions'] = minimum
    with pytest.raises(ValueError, match='min_verified_transitions'):
        validate_manifest(value)


def test_overlap_retries_only_recognized_aborts_after_joining_all_writers():
    from concurrent.futures import Future
    from google.api_core.exceptions import Aborted
    from testing.replay_harness.stages.privacy_overlap import finish_writers

    aborted, committed = Future(), Future()
    error = ValueError('transaction exhausted')
    error.__cause__ = Aborted('synthetic contention')
    aborted.set_exception(error)
    committed.set_result(None)
    calls = []
    assert finish_writers([aborted, committed], lambda: calls.append('real retry')) == [
        'aborted_then_committed',
        'committed',
    ]
    assert calls == ['real retry']
    unrelated = Future()
    unrelated.set_exception(ValueError('not an Aborted transaction'))
    with pytest.raises(ValueError):
        finish_writers([unrelated], lambda: calls.append('must not retry'))
    assert calls == ['real retry']
