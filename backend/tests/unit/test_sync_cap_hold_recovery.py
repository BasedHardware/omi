"""Recovery reaches real sync intake only after a current funded allowance."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.sync import cap_hold_recovery as recovery


@pytest.fixture
def state(monkeypatch, tmp_path):
    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(recovery, 'run_blocking', immediate)
    monkeypatch.setattr(recovery.cap_hold, 'metadata', Mock(return_value={'timestamp': 1792152000, 'source': 'omi'}))
    monkeypatch.setattr(
        recovery.cap_hold, 'recovery_directory', Mock(return_value=SimpleNamespace(name=str(tmp_path), cleanup=Mock()))
    )
    monkeypatch.setattr(recovery.cap_hold, 'read_audio', Mock())
    monkeypatch.setattr(recovery.cap_hold, 'renew', Mock(return_value=True))
    monkeypatch.setattr(recovery.users_db, 'get_user_transcription_preferences', Mock(return_value={'language': 'en'}))
    monkeypatch.setattr(recovery.users_db, 'get_user_private_cloud_sync_enabled', Mock(return_value=False))
    monkeypatch.setattr(recovery, 'sync_allowed', Mock(return_value=True))
    monkeypatch.setattr(recovery, 'process_segment', Mock(return_value=True))
    monkeypatch.setattr(recovery, 'finalize_recovered_sync_segment', Mock())
    monkeypatch.setattr(recovery, 'get_wav_duration', Mock(return_value=20))
    monkeypatch.setattr(recovery, 'record_usage', Mock())
    return SimpleNamespace(
        snapshot=SimpleNamespace(id='hold', reference=Mock()),
        row={'lease_token': 'owner-token', 'state': 'held'},
    )


async def test_reset_or_upgrade_reuses_sync_and_settles_stable_usage_key(state):
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_called_once()
    assert recovery.process_segment.call_args.kwargs['cap_recovery'] is True
    recovery.finalize_recovered_sync_segment.assert_called_once()
    usage = recovery.record_usage.call_args.kwargs
    assert usage['idempotency_key'] == 'cap-hold-hold-1792152000.wav'
    assert usage['transcription_seconds'] == 20
    state.snapshot.reference.update.assert_called_once()


async def test_execution_denial_keeps_checkpoint_and_audio_without_stt(state, monkeypatch):
    recovery.sync_allowed.return_value = False
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    state.snapshot.reference.update.assert_not_called()
    recovery.record_usage.assert_not_called()


async def test_lost_hold_lease_cannot_dispatch_or_acknowledge(state):
    recovery.cap_hold.renew.return_value = False
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    state.snapshot.reference.update.assert_not_called()


async def test_segment_recheck_refusal_does_not_consume_the_hold(state):
    def denied(*args, **kwargs):
        kwargs['deferred_outcome']['cap_held'] = True
        return False

    recovery.process_segment.side_effect = denied
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    state.snapshot.reference.update.assert_not_called()
    recovery.record_usage.assert_not_called()


async def test_partial_recovery_resumes_only_unprocessed_pieces(state):
    state.row['processed_paths'] = ['1792152000.wav']
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    recovery.record_usage.assert_not_called()


async def test_persistence_failure_keeps_audio_and_releases_local_staging(state):
    recovery.process_segment.side_effect = RuntimeError('synthetic persistence failure')
    with pytest.raises(RuntimeError):
        await recovery._recover_row('synthetic', state.snapshot, state.row)
    state.snapshot.reference.update.assert_not_called()
    recovery.cap_hold.recovery_directory.return_value.cleanup.assert_called_once()
