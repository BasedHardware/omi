"""Heavy-owner isolation at admission: no live services or account identities."""

from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from config.policy.batch import BatchUnitPolicy
from config.policy import ramp
from database import batch_ramp
from utils.batch_pipeline import intake
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


def policy(percent=5):
    return BatchUnitPolicy(
        batch_enabled=True, batch_percent=percent, live_admission_enabled=True, live_record_enabled=True
    )


def rows(count, **fields):
    return [dict(enqueued_at=100000, state='pending', duration_seconds=10, **fields) for _ in range(count)]


def test_boundaries_and_ship_on_kill_switch():
    assert ramp.exclusion_reason(ramp.owner_load(rows(30), [], 100000)) is None
    assert ramp.exclusion_reason(ramp.owner_load(rows(31), [], 100000)) == 'open_backlog'
    for flags in ({}, {ramp.SWITCH: 'on'}, {ramp.SWITCH: 'invalid'}):
        assert ramp.exclusion_enabled(5, flags)
    assert not ramp.exclusion_enabled(5, {ramp.SWITCH: ' OFF '})
    for percent in (0, 100):
        assert not ramp.exclusion_enabled(percent, {})


def test_run24_one_twenty_hour_pending_upload_is_excluded():
    pending = [{'payload': {'audio_start_seconds': 0, 'audio_end_seconds': 20 * 3600}}]
    assert ramp.exclusion_reason(ramp.owner_load([], pending, 100000)) == 'recording_hours'
    pending[0]['payload']['audio_end_seconds'] = 6 * 3600
    assert ramp.exclusion_reason(ramp.owner_load([], pending, 100000)) is None


def test_run25_42_open_excludes_but_completed_quarantined_old_do_not():
    assert ramp.exclusion_reason(ramp.owner_load(rows(42), [], 100000)) == 'open_backlog'
    closed = rows(20, client_status='completed')
    quarantined = [dict(row, state='quarantined') for row in rows(20)]
    old = [dict(row, enqueued_at=1) for row in rows(20)]
    assert ramp.exclusion_reason(ramp.owner_load(closed + quarantined + old, [], 100000)) is None


def test_pending_count_unknown_audio_and_saturation_fail_closed():
    assert ramp.exclusion_reason(ramp.owner_load([], [{}] * 31, 100000)) == 'open_backlog'
    assert ramp.exclusion_reason(ramp.owner_load([], [{}], 100000)) == 'load_unavailable'
    assert (
        ramp.exclusion_reason(ramp.owner_load(rows(ramp.READ_LIMIT, client_status='completed'), [], 100000))
        == 'load_unavailable'
    )
    for bad in (float('nan'), float('inf'), -1, True):
        assert ramp.audio_span({'audio_start_seconds': 0, 'audio_end_seconds': bad}) is None


def test_incoming_long_upload_counts_before_admission():
    assert ramp.exclusion_reason(ramp.owner_load([], [], 100000, incoming_audio_seconds=72000)) == 'recording_hours'


def test_exclusion_changes_only_new_dispatch_fields_and_emits_metric(monkeypatch):
    monkeypatch.delenv(ramp.SWITCH, raising=False)
    original = replace(policy(), batch_allowlisted=True, retire_percent=5, live_stt_retired=True)
    before = batch_ramp.EXCLUDED.labels(reason='open_backlog')._value.get()
    with patch.object(
        batch_ramp, 'read_owner_load', return_value={'open_backlog': 42, 'recording_seconds': 0, 'complete': True}
    ):
        filtered = batch_ramp.ramp_admission_policy('synthetic-owner', original)
    assert not filtered.batch_enabled and not filtered.batch_allowlisted
    assert not filtered.live_record_enabled and not filtered.live_stt_retired
    assert filtered.live_admission_enabled
    assert batch_ramp.EXCLUDED.labels(reason='open_backlog')._value.get() == before + 1
    assert original.batch_enabled


def test_reads_fail_to_legacy_and_disabled_full_rollout_do_no_reads(monkeypatch):
    monkeypatch.delenv(ramp.SWITCH, raising=False)
    with patch.object(batch_ramp, 'read_owner_load', side_effect=RuntimeError('private error')) as read:
        assert not batch_ramp.ramp_admission_policy('synthetic-owner', policy()).batch_enabled
        read.reset_mock()
        for original in (policy(100), replace(policy(), batch_enabled=False, live_record_enabled=False)):
            assert batch_ramp.ramp_admission_policy('synthetic-owner', original) is original
        monkeypatch.setenv(ramp.SWITCH, 'off')
        assert batch_ramp.ramp_admission_policy('synthetic-owner', policy()).batch_enabled
        read.assert_not_called()


def test_metadata_reads_are_bounded_projected_and_stage_qualified():
    client = Mock()
    query = client.collection.return_value
    query.where.return_value = query
    query.select.return_value = query
    query.limit.return_value = query
    query.stream.return_value = []
    assert batch_ramp.read_owner_load('synthetic-owner', firestore_client=client, stage='dev', now=100000)['complete']
    assert [call.args[0] for call in client.collection.call_args_list] == [
        'batch_pipeline_dev_jobs',
        'sync_backfill_pending_dev',
    ]
    assert all(call.args == (ramp.READ_LIMIT,) for call in query.limit.call_args_list)
    assert query.select.call_count == 2
    with pytest.raises(ValueError):
        batch_ramp.read_owner_load('synthetic-owner', firestore_client=client, stage='prod-typo')


@pytest.mark.asyncio
async def test_excluded_new_upload_uses_legacy_without_artifacts_but_prior_batch_keeps_custody(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *args: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    artifacts = Mock(side_effect=AssertionError('excluded upload must not stage batch artifacts'))
    monkeypatch.setattr(intake, 'artifacts_for', artifacts)
    arguments = dict(
        uid='synthetic-owner',
        job_id='new',
        content_id='content',
        paths=['retained.bin'],
        lane='backfill',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        policy=replace(policy(), batch_enabled=False, live_record_enabled=False),
    )
    assert await intake.accept_upload(**arguments) is None
    assert not store.rows
    artifacts.assert_not_called()
    store.rows['content', 'synthetic-owner/content'] = {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_prior'}
    # Prior custody cannot be translated to None/legacy even if its status read
    # finds a privacy/persistence problem (the existing intake fence returns 409).
    response = await intake.accept_upload(**arguments)
    assert response is not None and response.status_code == 409
