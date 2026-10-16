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
