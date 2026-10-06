"""Bounded ``s1_refused`` telemetry for the S1 claim gate.

The gate decision (``_s1_claims_complete``) is unchanged; when S1 is required
and the gate returns False, exactly one bounded log line and one
``omi_sync_lineage_resolve_total{outcome="s1_refused"}`` increment record a
closed refusal reason. Reasons never carry ids, filenames, roots, uids or
claim content, and telemetry failures must not change the False decision.
"""

import logging
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

import tests.unit.test_sync_v2 as sync_v2_harness
from tests.unit.test_sync_recording_lineage import ORIGIN, generation
from tests.unit.test_wal_audio_coverage_pipeline import (
    BIN_NAME,
    _claim,
    _coverage_env,
    _run_batch,
    _s1_spies,
    _WHOLE_BATCH_ARGS,
    _wire,
)
from utils.sync import recording_lineage
from utils.sync.recording_lineage import (
    OUTCOMES,
    S1_REFUSAL_REASONS,
    emit_s1_refusal,
    lineage_resolution_requested,
)

VALID = {BIN_NAME: _claim()}


@pytest.fixture
def coordinator():
    module, stubs = sync_v2_harness.TestAsyncCoordinatorBehavioral._load_sync_module()
    try:
        yield module, stubs
    finally:
        sync_v2_harness.TestAsyncCoordinatorBehavioral._cleanup(stubs['saved_modules'])


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', 'true')
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')


def _request(monkeypatch, caplog, claims, filenames, *, s1_env='true', dark='true', metric_broken=False):
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', s1_env)
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', dark)
    metrics = MagicMock()
    if metric_broken:
        metrics.labels.side_effect = RuntimeError('metric backend down')
    monkeypatch.setattr(recording_lineage, 'OMI_SYNC_LINEAGE_RESOLVE_TOTAL', metrics)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        requested = lineage_resolution_requested(
            'u', ORIGIN, 1.0, 2.0, capture_evidence_claims=deepcopy(claims), filenames=filenames
        )
    outcomes = [call.kwargs['outcome'] for call in metrics.labels.call_args_list]
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()]
    return requested, outcomes, lines


def test_s1_refused_is_a_registered_outcome():
    assert 's1_refused' in OUTCOMES
    assert set(S1_REFUSAL_REASONS) == {
        'no_claims',
        'parse_failed',
        'count_mismatch',
        'filename_mismatch',
        'not_admitted',
    }


@pytest.mark.parametrize(
    ('claims', 'filenames', 'reason'),
    [
        (None, [BIN_NAME], 'no_claims'),
        ({}, [BIN_NAME], 'no_claims'),
        (['not', 'a', 'mapping'], [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: 'not-a-dict'}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: {**_claim(), 'capture_root': 'not-a-uuid'}}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: {**_claim(), 'codec': 'aac'}}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: {**_claim(), 'channel': 'stereo'}}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: {**_claim(), 'frame_count': 0}}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: {**_claim(), 'rate_hz': 0}}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: {**_claim(), 'source_frame_start': -1}}, [BIN_NAME], 'parse_failed'),
        ({BIN_NAME: _claim()}, [], 'count_mismatch'),
        ({BIN_NAME: _claim()}, [BIN_NAME, 'extra.bin'], 'count_mismatch'),
        ({BIN_NAME: _claim(), 'g.bin': _claim()}, [BIN_NAME, BIN_NAME], 'count_mismatch'),
        ({'a.bin': _claim(), 'b.bin': _claim()}, ['c.bin', 'd.bin'], 'filename_mismatch'),
        ({f'f{i}.bin': _claim() for i in range(21)}, [f'f{i}.bin' for i in range(21)], 'count_mismatch'),
    ],
    ids=[
        'none',
        'empty-map',
        'nonmapping',
        'nondict-claim',
        'bad-root',
        'bad-codec',
        'bad-channel',
        'zero-frames',
        'zero-rate',
        'negative-start',
        'no-filenames',
        'unequal-counts',
        'duplicate-filenames',
        'filename-mismatch',
        'over-20-claims',
    ],
)
def test_refusal_reasons_emit_once_and_stay_bounded(monkeypatch, caplog, claims, filenames, reason):
    requested, outcomes, lines = _request(monkeypatch, caplog, claims, filenames)
    assert requested is False
    assert outcomes == ['s1_refused']
    assert len(lines) == 1
    assert f'outcome=s1_refused reason={reason}' in lines[0]
    assert 'job_ref=none' in lines[0]


def test_dark_write_disabled_classifies_not_admitted(monkeypatch, caplog):
    requested, outcomes, lines = _request(monkeypatch, caplog, VALID, [BIN_NAME], dark='false')
    assert requested is False
    assert outcomes == ['s1_refused']
    assert 'reason=not_admitted' in lines[0]


def test_oversize_serialized_claim_set_is_parse_failed(monkeypatch, caplog):
    names = [f"{'a' * 240}{i:03d}.bin" for i in range(20)]
    claims = {name: _claim() for name in names}
    requested, outcomes, lines = _request(monkeypatch, caplog, claims, names)
    assert requested is False
    assert outcomes == ['s1_refused'] and 'reason=parse_failed' in lines[0]


def test_valid_claims_pass_silently(monkeypatch, caplog):
    requested, outcomes, lines = _request(monkeypatch, caplog, VALID, [BIN_NAME])
    assert requested is True
    assert outcomes == [] and lines == []


def test_s1_gate_off_bypasses_silently(monkeypatch, caplog):
    requested, outcomes, lines = _request(monkeypatch, caplog, None, [], s1_env='off')
    assert requested is True
    assert outcomes == [] and lines == []


def test_malicious_claim_content_never_reaches_the_log(monkeypatch, caplog):
    hostile = {'secret_name_evil.bin': {**_claim(), 'capture_root': 'not-a-uuid\nforged line'}}
    requested, outcomes, lines = _request(monkeypatch, caplog, hostile, ['secret_name_evil.bin'])
    assert requested is False
    assert len(lines) == 1
    for forbidden in ('secret_name_evil', 'not-a-uuid', 'forged', 'u\n', 'account'):
        assert forbidden not in lines[0]


def test_metric_failure_does_not_change_the_false_decision(monkeypatch, caplog):
    requested, _, lines = _request(monkeypatch, caplog, None, [BIN_NAME], metric_broken=True)
    assert requested is False
    assert len(lines) == 1 and 'reason=no_claims' in lines[0]


def test_emit_s1_refusal_clamps_unknown_reasons(monkeypatch, caplog):
    metrics = MagicMock()
    monkeypatch.setattr(recording_lineage, 'OMI_SYNC_LINEAGE_RESOLVE_TOTAL', metrics)
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        emit_s1_refusal('attacker-supplied')
        emit_s1_refusal('count_mismatch')
    assert [call.kwargs['outcome'] for call in metrics.labels.call_args_list] == ['s1_refused'] * 2
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()]
    assert 'reason=parse_failed' in lines[0]
    assert 'reason=count_mismatch' in lines[1]
    assert 'attacker-supplied' not in lines[0]


@pytest.mark.asyncio
async def test_observed_map_count_mismatch_emits_one_s1_refusal(coordinator, monkeypatch, tmp_path):
    """Post-decode: source-map count != surviving WAV count emits count_mismatch
    exactly once before the legacy whole-batch resolution runs."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    refusals = []
    lineage_module = getattr(pipeline, 'sync_recording_lineage', recording_lineage)
    monkeypatch.setattr(lineage_module, 'emit_s1_refusal', lambda reason: refusals.append(reason))

    async def coverage(uid, source, should_lock, client_device_id, session, claims, wav_paths, decoded_frames, **kw):
        return (list(wav_paths), {}, False)

    pipeline.apply_sync_wal_audio_coverage = coverage
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path)
    assert refusals == ['count_mismatch']
    assert spies.plan_calls == []
    assert spies.resolver_calls == [_WHOLE_BATCH_ARGS]
    assert state.outcomes[-1].value == 'success'
