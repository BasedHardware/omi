"""Aged completed captures stop waiting on a long-lived pusher pod's restart."""

from datetime import datetime, timedelta, timezone

import pytest

from config.record_seal_rules import live_producer_grace_seconds
from utils.batch_pipeline.record_producer_proof import producers_quiesced
from utils.batch_pipeline.record_seal_repair import seal_refusal

NOW = 2_000_000_000.0
POD = {'pod': 'pusher-synthetic', 'process_started_at': NOW - 86400}


def row(age_seconds, tokens, **extra):
    return {
        'status': 'completed',
        'finished_at': datetime.fromtimestamp(NOW - age_seconds, timezone.utc),
        'record_upload_sessions': tokens,
        'record_lane_owner': 'batch_live_v1',
        'private_cloud_sync_enabled': True,
        **extra,
    }


JOB = {'state': 'record_pending', 'record_content_id': 'synthetic-content'}


@pytest.mark.parametrize(
    'raw,expected', [(None, 3600.0), ('0', 0.0), ('600', 600.0), ('bad', 3600.0), ('-5', 3600.0), ('nan', 3600.0)]
)
def test_grace_setting_is_bounded(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('RECORD_SEAL_LIVE_PRODUCER_GRACE_SECONDS', raising=False)
    else:
        monkeypatch.setenv('RECORD_SEAL_LIVE_PRODUCER_GRACE_SECONDS', raw)
    assert live_producer_grace_seconds() == expected


@pytest.mark.parametrize(
    'age,tokens,status,quiesced',
    [
        (3599, {'s': POD}, 'completed', False),  # still inside grace
        (3600, {'s': POD}, 'completed', True),
        (86400, {'s': POD, 't': POD}, 'completed', True),
        (86400, {'s': True}, 'completed', False),  # pre-identity token needs the operator attestation
        (86400, {'s': POD, 't': True}, 'completed', False),
        (86400, {'s': {'pod': ''}}, 'completed', False),
        (86400, {'s': POD}, 'in_progress', False),
        (86400, {}, 'completed', False),
    ],
)
def test_quiesced_requires_completed_aged_identified_producers(age, tokens, status, quiesced):
    assert producers_quiesced(row(age, tokens, status=status), tokens, NOW) is quiesced


def test_quiesced_rejects_missing_or_naive_finish():
    assert not producers_quiesced({'status': 'completed', 'finished_at': None}, {'s': POD}, NOW)
    naive = datetime.fromtimestamp(NOW - 86400, timezone.utc).replace(tzinfo=None)
    assert not producers_quiesced({'status': 'completed', 'finished_at': naive}, {'s': POD}, NOW)


def test_kill_switch_restores_pod_restart_rule(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_LIVE_PRODUCER_GRACE_SECONDS', '0')
    assert not producers_quiesced(row(86400, {'s': POD}), {'s': POD}, NOW)


def test_seal_refusal_admits_an_aged_live_pod_capture_only_past_grace(monkeypatch):
    monkeypatch.setattr('utils.batch_pipeline.record_producer_proof.time.time', lambda: NOW)
    # No pod proof at all: before this change every live-pod token refused.
    assert seal_refusal(JOB, row(600, {'s': POD})) == 'upload_pending'
    assert seal_refusal(JOB, row(7200, {'s': POD})) is None
    assert seal_refusal(JOB, row(7200, {'s': True})) == 'upload_pending'
    # The failed-upload gate still applies first; repair must opt in.
    assert seal_refusal(JOB, row(7200, {'s': POD}, record_upload_failed=True)) == 'upload_failed'
    assert seal_refusal(JOB, row(7200, {'s': POD}, record_upload_failed=True), repair_upload_failed=True) is None
    # Privacy refusals are unchanged.
    assert seal_refusal(JOB, row(7200, {'s': POD}, deleted=True)) == 'privacy_refused'
