"""The rollout gate must refuse incomplete, stale or unsafe operator evidence."""

import importlib.util
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'audio_storage_ramp_gate', Path(__file__).resolve().parents[2] / 'scripts/check_audio_storage_ramp.py'
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def receipt_for(step):
    previous, hold, stop, regional = gate.STEPS[step]
    env = {
        'AUDIO_ARCHIVE_STOP_PCM_ENABLED': 'true',
        'AUDIO_ARCHIVE_STOP_PCM_PERCENT': str(stop),
        'AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED': 'true' if regional else 'false',
        'AUDIO_ARCHIVE_REGIONAL_CACHE_PERCENT': str(regional),
        'BUCKET_AUDIO_DERIVED': 'omi-audio-derived-uc1' if regional else '',
        'AUDIO_DURABLE_OUTBOX_ENABLED': 'true',
        'AUDIO_ARCHIVE_READ_ENABLED': 'true',
    }
    applied = NOW - timedelta(hours=2)
    return {
        'previous_step': previous,
        'previous_applied_at': (applied - timedelta(hours=max(hold, 2))).isoformat(),
        'applied_at': applied.isoformat(),
        'lead_apply_ref': 'bus:synthetic-apply',
        'baseline_acceptance_ref': 'bus:synthetic-baseline',
        'cohort_attribution_ref': 'report:synthetic-cohort',
        'before': {
            'start': (applied - timedelta(hours=1)).isoformat(),
            'end': applied.isoformat(),
            'private_write_per_hour': 300000,
            'pcm_writes_avoided_per_hour': 10,
            'regional_write_per_hour': 0,
        },
        'after': {
            'start': applied.isoformat(),
            'end': NOW.isoformat(),
            'private_write_per_hour': 290000,
            'pcm_writes_avoided_per_hour': 100,
            'regional_write_per_hour': 100,
            'custody': {
                service: {'commits': 100, 'failures': 0, 'would_drop': 0, 'evidence_ref': 'report:synthetic-custody'}
                for service in ('listen', 'pusher')
            },
        },
        'serving': {
            surface: [
                {
                    'release_sha': 'a' * 40,
                    'image_digest': 'sha256:' + 'b' * 64,
                    'share_percent': 100,
                    'ready': True,
                    'effective_env': deepcopy(env),
                }
            ]
            for surface in gate.SURFACES
        },
        'quality': {
            name: {'passed': True, 'evidence_ref': 'report:synthetic-quality'}
            for name in ('batch_stt', 'shadow_wer', 'speech_redrive', 'playback', 'audio_merge', 'decode_failed')
        },
        'iam': {'passed': True, 'evidence_ref': 'report:synthetic-iam'},
        'dual_list': {'passed': True, 'evidence_ref': 'report:synthetic-list'},
    }


@pytest.mark.parametrize('step', gate.STEPS)
def test_complete_evidence_passes_each_step(step):
    assert gate.check(step, receipt_for(step), NOW) == []


@pytest.mark.parametrize('service', ('listen', 'pusher'))
def test_custody_failure_refuses(service):
    receipt = receipt_for('stop-5')
    receipt['after']['custody'][service]['failures'] = 1
    assert any('custody risk' in error for error in gate.check('stop-5', receipt, NOW))


def test_missing_custody_is_not_zero():
    receipt = receipt_for('stop-5')
    del receipt['after']['custody']['listen']['failures']
    with pytest.raises(KeyError):
        gate.check('stop-5', receipt, NOW)


def test_disabled_custody_refuses_even_if_cost_drops():
    receipt = receipt_for('stop-5')
    receipt['serving']['gke/pusher'][0]['effective_env']['AUDIO_DURABLE_OUTBOX_ENABLED'] = 'false'
    assert any('AUDIO_DURABLE_OUTBOX_ENABLED' in error for error in gate.check('stop-5', receipt, NOW))


def test_every_traffic_revision_must_have_expected_flags():
    receipt = receipt_for('stop-5')
    active = receipt['serving']['cloud_run/backend'][0]
    active['share_percent'] = 95
    old = deepcopy(active)
    old['share_percent'] = 5
    old['effective_env']['AUDIO_ARCHIVE_STOP_PCM_PERCENT'] = '0'
    receipt['serving']['cloud_run/backend'].append(old)
    assert any('AUDIO_ARCHIVE_STOP_PCM_PERCENT' in error for error in gate.check('stop-5', receipt, NOW))


@pytest.mark.parametrize('step', ('stop-25', 'stop-100', 'regional-100'))
def test_previous_soak_is_not_optional(step):
    receipt = receipt_for(step)
    receipt['previous_applied_at'] = receipt['applied_at']
    assert any('soak' in error for error in gate.check(step, receipt, NOW))


def test_old_lookback_cannot_trip_or_pass_new_step():
    receipt = receipt_for('stop-5')
    receipt['after']['start'] = receipt['before']['start']
    assert any('new-state' in error for error in gate.check('stop-5', receipt, NOW))


def test_stale_receipt_refuses():
    assert any('last hour' in error for error in gate.check('stop-5', receipt_for('stop-5'), NOW + timedelta(hours=2)))


@pytest.mark.parametrize('field', ('iam', 'dual_list'))
def test_regional_requires_iam_and_noncohort_read_guard(field):
    receipt = receipt_for('regional-5')
    receipt[field]['passed'] = False
    assert gate.check('regional-5', receipt, NOW)


@pytest.mark.parametrize('value', (float('nan'), float('inf'), -1, True))
def test_invalid_numeric_telemetry_refuses(value):
    receipt = receipt_for('stop-5')
    receipt['after']['private_write_per_hour'] = value
    with pytest.raises(ValueError):
        gate.check('stop-5', receipt, NOW)
