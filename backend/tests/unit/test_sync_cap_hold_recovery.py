"""Recovery reaches real sync intake only after a current funded allowance."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest

from utils.sync import cap_hold_recovery as recovery
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def state(monkeypatch, tmp_path):
    checkpoint, renew = recovery.cap_hold.checkpoint, recovery.cap_hold.renew
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(recovery.cap_hold, 'ensure_summary', lambda uid: {'version': 2, 'seconds': 0, 'count': 0})

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(recovery, 'run_blocking', immediate)
    monkeypatch.setattr(recovery.cap_recovery_plan, 'run_blocking', immediate)
    monkeypatch.setattr(
        recovery.cap_recovery_plan, 'persist_piece', Mock(return_value={'audio_path': 'retained-piece', 'seconds': 20})
    )
    monkeypatch.setattr(recovery.sync_cap_recovery, 'ingested_piece', Mock(return_value=None))
    monkeypatch.setattr(recovery.time, 'time', lambda: 100.0)
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
        kwargs['deferred_outcome'].update(provider='modulate', provider_called=True)
        return True

    monkeypatch.setattr(recovery, 'process_segment', Mock(side_effect=processed))
    monkeypatch.setattr(recovery, 'build_person_embeddings_cache', Mock(return_value={'known': 'embedding'}))
    monkeypatch.setattr(
        recovery,
        'prepare_audio',
        AsyncMock(side_effect=lambda uid, path, meta: ({path}, {}, {}, {})),
    )
    monkeypatch.setattr(recovery, 'finalize_recovered_sync_segment', Mock())
    monkeypatch.setattr(recovery, 'record_usage', Mock())
    monkeypatch.setattr(recovery, 'get_prerecorded_service', Mock(return_value=('modulate', 'en', 'velma-2')))
    row = {'lease_token': 'owner-token', 'state': 'held'}
    reference = Mock()
    reference.get.return_value.to_dict.side_effect = lambda: dict(row)
    return SimpleNamespace(
        snapshot=SimpleNamespace(id='hold', reference=reference),
        row=row,
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
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert not state.row['piece_receipts']
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
        kwargs['deferred_outcome']['provider_called'] = True
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
async def test_atomic_ingest_proof_recovers_save_error_or_lost_lease(state, monkeypatch, fault):
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
        assert intent['state'] == 'dispatched' and intent['attempt'] == 1
        kwargs['deferred_outcome']['provider_called'] = True
        client.rows[key]['piece_ingests'] = {
            '1792152000.wav': {**intent, 'state': 'transcribed', 'has_content': True, 'response': {}}
        }
        assert kwargs['cap_recovery_service'] == ('modulate', 'en', 'velma-2')
        ingested()
        if fault == 'save-error':
            fail_save[0] = True
        else:
            clock[0] = 2001
            assert recovery.cap_hold.claim('synthetic', ref, clock[0])
        return True

    recovery.sync_cap_recovery.ingested_piece.side_effect = (
        lambda uid, hold, piece: client.rows[key].get('piece_ingests', {}).get(piece)
    )
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
    assert await recovery._recover_row('synthetic', state.snapshot, retry)
    assert retry['retain_audio']
    recovery.process_segment.assert_called_once()
    ingested.assert_called_once()
    recovery.prepare_audio.assert_awaited_once()
    recovery.record_usage.assert_called_once()
    recovery.finalize_recovered_sync_segment.assert_called_once()


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
    await recovery.recover_selected('synthetic', state.snapshot)
    recovery._settle_and_erase.assert_not_called()
    recovery.cap_hold.release.assert_called_once_with('synthetic', state.snapshot.reference, 'owner-token')


@pytest.mark.parametrize('reason', ['provider_select', 'cap_held'])
async def test_known_noncall_clears_intent_and_next_claim_retries(state, reason):
    normal = recovery.process_segment.side_effect

    def noncall(*args, **kwargs):
        kwargs['deferred_outcome']['provider_called'] = False
        if reason == 'cap_held':
            kwargs['deferred_outcome']['cap_held'] = True
        else:
            args[4].append('provider_select')
        return False

    recovery.process_segment.side_effect = noncall
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert not state.row['piece_receipts']
    recovery.process_segment.side_effect = normal
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert recovery.process_segment.call_count == 2
    recovery.prepare_audio.assert_awaited_once()  # Frozen piece, no changed VAD plan.


async def test_ambiguous_piece_redispatches_only_once_then_retains_audio_and_finishes_sibling(state, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(recovery.time, 'time', lambda: clock[0])
    recovery.prepare_audio.side_effect = lambda uid, path, meta: (
        {path, path.replace('1792152000', '1792152020')},
        {},
        {},
        {},
    )
    attempts = []

    def process(path, uid, response, lock, errors, *args, **kwargs):
        kwargs['deferred_outcome']['provider_called'] = True
        if '1792152000' in path:
            attempts.append(kwargs['cap_recovery_checkpoint']['attempt'])
            errors.append('ambiguous_provider_result')
            return False
        response['updated_memories'].add('sibling')
        response['_merged'] = {'sibling': 'en'}
        return True

    recovery.process_segment.side_effect = process
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert attempts == [1]
    recovery.finalize_recovered_sync_segment.assert_called_once()
    assert recovery.finalize_recovered_sync_segment.call_args.args[1]['updated_memories'] == {'sibling'}
    # Still cooling down: neither provider nor sibling finalization repeats.
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert attempts == [1]
    clock[0] = 1901
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert attempts == [1, 2]
    clock[0] = 3702
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    failed = state.row['piece_receipts']['1792152000.wav']
    assert failed['state'] == 'failed_reconciliation' and failed['attempt'] == 2
    assert state.row['retain_audio'] and state.row['failed_reconciliation']
    recovery.finalize_recovered_sync_segment.assert_called_once()
    recovery.record_usage.assert_called_once()
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert attempts == [1, 2]
    monkeypatch.setattr(recovery, '_erase', Mock())
    monkeypatch.setattr(recovery.sync_cap_holds, 'settle_hold', Mock())
    recovery._settle_and_erase('synthetic', state.snapshot, state.row)
    recovery._erase.assert_not_called()
    recovery.sync_cap_holds.settle_hold.assert_not_called()  # Never claim failed audio completed.


async def test_ingested_ambiguity_finalizes_without_provider_and_settles_once(state):
    state.row['piece_plan'] = {'1792152000.wav': {'audio_path': 'retained-piece', 'seconds': 20}}
    state.row['piece_receipts'] = {'1792152000.wav': {'state': 'dispatched', 'attempt': 1, 'dispatched_at': -1801}}
    recovery.sync_cap_recovery.ingested_piece.return_value = {
        'state': 'transcribed',
        'has_content': True,
        'seconds': 20,
        'response': {'updated_memories': ['ingested'], '_merged': {'ingested': 'en'}},
        'usage_metadata': {'funding': 'omi', 'provider': 'modulate', 'source': 'sync_v2'},
    }
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    recovery.cap_hold.read_audio.assert_not_called()
    recovery.prepare_audio.assert_not_awaited()
    recovery.finalize_recovered_sync_segment.assert_called_once()
    assert state.row['retain_audio']
    assert recovery.record_usage.call_args.kwargs['idempotency_key'] == 'cap-hold-hold-1792152000.wav'


async def test_second_attempt_noncall_reverts_prior_intent_without_spending_retry(state):
    prior = {'state': 'dispatched', 'attempt': 1, 'dispatched_at': -1801}
    state.row.update(
        piece_plan={'1792152000.wav': {'audio_path': 'piece', 'seconds': 20}}, piece_receipts={'1792152000.wav': prior}
    )

    def noncall(*args, **kwargs):
        kwargs['deferred_outcome'].update(provider_called=False, cap_held=True)
        return False

    recovery.process_segment.side_effect = noncall
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert state.row['piece_receipts']['1792152000.wav'] == prior


async def test_flag_off_recovery_has_no_io(state, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    await recovery.recover('synthetic')
    recovery.cap_hold.metadata.assert_not_called()
    recovery.process_segment.assert_not_called()


async def test_not_ingested_piece_gets_one_successful_redispatch_with_stable_usage_key(state, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(recovery.time, 'time', lambda: clock[0])
    attempts = []

    def process(*args, **kwargs):
        attempt = kwargs['cap_recovery_checkpoint']['attempt']
        attempts.append(attempt)
        kwargs['deferred_outcome']['provider_called'] = True
        if attempt == 1:
            args[4].append('provider_reply_unknown')
            return False
        args[2]['new_memories'].add('recovered')
        return True

    recovery.process_segment.side_effect = process
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    clock[0] = 1901
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert attempts == [1, 2]
    assert state.row['piece_receipts']['1792152000.wav']['state'] == 'transcribed'
    recovery.record_usage.assert_called_once()
    assert recovery.record_usage.call_args.kwargs['idempotency_key'] == 'cap-hold-hold-1792152000.wav'


async def test_cap_denial_after_provider_call_remains_ambiguous(state):
    def called_then_denied(*args, **kwargs):
        kwargs['deferred_outcome'].update(provider_called=True, cap_held=True)
        return False

    recovery.process_segment.side_effect = called_then_denied
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert state.row['piece_receipts']['1792152000.wav']['state'] == 'dispatched'


def test_retained_manifest_cannot_dispatch_and_does_not_starve_pending_holds(state, monkeypatch):
    key = ('users', 'synthetic', 'stt_cap_holds', 'hold')
    client = StrictFirestore({key: {'state': 'retained', 'lease_token': 'owner', 'lease_until': 0}})
    ref = client.document('/'.join(key))
    monkeypatch.setattr(recovery.cap_hold, 'get_firestore_client', lambda: client)
    recovery.cap_hold.release('synthetic', ref, 'owner')
    assert client.rows[key]['next_attempt_at'] == 253402300799
    monkeypatch.setattr(recovery.cap_hold, 'external_write_fence', lambda _: nullcontext())
    assert recovery.cap_hold.claim('synthetic', ref, 2000) is None


def test_reconciled_retention_waits_for_ledger_settlement_and_retries_failure(state, monkeypatch):
    state.row.update(state='completed', retain_audio=True)
    recovery.cap_hold.metadata.return_value['content_id'] = 'content'
    settle = Mock(side_effect=RuntimeError('synthetic settlement failure'))
    monkeypatch.setattr(recovery.sync_cap_holds, 'settle_hold', settle)
    monkeypatch.setattr(recovery, '_erase', Mock())
    with pytest.raises(RuntimeError):
        recovery._settle_and_erase('synthetic', state.snapshot, state.row)
    state.snapshot.reference.update.assert_not_called()
    assert state.row['state'] == 'completed'
    settle.side_effect = None
    settle.return_value = True
    recovery._settle_and_erase('synthetic', state.snapshot, state.row)
    assert state.snapshot.reference.update.call_args.args[0]['state'] == 'retained'
    recovery._erase.assert_not_called()


async def test_ladder_only_recovery_waits_for_budget_reset_then_releases(state, monkeypatch):
    from utils import stt_cap_dispatch, ladder_v1

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    snapshot = {'budget_percent': 100, 'budget_units': 100, 'used_units': 100}
    monkeypatch.setattr(ladder_v1, 'budget_snapshot', lambda *a, **k: snapshot)
    monkeypatch.setattr(recovery, 'sync_allowed', stt_cap_dispatch.sync_allowed)
    assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    snapshot.update(budget_percent=0, used_units=0)
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    recovery.process_segment.assert_called_once()
    assert state.row['finalized'] is True


async def test_silent_live_capture_settles_without_provider_or_ambiguous_receipt(state, monkeypatch):
    from utils.sync import cap_recovery_audio

    meta = {
        'origin': 'live',
        'full_capture': True,
        'timestamp': 100,
        'source': 'phone',
        'channel': 0,
        'live_storage_month': '2026-10',
    }
    monkeypatch.setattr(recovery.cap_hold, 'metadata', Mock(return_value=meta))
    monkeypatch.setattr(recovery, 'prepare_audio', cap_recovery_audio.prepare)
    monkeypatch.setattr(cap_recovery_audio, 'retrieve_vad_segments', Mock())  # Real branch, no speech windows.

    async def leaf(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap_recovery_audio, 'run_blocking', leaf)
    assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert state.row['piece_plan'] == {}
    assert not state.row['failed_reconciliation']
    recovery.process_segment.assert_not_called()
    assert recovery.cap_hold.remaining_seconds({**state.row, 'seconds': 60}) == 0


async def test_legacy_wake_only_resumes_an_explicit_backlog_runner(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    runner = AsyncMock()
    monkeypatch.setattr(recovery, '_backlog_runner', runner)
    await recovery.recover('synthetic')
    runner.assert_awaited_once_with('synthetic')


async def test_owner_budget_stops_before_second_frozen_piece_and_resumes(state, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(recovery.cap_work_budget.time, 'monotonic', lambda: now[0])
    state.row['piece_plan'] = {
        'a.wav': {'audio_path': 'source-a', 'seconds': 20},
        'b.wav': {'audio_path': 'source-b', 'seconds': 20},
    }
    original = recovery.process_segment.side_effect

    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        now[0] += 901
        return result

    recovery.process_segment.side_effect = slow
    with recovery.cap_work_budget.visit(900):
        assert not await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert recovery.process_segment.call_count == 1
    assert state.row['processed_paths'] == ['a.wav'] and not state.row.get('finalized')
    with recovery.cap_work_budget.visit(900):
        assert await recovery._recover_row('synthetic', state.snapshot, state.row)
    assert recovery.process_segment.call_count == 2 and state.row['finalized']


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize(
    'origin,lanes,selected',
    [
        ('live', 'live', True),
        ('live', 'sync,batch', False),
        ('sync', 'live', False),
        ('sync', 'sync', True),
        ('batch', 'batch', True),
        ('unknown', 'live,sync,batch', False),
        (None, 'live,sync,batch', False),
        ('legacy', 'live', False),
        ('legacy', 'sync', True),
    ],
)
async def test_recovery_keeps_original_origin_through_real_dispatch(
    state, monkeypatch, ladder, origin, lanes, selected
):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    meta = {'timestamp': 1792152000, 'source': 'omi', 'sync_lane': 'fresh'}
    if origin != 'legacy':
        meta['origin'] = origin
    recovery.cap_hold.metadata.return_value = meta
    # The plan/codec/storage contract has separate coverage; retain a frozen
    # piece here to isolate original-lane dispatch through the real coordinator.
    state.row['piece_plan'] = {'1792152000.wav': {'seconds': 20}}
    assert await recovery._recover_row('synthetic', state.snapshot, state.row) is selected
    if selected:
        lane = 'sync' if origin == 'legacy' else origin
        assert recovery.process_segment.call_args.kwargs['cap_dispatch_lane'] == lane
        recovery.sync_allowed.assert_called_with('synthetic', lane=lane)
        assert meta.get('origin') == (None if origin == 'legacy' else origin)
    else:
        recovery.cap_hold.read_audio.assert_not_called()
        recovery.process_segment.assert_not_called()
        recovery.record_usage.assert_not_called()


async def test_excluded_owner_does_not_read_hold_metadata_or_claim(state, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:other')
    state.snapshot.to_dict = lambda: state.row
    claim = Mock(side_effect=AssertionError('excluded recovery claim'))
    monkeypatch.setattr(recovery.cap_hold, 'claim', claim)
    assert not await recovery.recover_selected('synthetic', state.snapshot)
    recovery.cap_hold.metadata.assert_not_called()
    claim.assert_not_called()
