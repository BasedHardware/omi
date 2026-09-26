import io
from pathlib import Path
from unittest.mock import patch

from tests.unit.test_chat_quota_counting_router import _cleanup, _make_chat_client


def test_voice_question_wav_in_syncing_dir_is_deleted_after_the_stream(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    wav = Path('syncing', 'test-uid', 'recording_fs160_1726790400.wav')
    wav.parent.mkdir(parents=True)
    wav.write_bytes(b'RIFF')

    client, module, saved = _make_chat_client()
    try:

        async def fake_voice_stream(*args, **kwargs):
            yield 'done: e30=\n\n'

        with patch.object(module, 'retrieve_file_paths', return_value=[str(wav.with_suffix('.bin'))]):
            with patch.object(module, 'decode_files_to_wav', return_value=[str(wav)]):
                with patch.object(module, 'process_voice_message_segment_stream', side_effect=fake_voice_stream):
                    response = client.post(
                        '/v2/voice-messages',
                        files=[('files', ('recording_fs160_1726790400.bin', io.BytesIO(b'\x00' * 100), 'audio/ogg'))],
                        headers={'X-App-Platform': 'ios'},
                    )

        assert response.status_code == 200
        assert not wav.exists()
    finally:
        _cleanup(saved)


def test_cleanup_leaves_other_users_and_other_folders_alone(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    other_user = Path('syncing', 'other-uid', 'voice.wav')
    nested = Path('syncing', 'test-uid', 'nested', 'voice.wav')
    for path in (other_user, nested):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'RIFF')

    client, module, saved = _make_chat_client()
    try:
        module._cleanup_temp_voice_wavs([str(other_user), str(nested)], 'test-uid')
    finally:
        _cleanup(saved)

    assert other_user.exists()
    assert nested.exists()
