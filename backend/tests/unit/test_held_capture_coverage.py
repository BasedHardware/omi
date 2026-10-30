"""Held retries consult committed S1 proof without replacing cached-result custody."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest
from fastapi.responses import JSONResponse

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_capture_coverage_ledger import ledger, identity, rec, mapping, wav  # noqa: F401
from tests.unit.test_sync_cap_hold_recovery import state  # noqa: F401
from tests.unit.test_cap_hold_batch_admission import hook  # noqa: F401
from utils.batch_pipeline import cap_hold_admission as adapter, intake
from utils.batch_pipeline.held_coverage import HeldDecoder
from utils.capture import coverage
from utils.sync import cap_hold_recovery as recovery, held_coverage


def meta_for(key, *, start=0):
    return {
        'timestamp': 1760000000,
        'source': 'omi',
        'source_position_map': (mapping(key), start),
        'client_device_id': key.device_id,
        'recording_session_id': key.recording_session_id,
    }


def stored_piece(state, monkeypatch, tmp_path, key, prior=None):
    path = wav(tmp_path)
    meta = meta_for(key)
    recovery.cap_hold.metadata.return_value = meta
    name = 'piece.wav'
    state.row['piece_plan'] = {name: {'audio_path': 'retained-piece', 'seconds': 0.2}}
    if prior:
        state.row['piece_receipts'] = {name: prior}
    monkeypatch.setattr(
        recovery.cap_recovery_plan,
        'stage_piece',
        AsyncMock(
            return_value=(
                path,
                {
                    'source_position_map': meta['source_position_map'],
                    'recording_session_id': key.recording_session_id,
                },
            )
        ),
    )
    return name


@pytest.mark.parametrize('mode,skipped', [('serve', True), ('shadow', False), ('off', False), ('typo', False)])
async def test_stored_plan_rechecks_before_new_provider_intent(
    ledger,
    identity,
    state,
    monkeypatch,
    tmp_path,
    mode,
    skipped,
):
    uid, key = identity
    name = stored_piece(state, monkeypatch, tmp_path, key)
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    monkeypatch.setenv(coverage.FLAG, mode)
    assert await recovery._recover_row(uid, state.snapshot, state.row)
    receipt = state.row['piece_receipts'][name]
    assert bool(receipt.get('coverage_committed')) is skipped
    assert recovery.process_segment.call_count == int(not skipped)
    assert recovery.cap_recovery_pacing.reserve.call_count == int(not skipped)
    assert recovery.record_usage.call_count == int(not skipped)
    assert name in state.row['processed_paths']


async def test_partial_stored_piece_delegates_before_dispatch(ledger, identity, state, monkeypatch, tmp_path):
    uid, key = identity
    name = stored_piece(state, monkeypatch, tmp_path, key)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    recovery.record_usage.assert_not_called()
    children = state.row['piece_receipts'][name]['coverage_children']
    assert len(children) == 2 and name in state.row['processed_paths']
    assert [state.row['piece_plan'][child]['seconds'] for child in children] == [0.06, 0.06]
    assert not state.row.get('finalized')


async def test_cached_provider_result_reconciles_even_after_full_coverage(
    ledger,
    identity,
    state,
    monkeypatch,
    tmp_path,
):
    uid, key = identity
    prior = {
        'state': 'dispatched',
        'provider_result': 'encrypted-result',
        'attempt': 1,
        'provider': 'modulate',
        'model': 'velma-2',
    }
    name = stored_piece(state, monkeypatch, tmp_path, key, prior)
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    monkeypatch.setattr(recovery, 'piece_state', Mock(side_effect=AssertionError('cached result must reconcile')))
    assert await recovery._recover_row(uid, state.snapshot, state.row)
    recovery.process_segment.assert_called_once()
    recovery.cap_recovery_pacing.reserve.assert_not_called()
    assert state.row['piece_receipts'][name]['state'] == 'transcribed'
    assert not state.row['piece_receipts'][name].get('coverage_committed')


async def test_covered_receipt_checkpoint_failure_retains_piece(ledger, identity, state, monkeypatch, tmp_path):
    uid, key = identity
    stored_piece(state, monkeypatch, tmp_path, key)
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    recovery.cap_hold.checkpoint.return_value = False
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    recovery.process_segment.assert_not_called()
    recovery.record_usage.assert_not_called()
    assert not state.row.get('processed_paths') and not state.row.get('finalized')


@pytest.mark.parametrize('mode,count', [('serve', 0), ('shadow', 1), ('off', 1), ('typo', 1)])
def test_batch_held_custom_decode_full_proof_only(ledger, identity, monkeypatch, tmp_path, mode, count):
    uid, key = identity
    path = wav(tmp_path)
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    monkeypatch.setenv(coverage.FLAG, mode)
    decoder = HeldDecoder(uid, path, 1760000000, meta_for(key), legacy=adapter.wav_units)
    units = list(decoder(3600))
    assert len(units) == count
    assert decoder.all_covered is (mode == 'serve')
    if count:
        assert units == list(adapter.wav_units(path, 1760000000, 3600))


def test_partial_batch_decode_preserves_gap_clock_and_provenance(ledger, identity, tmp_path):
    uid, key = identity
    path = wav(tmp_path)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    decoder = HeldDecoder(uid, path, 1760000000, meta_for(key), legacy=adapter.wav_units)
    units = list(decoder(3600))
    assert [round(u.duration_seconds, 2) for u in units] == [0.06, 0.06]
    assert [u.capture_at for u in units] == [1760000000, 1760000000.14]
    assert [(u.coverage_runs[0]['start'], u.coverage_runs[0]['end']) for u in units] == [(0, 3), (7, 10)]
    assert not decoder.all_covered


def test_batch_partial_frame_edges_keep_exact_source_provenance(ledger, identity, tmp_path):
    uid, key = identity
    path = wav(tmp_path, 3)
    meta = meta_for(key, start=160)
    decoder = HeldDecoder(uid, path, 1760000000, meta, legacy=adapter.wav_units)
    units = list(decoder(3600))
    assert len(units) == 1
    assert [(r['start'], r['end'], r['sample_start']) for r in units[0].coverage_runs] == [(1, 3, 160)]
    assert units[0].duration_seconds == 0.06


def test_missing_piece_position_never_reuses_full_capture_map(ledger, identity, tmp_path):
    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    assert (
        held_coverage.proof(
            uid,
            wav(tmp_path),
            {
                'source_frame_map': mapping(key),
                'source_position_map': None,
            },
        )
        is None
    )


async def test_batch_admission_only_trusts_its_decoder_full_proof(ledger, identity, monkeypatch, tmp_path):
    uid, key = identity
    meta = meta_for(key)
    monkeypatch.setattr(adapter, 'eligible', lambda _: True)
    monkeypatch.setattr(recovery.cap_hold, 'metadata', lambda *a: meta)
    directory = SimpleNamespace(name=str(tmp_path), cleanup=Mock())
    monkeypatch.setattr(recovery.cap_hold, 'recovery_directory', lambda _: directory)

    def read(uid, row, path):
        with wave.open(path, 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(bytes(6400))

    monkeypatch.setattr(recovery.cap_hold, 'read_audio', read)
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))

    async def accept(**kwargs):
        assert not list(kwargs['decode'](3600))
        return JSONResponse(status_code=200, content={'outcome': 'success'})

    monkeypatch.setattr(intake, 'accept_upload', accept)
    assert (await adapter.admit_held(uid, SimpleNamespace(id='held'), {'state': 'held'})).outcome == 'covered'
    assert directory.cleanup.called


async def test_fully_covered_batch_hold_settles_without_new_reservation(hook, monkeypatch):
    monkeypatch.setattr(adapter, 'enabled_for', lambda *a: True)
    monkeypatch.setattr(adapter, 'admit_held', AsyncMock(return_value=adapter.HeldAdmission('covered')))
    reserve = Mock(side_effect=AssertionError('covered audio must not reserve batch spend'))
    monkeypatch.setattr(recovery.cap_hold_reservations, 'reserve', reserve)
    assert await recovery.recover_selected(str(__import__('uuid').UUID(int=11)), hook.snapshot)
    assert ('settle_and_erase',) in hook.events
    assert not any(event[0] == 'legacy' for event in hook.events)
    saved = [event[1] for event in hook.events if event[0] == 'save']
    assert saved == [{'state': 'completed', 'finalized': True, 'recovery_response': {}}]


def test_full_capture_metadata_uses_original_frame_positions(ledger, identity, tmp_path):
    uid, key = identity
    path = wav(tmp_path)
    meta = {'source_frame_map': mapping(key)}
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    decoder = HeldDecoder(uid, path, 1760000000, meta, legacy=adapter.wav_units)
    assert list(decoder(3600)) == [] and decoder.all_covered


def test_missing_or_malformed_proof_never_suppresses_audio(ledger, identity, tmp_path, monkeypatch):
    uid, key = identity
    path = wav(tmp_path)
    for meta in (
        {},
        {'source_position_map': [mapping(key)]},
        {'source_frame_map': {**mapping(key), 'offsets': [0, 0]}},
    ):
        decoder = HeldDecoder(uid, path, 1760000000, meta, legacy=adapter.wav_units)
        assert list(decoder(3600)) == list(adapter.wav_units(path, 1760000000, 3600))
        assert not decoder.all_covered
    monkeypatch.setattr(coverage, 'admit', Mock(side_effect=RuntimeError('offline ledger')))
    decoder = HeldDecoder(uid, path, 1760000000, meta_for(key), legacy=adapter.wav_units)
    assert list(decoder(3600)) and not decoder.all_covered


@pytest.mark.parametrize('mode,outcome', [('serve', 'skipped'), ('shadow', 'would_skip')])
def test_held_batch_metrics_count_covered_samples_once(ledger, identity, tmp_path, monkeypatch, mode, outcome):
    # Shadow measures a uid sample; this test measures the shadow arithmetic for a sampled uid.
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE_SHADOW_PERCENT', '100')
    from utils.capture.coverage_metrics import SECONDS

    uid, key = identity
    path = wav(tmp_path)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    monkeypatch.setenv(coverage.FLAG, mode)
    metric = SECONDS.labels(origin='batch', outcome=outcome)._value
    before = metric.get()
    list(HeldDecoder(uid, path, 1760000000, meta_for(key), legacy=adapter.wav_units)(3600))
    assert metric.get() - before == pytest.approx(0.08)


async def test_legacy_partial_metric_counts_only_covered_audio(ledger, identity, state, tmp_path, monkeypatch):
    from utils.capture.coverage_metrics import SECONDS

    uid, key = identity
    stored_piece(state, monkeypatch, tmp_path, key)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    metric = SECONDS.labels(origin='sync', outcome='skipped')._value
    before = metric.get()
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    assert metric.get() - before == pytest.approx(0.08)


def stage_children(monkeypatch, state):
    import json
    from pathlib import Path
    from utils.encryption import decrypt

    original_path = recovery.cap_recovery_plan.stage_piece.return_value[0]

    async def stage(uid, name, entry, directory, *args):
        if not entry.get('source_slice'):
            return original_path, {
                'source_position_map': recovery.cap_hold.metadata.return_value['source_position_map']
            }
        target = str(Path(directory.name) / name)
        with wave.open(original_path, 'rb') as source, wave.open(target, 'wb') as audio:
            audio.setparams(source.getparams())
            source.setpos(entry['source_slice']['start'])
            audio.writeframes(source.readframes(entry['source_slice']['frames']))
        return target, json.loads(decrypt(entry['metadata'], uid))

    monkeypatch.setattr(recovery.cap_recovery_plan, 'stage_piece', stage)


@pytest.mark.parametrize('ambiguous,floor', [(False, 1), (True, 2)])
async def test_children_transcribe_only_uncovered_and_inherit_attempt_ceiling(
    ledger,
    identity,
    state,
    monkeypatch,
    tmp_path,
    ambiguous,
    floor,
):
    uid, key = identity
    prior = {'state': 'dispatched', 'attempt': 1, 'dispatched_at': -1801} if ambiguous else None
    name = stored_piece(state, monkeypatch, tmp_path, key, prior)
    state.row['piece_plan'][name]['audio_path'] = 'retained-piece'
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    children = state.row['piece_receipts'][name]['coverage_children']
    assert all(state.row['piece_plan'][child]['coverage_attempt_floor'] == floor for child in children)
    stage_children(monkeypatch, state)
    assert await recovery._recover_row(uid, state.snapshot, state.row)
    assert recovery.process_segment.call_count == 2
    assert sum(
        call.kwargs['cap_recovery_checkpoint']['receipt']['seconds'] for call in recovery.process_segment.call_args_list
    ) == pytest.approx(0.12)
    assert all(
        call.kwargs['cap_recovery_checkpoint']['attempt'] == floor for call in recovery.process_segment.call_args_list
    )
    assert set(children) <= set(state.row['processed_paths']) and state.row['finalized']


async def test_split_checkpoint_failure_retries_same_child_identities_without_uploads(
    ledger,
    identity,
    state,
    monkeypatch,
    tmp_path,
):
    from copy import deepcopy

    uid, key = identity
    name = stored_piece(state, monkeypatch, tmp_path, key)
    state.row['piece_plan'][name]['audio_path'] = 'retained-piece'
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    upload = Mock(side_effect=AssertionError('child slices reuse existing encrypted custody'))
    monkeypatch.setattr(recovery.cap_hold, 'upload_held_audio', upload)
    before = deepcopy(state.row)
    state.row['piece_plan'][name]['audio_path'] = 'retained-piece'
    recovery.cap_hold.checkpoint.return_value = False
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    first = recovery.cap_hold.checkpoint.call_args.args[3]
    assert state.row == before and not state.row.get('processed_paths')
    recovery.cap_hold.checkpoint.return_value = True
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    second = [call.args[3] for call in recovery.cap_hold.checkpoint.call_args_list if 'piece_plan' in call.args[3]][-1]
    assert set(first['piece_plan']) == set(second['piece_plan'])
    assert first['piece_receipts'] == second['piece_receipts']
    assert set(first) == {'piece_plan', 'piece_receipts', 'processed_paths'}
    upload.assert_not_called()
    recovery.process_segment.assert_not_called()


async def test_child_failure_retains_hold_and_cannot_restart_attempt_budget(
    ledger,
    identity,
    state,
    monkeypatch,
    tmp_path,
):
    uid, key = identity
    prior = {'state': 'dispatched', 'attempt': 1, 'dispatched_at': -1801}
    name = stored_piece(state, monkeypatch, tmp_path, key, prior)
    state.row['piece_plan'][name]['audio_path'] = 'retained-piece'
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    stage_children(monkeypatch, state)

    def failed(*args, **kwargs):
        kwargs['deferred_outcome']['provider_called'] = True
        args[4].append('offline provider')
        return False

    recovery.process_segment.side_effect = failed
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    assert recovery.process_segment.call_count == 2
    # Cooldown retains accepted identities and makes no third paid attempt.
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    assert recovery.process_segment.call_count == 2
    monkeypatch.setattr(recovery.time, 'time', lambda: 2001)
    assert await recovery._recover_row(uid, state.snapshot, state.row)
    assert state.row['failed_reconciliation'] and state.row['retain_audio']
    assert recovery.process_segment.call_count == 2


async def test_split_capacity_failure_never_acknowledges_uncovered_audio(
    ledger,
    identity,
    state,
    monkeypatch,
    tmp_path,
):
    from utils.sync import held_piece_split as split

    uid, key = identity
    name = stored_piece(state, monkeypatch, tmp_path, key)
    state.row['piece_plan'][name]['audio_path'] = 'retained-piece'
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    monkeypatch.setattr(split, 'MAX_CHILDREN', 1)
    assert not await recovery._recover_row(uid, state.snapshot, state.row)
    assert not state.row.get('processed_paths') and not state.row.get('piece_receipts')
    recovery.process_segment.assert_not_called()


def test_child_source_slice_reuses_custody_and_verifies_content_hash(ledger, identity, tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    from utils.sync import cap_hold, held_piece_split as split

    uid, key = identity
    path = wav(tmp_path)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    decision = held_coverage.proof(uid, path, meta_for(key))
    entry = {'audio_path': 'frozen-source', 'seconds': 0.2}
    children = split.children(uid, 'hold', 'parent.wav', path, {}, entry, decision, 1)
    monkeypatch.setattr(cap_hold, '_read_single_audio', lambda uid, row, target: shutil.copyfile(path, target))
    for name, child in children.items():
        target = str(Path(tmp_path) / name)
        cap_hold.read_audio(uid, child, target)
        with wave.open(target, 'rb') as audio:
            assert audio.getnframes() == 960
    first = next(iter(children.values()))
    corrupt = {**first, 'source_slice': {**first['source_slice'], 'sha256': '0' * 64}}
    with pytest.raises(ValueError, match='source decode changed'):
        cap_hold.read_audio(uid, corrupt, str(Path(tmp_path) / 'corrupt.wav'))


@pytest.mark.parametrize('fence', ['current', 'lost'])
async def test_delegation_checkpoint_atomically_carries_children_or_writes_nothing(
    ledger,
    identity,
    state,
    tmp_path,
    monkeypatch,
    fence,
):
    from contextlib import nullcontext
    from copy import deepcopy
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync import cap_hold, held_piece_split as split

    uid, key = identity
    path = wav(tmp_path)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    decision = held_coverage.proof(uid, path, meta_for(key))
    row = {
        'lease_token': 'owner',
        'lease_until': 1000,
        'state': 'held',
        'piece_plan': {'parent.wav': {'audio_path': 'frozen', 'seconds': 0.2}},
    }
    root = ('users', uid, 'stt_cap_holds', 'hold')
    client = StrictFirestore({root: {**row, 'lease_token': 'other' if fence == 'lost' else 'owner'}})
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    snapshot = SimpleNamespace(id='hold', reference=client.document('/'.join(root)))
    before = deepcopy(client.rows)

    async def save(uid, snapshot, current, updates):
        applied = state.checkpoint(uid, snapshot.reference, current['lease_token'], updates)
        if applied:
            current.update(updates)
        return applied

    piece = ('parent.wav', path, {}, decision, 1)
    assert await split.delegate(uid, snapshot, row, piece, row['piece_plan'], {}, set(), save=save) is (
        fence == 'current'
    )
    if fence == 'lost':
        assert client.rows == before
    else:
        persisted = client.rows[root]
        assert len(persisted['piece_plan']) == 3
        assert persisted['processed_paths'] == ['parent.wav']
        assert len(persisted['piece_receipts']['parent.wav']['coverage_children']) == 2
        assert any(
            ref == root and 'piece_plan' in data and 'piece_receipts' in data
            for tx in client.transactions
            for ref, data in tx.updates
        )


@pytest.mark.parametrize('rate', [8000, 24000, 48000])
def test_native_rate_batch_trim_precedes_resampling_without_invented_provenance(
    ledger,
    identity,
    tmp_path,
    rate,
):
    from pathlib import Path

    uid, key = identity
    path = str(Path(tmp_path) / 'native.wav')
    # Distinct signs expose accidental inclusion of the committed middle.
    with wave.open(path, 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes((100).to_bytes(2, 'little', signed=True) * rate)
        audio.writeframes((-1000).to_bytes(2, 'little', signed=True) * rate)
        audio.writeframes((200).to_bytes(2, 'little', signed=True) * rate)
    frame_map = mapping(key, 3)
    frame_map['claim']['rate_hz'] = rate
    frame_map['offsets'] = [i * rate for i in range(4)]
    coverage.record(uid, key, rec('committed', 'live', (1, 2)))
    decoder = HeldDecoder(uid, path, 1760000000, {'source_frame_map': frame_map}, legacy=adapter.wav_units)
    units = list(decoder(3600))
    assert len(units) == 2 and not decoder.all_covered
    assert [unit.capture_at for unit in units] == [1760000000, 1760000002]
    assert all(not unit.coverage_runs for unit in units)
    import io

    for unit in units:
        with wave.open(io.BytesIO(unit.wav), 'rb') as audio:
            assert audio.getframerate() == 16000
            data = audio.readframes(audio.getnframes())
        assert all(int.from_bytes(data[i : i + 2], 'little', signed=True) >= 0 for i in range(0, len(data), 2))


def test_child_context_compacts_map_and_preserves_partial_edge_coordinates(ledger, identity, tmp_path):
    import json
    from utils.encryption import decrypt
    from utils.capture_evidence import source_coordinate
    from utils.sync import held_piece_split as split

    uid, key = identity
    path = wav(tmp_path, 3)
    meta = meta_for(key, start=160)
    coverage.record(uid, key, rec('committed', 'live', (2, 3)))
    decision = held_coverage.proof(uid, path, meta)
    children = split.children(uid, 'hold', 'parent.wav', path, {}, {'audio_path': 'frozen'}, decision, 1)
    assert len(children) == 2
    for child, (low, high) in zip(children.values(), decision.uncovered):
        compact, start = json.loads(decrypt(child['metadata'], uid))['source_position_map']
        assert len(compact['offsets']) < len(decision.mapping['offsets'])
        assert source_coordinate(compact, start) == source_coordinate(decision.mapping, low)
        assert source_coordinate(compact, start + high - low) == source_coordinate(decision.mapping, high)
