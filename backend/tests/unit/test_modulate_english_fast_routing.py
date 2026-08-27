"""Only explicit-English sessions may reach the English-only Velma-2 model.

The ``velma-2-stt-streaming-english-v2`` endpoint rejects a ``language`` parameter and
accepts neither ``speaker_diarization`` nor ``partial_results``. Routing a ``multi``
session there would send auto-detect traffic -- which resolves to any language -- to a
model that can only transcribe English, so those users would get wrong transcripts
rather than an error. Every non-English and every auto-detect session must stay on the
multilingual endpoint with its diarization parameters intact.
"""

import urllib.parse
from unittest.mock import AsyncMock, patch

import pytest

from utils.stt import streaming


def _connect_uri(mock_connect):
    return mock_connect.await_args.args[0]


def _params(uri):
    return urllib.parse.parse_qs(urllib.parse.urlparse(uri).query)


async def _connect(language):
    with patch.object(streaming.websockets, 'connect', new=AsyncMock()) as mock_connect, patch.object(
        streaming, 'SafeModulateSocket'
    ), patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'}):
        await streaming.process_audio_modulate(lambda _segments: None, 16000, language)
        return _connect_uri(mock_connect)


@pytest.mark.asyncio
@pytest.mark.parametrize('language', ['en', 'en-US', 'EN', 'en_GB'])
async def test_english_sessions_use_english_fast_model(language):
    uri = await _connect(language)
    assert streaming.MODULATE_ENGLISH_FAST_PATH in uri
    params = _params(uri)
    assert 'language' not in params
    assert 'speaker_diarization' not in params
    assert 'partial_results' not in params


@pytest.mark.asyncio
@pytest.mark.parametrize('language', ['multi', 'ja', 'es-ES', 'pl', ''])
async def test_non_english_sessions_stay_on_multilingual_model(language):
    uri = await _connect(language)
    assert f'/{streaming.MODULATE_MULTILINGUAL_PATH}?' in uri
    params = _params(uri)
    assert params['speaker_diarization'] == ['true']
    assert params['partial_results'] == ['true']


@pytest.mark.asyncio
async def test_english_fast_can_be_disabled_without_a_deploy():
    with patch.object(streaming, 'MODULATE_ENGLISH_FAST_ENABLED', False):
        uri = await _connect('en')
    assert f'/{streaming.MODULATE_MULTILINGUAL_PATH}?' in uri
    assert _params(uri)['language'] == ['en']
