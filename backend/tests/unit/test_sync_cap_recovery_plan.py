"""Immutable pieces retain exact bytes and lineage across changing VAD/coverage."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import wave

import pytest

from utils.sync import cap_recovery_plan as plan


@pytest.mark.parametrize('upload_fails', [False, True])
async def test_piece_plan_is_durable_before_dispatch_and_replays_frozen_audio(tmp_path, monkeypatch, upload_fails):
    async def leaf(pool, fn, *args):
        return fn(*args)

    monkeypatch.setattr(plan, 'run_blocking', leaf)
    blobs = {}

    def upload(uid, path, identity, context):
        if upload_fails:
            raise RuntimeError('synthetic storage failure')
        blob = f'chunks/{uid}/cap-held/{identity}'
        with open(path, 'rb') as source:
            blobs[blob] = source.read()
        return {'audio_path': blob, 'metadata': json.dumps(context)}

    monkeypatch.setattr(plan.cap_hold, 'upload_held_audio', upload)
    monkeypatch.setattr(plan.cap_hold, 'read_audio', lambda uid, row, path: None)
    piece = tmp_path / '1792152000.wav'
    with wave.open(str(piece), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x01\x02' * 1600)
    original = piece.read_bytes()
    context = {
        'target_conversation_id': 'bound',
        'source_position_map': ({'claim': 'synthetic'}, 100),
        'lineage_binding': 'bound',
    }
    prepare = AsyncMock(
        return_value=(
            {str(piece)},
            {str(piece): context['source_position_map']},
            {str(piece): 'bound'},
            {str(piece): 'bound'},
        )
    )
    row = {'audio_path': 'original-held-audio'}

    async def save(uid, snapshot, stored, update):
        stored.update(update)
        return True

    directory, snapshot = SimpleNamespace(name=str(tmp_path)), SimpleNamespace(id='hold')
    if upload_fails:
        with pytest.raises(RuntimeError):
            await plan.ensure_plan('synthetic', snapshot, row, {'timestamp': 1}, directory, prepare, save)
        assert 'piece_plan' not in row and row['audio_path'] == 'original-held-audio'
        return
    pieces, _, _ = await plan.ensure_plan('synthetic', snapshot, row, {'timestamp': 1}, directory, prepare, save)
    assert row['piece_plan'] == pieces
    # Later code/config may change VAD and WAL overlap. Neither may redefine a retry.
    prepare.side_effect = AssertionError('must not prepare the source again')
    piece.write_bytes(b'changed-local-source')
    monkeypatch.setattr(
        plan.cap_hold, 'read_audio', lambda uid, item, path: piece.write_bytes(blobs[item['audio_path']])
    )
    monkeypatch.setattr(plan.cap_hold, 'metadata', lambda uid, item: json.loads(item['metadata']))
    replay, locals_, contexts = await plan.ensure_plan(
        'synthetic', snapshot, row, {'timestamp': 1}, directory, prepare, save
    )
    path, restored_context = await plan.stage_piece(
        'synthetic', piece.name, replay[piece.name], directory, locals_, contexts
    )
    assert path == str(piece) and piece.read_bytes() == original
    assert restored_context == context
    prepare.assert_awaited_once()


async def test_v4_plan_freezes_source_slices_without_second_audio_upload(tmp_path, monkeypatch):
    import shutil
    from utils.sync import cap_hold, live_cap_codec as codec
    from utils.encryption import decrypt

    async def leaf(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(plan, 'run_blocking', leaf)
    original = tmp_path / 'original.opus'
    codec.encode(str(original), b'\x01\x02' * 16000, 16000)
    reads = []

    def fetch(uid, row, path):
        reads.append(row['audio_path'])
        shutil.copyfile(original, path)

    monkeypatch.setattr(cap_hold, '_read_single_audio', fetch)
    upload = Mock(side_effect=AssertionError('a source-slice plan must not upload another audio copy'))
    monkeypatch.setattr(cap_hold, 'upload_held_audio', upload)
    row = {
        'live_custody_version': 4,
        'audio_path': 'chunks/synthetic/cap-held/source.opus.enc',
        'audio_codec': 'ogg_opus',
        'sample_rate': 16000,
        'source_frames': 16000,
    }
    directory, snapshot = SimpleNamespace(name=str(tmp_path)), SimpleNamespace(id='source')

    async def prepare(uid, path, meta):
        with wave.open(path) as audio:
            audio.setpos(100)
            data = audio.readframes(1000)
        piece = str(tmp_path / '100.006250.wav')
        with wave.open(piece, 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(data)
        return {piece}, {piece: ({'live_source_slice': True}, 100)}, {}, {}

    async def save(uid, snapshot, stored, update):
        stored.update(update)
        return True

    meta = {'timestamp': 100, 'target_conversation_id': 'original-owner'}
    pieces, _, _ = await plan.ensure_plan('synthetic', snapshot, row, meta, directory, prepare, save)
    name, entry = next(iter(pieces.items()))
    expected = (tmp_path / name).read_bytes()
    assert entry['audio_path'] == row['audio_path'] and entry['source_slice']['start'] == 100
    assert entry['source_frames'] == 16000 and entry['seconds'] == 1000 / 16000
    frozen_context = json.loads(decrypt(entry['metadata'], 'synthetic'))
    assert frozen_context['target_conversation_id'] == 'original-owner'
    assert frozen_context['source_position_map'] is None
    prepare_again = AsyncMock(side_effect=AssertionError('retry must not replan VAD'))
    pieces, locals_, contexts = await plan.ensure_plan('synthetic', snapshot, row, meta, directory, prepare_again, save)
    path, context = await plan.stage_piece('synthetic', name, entry, directory, locals_, contexts)
    assert open(path, 'rb').read() == expected and context == frozen_context
    # Two pieces/retries reuse one decoded local source, never a second cloud object.
    await plan.stage_piece('synthetic', name, entry, directory, {}, {})
    assert len(reads) == 2  # Initial planning source + one cached retry source.
    upload.assert_not_called()
    changed = {**entry, 'source_slice': {**entry['source_slice'], 'sha256': 'changed'}}
    with pytest.raises(ValueError, match='decode changed'):
        await plan.stage_piece('synthetic', name, changed, directory, {}, {})
    assert not (tmp_path / name).exists()
