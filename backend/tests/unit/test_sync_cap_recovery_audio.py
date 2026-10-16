"""Held capture replay runs coverage before VAD and preserves source coordinates."""

from unittest.mock import AsyncMock, Mock

from utils.sync import cap_recovery_audio as audio


async def test_recovery_replays_wal_and_safety_coverage_before_vad(monkeypatch):
    events = []
    mapping = {'claim': {'codec': 'pcm16'}, 'offsets': [0, 400, 800]}

    async def run_blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def wal(*args, **kwargs):
        events.append('wal')
        assert args[5] == {'audio_pcm16_1792152000.bin': mapping['claim']}
        assert args[7] == {'/local/audio_pcm16_1792152000.wav': [400, 400]}
        return ['/local/remaining.wav'], {'/local/remaining.wav': mapping}, False

    async def safety(*args, **kwargs):
        events.append('safety')
        assert kwargs['protected_paths'] == {'/local/remaining.wav': mapping}
        return ['/local/remaining.wav'], set()

    def vad(path, segments, errors, **kwargs):
        events.append('vad')
        assert path == '/local/remaining.wav'
        assert kwargs['source_frame_map'] == mapping
        segments.add('/local/piece.wav')
        kwargs['segment_source_maps']['/local/piece.wav'] = (mapping, 400)

    monkeypatch.setattr(audio, 'run_blocking', run_blocking)
    monkeypatch.setattr(audio, 'apply_sync_wal_audio_coverage', wal)
    monkeypatch.setattr(audio, 'apply_safety_wal_coverage', safety)
    monkeypatch.setattr(audio, 'sync_safety_wal_enabled', lambda: True)
    monkeypatch.setattr(audio, 'sync_lineage_resolve_active_for', lambda uid: False)
    monkeypatch.setattr(audio, 'retrieve_vad_segments', vad)
    paths, maps, _, _ = await audio.prepare(
        'synthetic',
        '/local/audio_pcm16_1792152000.wav',
        {'source': 'omi', 'full_capture': True, 'source_frame_map': mapping, 'recording_session_id': 'origin'},
    )
    assert events == ['wal', 'safety', 'vad']
    assert paths == {'/local/piece.wav'}
    assert maps['/local/piece.wav'] == (mapping, 400)


async def test_already_segmented_hold_preserves_position_without_repeating_vad(monkeypatch):
    vad = Mock()
    coverage = AsyncMock()
    monkeypatch.setattr(audio, 'retrieve_vad_segments', vad)
    monkeypatch.setattr(audio, 'apply_sync_wal_audio_coverage', coverage)
    position = [{'claim': {'codec': 'pcm16'}, 'offsets': [0, 400]}, 10]
    paths, maps, _, _ = await audio.prepare('synthetic', '/local/piece.wav', {'source_position_map': position})
    assert paths == {'/local/piece.wav'}
    assert maps['/local/piece.wav'] == tuple(position)
    vad.assert_not_called()
    coverage.assert_not_called()
