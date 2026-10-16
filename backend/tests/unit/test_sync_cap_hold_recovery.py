"""Recovery reaches real sync intake only after a current funded allowance."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest

from utils.sync import cap_hold_recovery as recovery
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def state(monkeypatch, tmp_path):
    checkpoint, renew = recovery.cap_hold.checkpoint, recovery.cap_hold.renew
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(recovery, 'run_blocking', immediate)
    monkeypatch.setattr(recovery.cap_hold, 'metadata', Mock(return_value={'timestamp': 1792152000, 'source': 'omi'}))
    monkeypatch.setattr(
        recovery.cap_hold, 'recovery_directory', Mock(return_value=SimpleNamespace(name=str(tmp_path), cleanup=Mock()))
    )
    monkeypatch.setattr(recovery.cap_hold, 'read_audio', Mock())
    monkeypatch.setattr(recovery.cap_hold, 'renew', Mock(return_value=True))
    monkeypatch.setattr(recovery.cap_hold, 'checkpoint', Mock(return_value=True))
    monkeypatch.setattr(recovery.users_db, 'get_user_transcription_preferences', Mock(return_value={'language': 'en'}))
    monkeypatch.setattr(recovery.users_db, 'get_user_private_cloud_sync_enabled', Mock(return_value=False))
    monkeypatch.setattr(recovery, 'sync_allowed', Mock(return_value=True))
    monkeypatch.setattr(recovery, 'get_hard_restriction_status', Mock(return_value=(False, None)))
    monkeypatch.setattr(recovery, 'is_daily_audio_ceiling_exceeded', Mock(return_value=False))

    def processed(*args, **kwargs):
        kwargs['deferred_outcome']['provider'] = 'modulate'
        return True

    monkeypatch.setattr(recovery, 'process_segment', Mock(side_effect=processed))
    monkeypatch.setattr(recovery, 'build_person_embeddings_cache', Mock(return_value={'known': 'embedding'}))
    monkeypatch.setattr(
        recovery,
        'prepare_audio',
        AsyncMock(side_effect=lambda uid, path, meta: ({path}, {}, {}, {})),
    )
    monkeypatch.setattr(recovery, 'finalize_recovered_sync_segment', Mock())
    monkeypatch.setattr(recovery, 'get_wav_duration', Mock(return_value=20))
    monkeypatch.setattr(recovery, 'record_usage', Mock())
    monkeypatch.setattr(recovery, 'get_prerecorded_service', Mock(return_value=('modulate', 'en', 'velma-2')))
    return SimpleNamespace(
        snapshot=SimpleNamespace(id='hold', reference=Mock()),
        row={'lease_token': 'owner-token', 'state': 'held'},
        checkpoint=checkpoint,
        renew=renew,
    )


async def test_reset_or_upgrade_reuses_sync_and_settles_stable_usage_key(state):
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_called_once()
    assert recovery.process_segment.call_args.kwargs['cap_recovery'] is True
    assert recovery.process_segment.call_args.kwargs['cap_recovery_service'] == ('modulate', 'en', 'velma-2')
    recovery.finalize_recovered_sync_segment.assert_called_once()
    usage = recovery.record_usage.call_args.kwargs
    assert usage['idempotency_key'] == 'cap-hold-hold-1792152000.wav'
    assert usage['transcription_seconds'] == 20
    assert usage['usage_metadata'] == {'funding': 'omi', 'provider': 'modulate', 'source': 'sync_v2'}
    assert state.row['processed_paths'] == ['1792152000.wav']
    assert state.row['finalized']
    assert state.row['piece_receipts']['1792152000.wav']['has_content']
    assert recovery.process_segment.call_args.args[8] == {'known': 'embedding'}


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


async def test_usage_failure_reuses_persisted_transcription_receipt(state):
    recovery.record_usage.side_effect = RuntimeError('synthetic usage unavailable')
    with pytest.raises(RuntimeError):
        await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert state.row['piece_receipts']['1792152000.wav']['has_content']
    recovery.finalize_recovered_sync_segment.assert_not_called()
    recovery.record_usage.side_effect = None
    # Already accepted content can settle even if no new provider work is allowed.
    recovery.sync_allowed.return_value = False
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_called_once()
    recovery.finalize_recovered_sync_segment.assert_called_once()
    assert recovery.record_usage.call_count == 2
    assert recovery.record_usage.call_args.kwargs['usage_metadata']['provider'] == 'modulate'
    assert recovery.record_usage.call_args_list[0] == recovery.record_usage.call_args_list[1]


async def test_geolocation_and_speaker_context_survive_hold(state):
    meta = recovery.cap_hold.metadata.return_value
    meta['geolocation'] = {'latitude': 10.7, 'longitude': 106.7}
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    args = recovery.process_segment.call_args
    assert args.args[8] == {'known': 'embedding'}
    assert args.kwargs['geolocation'].latitude == 10.7
    assert args.kwargs['geolocation'].longitude == 106.7


async def test_all_pieces_join_before_one_finalization(state):
    recovery.prepare_audio.side_effect = lambda uid, path, meta: (
        {path, path.replace('1792152000', '1792152020')},
        {},
        {},
        {},
    )

    def persist(path, uid, response, *args, **kwargs):
        response['updated_memories'].add('joined-conversation')
        response['_merged'] = {'joined-conversation': 'en'}
        return True

    recovery.process_segment.side_effect = persist
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert recovery.process_segment.call_count == 2
    recovery.finalize_recovered_sync_segment.assert_called_once()
    response = recovery.finalize_recovered_sync_segment.call_args.args[1]
    assert response['updated_memories'] == {'joined-conversation'}
    assert response['_merged'] == {'joined-conversation': 'en'}
    assert len(state.row['piece_receipts']) == 2


async def test_lost_checkpoint_fence_cannot_settle_or_finalize(state):
    recovery.cap_hold.checkpoint.return_value = False
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    recovery.record_usage.assert_not_called()
    recovery.finalize_recovered_sync_segment.assert_not_called()


@pytest.mark.parametrize('fault', ['save-error', 'lost-lease'])
async def test_ambiguous_dispatch_never_repeats_stt_or_ingestion_on_new_claim(state, monkeypatch, fault):
    clock = [100.0]
    key = ('users', 'synthetic', 'stt_cap_holds', 'hold')
    client = StrictFirestore({key: {'state': 'held', 'lease_until': 0, 'audio_path': 'retained'}})
    ref = client.document('/'.join(key))
    state.snapshot.reference = ref
    monkeypatch.setattr(recovery.cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(recovery.cap_hold, 'external_write_fence', lambda _: nullcontext())
    monkeypatch.setattr(recovery.cap_hold.time, 'time', lambda: clock[0])
    monkeypatch.setattr(recovery.cap_hold, 'renew', state.renew)
    fail_save = [False]

    def checkpoint(*args):
        if fail_save[0]:
            raise RuntimeError('transcript checkpoint unavailable after ingestion')
        return state.checkpoint(*args)

    monkeypatch.setattr(recovery.cap_hold, 'checkpoint', checkpoint)
    ingested = Mock()

    def dispatch_and_ingest(*args, **kwargs):
        intent = client.rows[key]['piece_receipts']['1792152000.wav']
        assert intent == {'state': 'dispatched', 'provider': 'modulate', 'model': 'velma-2', 'funding': 'omi'}
        assert kwargs['cap_recovery_service'] == ('modulate', 'en', 'velma-2')
        ingested()
        if fault == 'save-error':
            fail_save[0] = True
        else:
            clock[0] = 2001
            assert recovery.cap_hold.claim('synthetic', ref, clock[0])
        return True

    recovery.process_segment.side_effect = dispatch_and_ingest
    row = recovery.cap_hold.claim('synthetic', ref, clock[0])
    if fault == 'save-error':
        with pytest.raises(RuntimeError, match='checkpoint unavailable'):
            await recovery._recover_row('synthetic', state.snapshot, row)
    else:
        assert not await recovery._recover_row('synthetic', state.snapshot, row)
    assert client.rows[key]['piece_receipts']['1792152000.wav']['state'] == 'dispatched'
    assert client.rows[key]['audio_path'] == 'retained'
    fail_save[0] = False
    # A real new fenced claim loads only durable state, not the prior local row.
    clock[0] = 4002
    retry = recovery.cap_hold.claim('synthetic', ref, clock[0])
    assert retry['lease_token'] != row['lease_token']
    assert not await recovery._recover_row('synthetic', state.snapshot, retry)
    recovery.process_segment.assert_called_once()
    ingested.assert_called_once()
    recovery.prepare_audio.assert_awaited_once()
    recovery.record_usage.assert_not_called()
    recovery.finalize_recovered_sync_segment.assert_not_called()


@pytest.mark.parametrize('restriction', ['hard', 'daily'])
async def test_recovery_cannot_bypass_current_abuse_restrictions(state, restriction):
    if restriction == 'hard':
        recovery.get_hard_restriction_status.return_value = (True, 60)
    else:
        recovery.is_daily_audio_ceiling_exceeded.return_value = True
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    recovery.cap_hold.read_audio.assert_not_called()


async def test_lost_completion_lease_cannot_settle_or_erase_audio(state, monkeypatch):
    state.snapshot.to_dict = Mock(return_value={'state': 'held'})
    monkeypatch.setattr(recovery.cap_hold, 'recovery_cooldown', Mock(return_value=True))
    monkeypatch.setattr(recovery.cap_hold, 'pending_holds', Mock(return_value=[state.snapshot]))
    monkeypatch.setattr(recovery.cap_hold, 'claim', Mock(return_value=state.row))
    monkeypatch.setattr(recovery.cap_hold, 'release', Mock())
    monkeypatch.setattr(recovery, '_recover_row', AsyncMock(return_value=True))
    monkeypatch.setattr(recovery, '_settle_and_erase', Mock())
    recovery.cap_hold.checkpoint.return_value = False
    await recovery.recover('synthetic')
    recovery._settle_and_erase.assert_not_called()
    recovery.cap_hold.release.assert_called_once_with('synthetic', state.snapshot.reference, 'owner-token')
