"""Exercise real voice HTTP handlers with synthetic provider results."""

import io
from unittest.mock import Mock

import pytest

from tests.unit.test_chat_quota_counting_router import _make_chat_client, _cleanup


def test_pcm_response_reports_the_provider_that_served(monkeypatch):
    client, router, saved = _make_chat_client()
    try:
        monkeypatch.setattr(router, 'get_prerecorded_service', lambda _: ('modulate', 'en', 'velma-2'))
        dispatch = Mock(return_value=('recovered', 'en', 'soniox', 'stt-async-v5'))
        monkeypatch.setattr(router, 'transcribe_pcm_bytes', dispatch)
        response = client.post(
            '/v2/voice-message/transcribe?language=en',
            content=b'\x01\x00' * 160,
            headers={'Content-Type': 'application/octet-stream'},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            'transcript': 'recovered',
            'language': 'en',
            'stt_provider': 'soniox',
            'stt_model': 'stt-async-v5',
            'outcome': 'success',
        }
        assert dispatch.call_args.kwargs['return_provider'] is True
    finally:
        _cleanup(saved)


@pytest.mark.parametrize('providers', [('soniox', 'modulate'), ('modulate', 'soniox')])
def test_multipart_reports_soniox_if_any_segment_used_it(monkeypatch, tmp_path, providers):
    client, router, saved = _make_chat_client()
    try:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(router, 'get_prerecorded_service', lambda _: ('modulate', 'en', 'velma-2'))
        results = [('recovered', 'en', p, 'stt-async-v5' if p == 'soniox' else 'velma-2') for p in providers]
        dispatch = Mock(side_effect=results)
        monkeypatch.setattr(router, 'transcribe_voice_message_segment', dispatch)
        response = client.post(
            '/v2/voice-message/transcribe',
            files=[('files', (name, io.BytesIO(b'RIFF'), 'audio/wav')) for name in ('first.wav', 'second.wav')],
        )
        assert response.status_code == 200, response.text
        assert response.json()['transcript'] == 'recovered recovered'
        assert response.json()['stt_provider'] == 'soniox'
        assert response.json()['stt_model'] == 'stt-async-v5'
        assert dispatch.call_count == 2
    finally:
        _cleanup(saved)
