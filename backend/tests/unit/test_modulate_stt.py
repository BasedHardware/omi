import asyncio
import json
import struct
import sys
import threading
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

# Stub heavy deps before import
for mod in [
    'google.cloud',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.storage',
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'google.api_core',
    'google.api_core.exceptions',
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.firestore',
    'database.redis_db',
    'database.auth',
    'utils.other.storage',
    'deepgram',
    'deepgram.clients.live.v1',
    'fal_client',
    'opuslib',
    'silero_vad',
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Stub deepgram classes needed at import time
sys.modules['deepgram'].DeepgramClient = MagicMock
sys.modules['deepgram'].DeepgramClientOptions = MagicMock
sys.modules['deepgram'].LiveTranscriptionEvents = MagicMock()
sys.modules['deepgram.clients.live.v1'].LiveOptions = MagicMock

from utils.stt.streaming import (
    STTService,
    SafeModulateSocket,
    _build_wav_header,
    get_stt_service_for_language,
    modulate_languages,
)


class TestSTTServiceEnum(unittest.TestCase):
    def test_modulate_enum_exists(self):
        self.assertEqual(STTService.modulate.value, 'modulate')

    def test_get_model_name_modulate(self):
        self.assertEqual(STTService.get_model_name(STTService.modulate), 'modulate_streaming')

    def test_get_model_name_deepgram(self):
        self.assertEqual(STTService.get_model_name(STTService.deepgram), 'deepgram_streaming')


class TestLanguageRouting(unittest.TestCase):
    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2'])
    def test_modulate_routing_english(self):
        service, lang, model = get_stt_service_for_language('en')
        self.assertEqual(service, STTService.modulate)
        self.assertEqual(lang, 'en')
        self.assertEqual(model, 'velma-2')

    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2'])
    def test_modulate_routing_multi(self):
        service, lang, model = get_stt_service_for_language('multi')
        self.assertEqual(service, STTService.modulate)
        self.assertEqual(lang, 'multi')

    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2'])
    def test_modulate_unsupported_lang_fallback(self):
        service, lang, model = get_stt_service_for_language('xx-unsupported')
        self.assertEqual(service, STTService.deepgram)
        self.assertEqual(lang, 'en')
        self.assertEqual(model, 'nova-3')

    @patch('utils.stt.streaming.stt_service_models', ['dg-nova-3'])
    def test_deepgram_default(self):
        service, lang, model = get_stt_service_for_language('en')
        self.assertEqual(service, STTService.deepgram)

    @patch('utils.stt.streaming.stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    def test_deepgram_first_wins(self):
        service, lang, model = get_stt_service_for_language('en')
        self.assertEqual(service, STTService.deepgram)

    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2', 'dg-nova-3'])
    def test_modulate_first_wins(self):
        service, lang, model = get_stt_service_for_language('en')
        self.assertEqual(service, STTService.modulate)


class TestWAVHeader(unittest.TestCase):
    def test_wav_header_valid(self):
        header = _build_wav_header(16000)
        self.assertTrue(header.startswith(b'RIFF'))
        self.assertIn(b'WAVE', header)
        self.assertIn(b'fmt ', header)

    def test_wav_header_sample_rate(self):
        header = _build_wav_header(48000)
        fmt_offset = header.index(b'fmt ') + 4
        fmt_offset += 4  # skip chunk size
        fmt_offset += 2  # skip audio format
        fmt_offset += 2  # skip num channels
        sr = struct.unpack_from('<I', header, fmt_offset)[0]
        self.assertEqual(sr, 48000)

    def test_wav_header_mono_16bit(self):
        header = _build_wav_header(16000, bits_per_sample=16, channels=1)
        fmt_offset = header.index(b'fmt ') + 4
        fmt_offset += 4  # chunk size
        fmt_offset += 2  # audio format
        channels = struct.unpack_from('<H', header, fmt_offset)[0]
        self.assertEqual(channels, 1)


class TestSafeModulateSocket(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.ws = AsyncMock()
        self.ws.__aiter__ = AsyncMock(return_value=iter([]))
        self.transcript_callback = MagicMock()

    def tearDown(self):
        self.loop.close()

    def _make_socket(self, preseconds=0):
        async def create():
            sock = SafeModulateSocket(self.ws, self.transcript_callback, self.loop, preseconds=preseconds)
            sock.set_wav_header(_build_wav_header(16000))
            sock._recv_task.cancel()
            sock._send_task.cancel()
            return sock

        return self.loop.run_until_complete(create())

    def test_send_prepends_wav_header_once(self):
        sock = self._make_socket()
        header = _build_wav_header(16000)
        audio = b'\x00' * 100

        # First send should prepend WAV header
        sock.send(audio)
        self.assertTrue(sock._header_sent)

    def test_finalize_is_noop(self):
        sock = self._make_socket()
        sock.finalize()  # Should not raise

    def test_is_connection_dead_initially_false(self):
        sock = self._make_socket()
        self.assertFalse(sock.is_connection_dead)
        self.assertIsNone(sock.death_reason)

    def test_mark_dead(self):
        sock = self._make_socket()
        sock._mark_dead('test reason')
        self.assertTrue(sock.is_connection_dead)
        self.assertEqual(sock.death_reason, 'test reason')

    def test_mark_dead_only_first(self):
        sock = self._make_socket()
        sock._mark_dead('first')
        sock._mark_dead('second')
        self.assertEqual(sock.death_reason, 'first')

    def test_send_after_dead_is_noop(self):
        sock = self._make_socket()
        sock._mark_dead('dead')
        sock.send(b'\x00' * 10)  # Should not raise

    def test_send_after_closed_is_noop(self):
        sock = self._make_socket()
        sock.finish()
        sock.send(b'\x00' * 10)  # Should not raise

    def test_send_then_drain_ordering(self):
        """Audio sent via send() must arrive at ws.send() before EOS from drain_and_close()."""
        sent_data = []
        ws = AsyncMock()
        ws.send = AsyncMock(side_effect=lambda d: sent_data.append(d))
        ws.close = AsyncMock()

        loop = asyncio.new_event_loop()

        async def run():
            sock = SafeModulateSocket(ws, lambda s: None, loop, preseconds=0)
            sock.set_wav_header(b'')  # empty header for simplicity
            sock._recv_task.cancel()
            # send() uses call_soon_threadsafe, then drain_and_close() enqueues EOS
            sock.send(b'audio_chunk')
            await sock.drain_and_close()
            return sent_data

        try:
            result = loop.run_until_complete(run())
            # audio_chunk must appear before EOS ('')
            audio_idx = next((i for i, d in enumerate(result) if d == b'audio_chunk'), None)
            eos_idx = next((i for i, d in enumerate(result) if d == ''), None)
            self.assertIsNotNone(audio_idx, 'audio_chunk was not sent')
            self.assertIsNotNone(eos_idx, 'EOS was not sent')
            self.assertLess(audio_idx, eos_idx, 'audio must be sent before EOS')
        finally:
            loop.close()


class TestUtteranceHandling(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.ws = AsyncMock()
        self.ws.__aiter__ = AsyncMock(return_value=iter([]))
        self.segments = []
        self.transcript_callback = lambda s: self.segments.extend(s)

    def tearDown(self):
        self.loop.close()

    def _make_socket(self, preseconds=0):
        async def create():
            sock = SafeModulateSocket(self.ws, self.transcript_callback, self.loop, preseconds=preseconds)
            sock._recv_task.cancel()
            sock._send_task.cancel()
            return sock

        return self.loop.run_until_complete(create())

    def test_utterance_parsing(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'hello world', 'start_ms': 1000, 'duration_ms': 500, 'speaker': 1}
        sock._handle_utterance(msg)

        self.assertEqual(len(self.segments), 1)
        seg = self.segments[0]
        self.assertEqual(seg['text'], 'hello world')
        self.assertAlmostEqual(seg['start'], 1.0)
        self.assertAlmostEqual(seg['end'], 1.5)
        self.assertEqual(seg['speaker'], 'SPEAKER_00')
        self.assertFalse(seg['is_user'])

    def test_speaker_mapping_1_to_00(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'a', 'start_ms': 0, 'duration_ms': 100, 'speaker': 1}
        sock._handle_utterance(msg)
        self.assertEqual(self.segments[0]['speaker'], 'SPEAKER_00')

    def test_speaker_mapping_2_to_01(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'a', 'start_ms': 0, 'duration_ms': 100, 'speaker': 2}
        sock._handle_utterance(msg)
        self.assertEqual(self.segments[0]['speaker'], 'SPEAKER_01')

    def test_speaker_mapping_none_defaults_to_00(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'a', 'start_ms': 0, 'duration_ms': 100, 'speaker': None}
        sock._handle_utterance(msg)
        self.assertEqual(self.segments[0]['speaker'], 'SPEAKER_00')

    def test_speaker_mapping_missing_defaults_to_00(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'a', 'start_ms': 0, 'duration_ms': 100}
        sock._handle_utterance(msg)
        self.assertEqual(self.segments[0]['speaker'], 'SPEAKER_00')

    def test_speaker_mapping_zero_defaults_to_00(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'a', 'start_ms': 0, 'duration_ms': 100, 'speaker': 0}
        sock._handle_utterance(msg)
        self.assertEqual(self.segments[0]['speaker'], 'SPEAKER_00')

    def test_empty_text_skipped(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': '', 'start_ms': 0, 'duration_ms': 100, 'speaker': 1}
        sock._handle_utterance(msg)
        self.assertEqual(len(self.segments), 0)

    def test_whitespace_text_skipped(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': '   ', 'start_ms': 0, 'duration_ms': 100, 'speaker': 1}
        sock._handle_utterance(msg)
        self.assertEqual(len(self.segments), 0)

    def test_preseconds_filter(self):
        sock = self._make_socket(preseconds=5)
        msg = {'type': 'utterance', 'text': 'early', 'start_ms': 3000, 'duration_ms': 500, 'speaker': 1}
        sock._handle_utterance(msg)
        self.assertEqual(len(self.segments), 0)

    def test_preseconds_boundary(self):
        sock = self._make_socket(preseconds=5)
        msg = {'type': 'utterance', 'text': 'at boundary', 'start_ms': 5000, 'duration_ms': 500, 'speaker': 1}
        sock._handle_utterance(msg)
        self.assertEqual(len(self.segments), 1)

    def test_timestamp_conversion(self):
        sock = self._make_socket()
        msg = {'type': 'utterance', 'text': 'hello', 'start_ms': 2500, 'duration_ms': 1500, 'speaker': 1}
        sock._handle_utterance(msg)
        self.assertAlmostEqual(self.segments[0]['start'], 2.5)
        self.assertAlmostEqual(self.segments[0]['end'], 4.0)


class TestModulatePrerecorded(unittest.TestCase):
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    @patch('utils.stt.pre_recorded.httpx.Client')
    def test_basic_transcription(self, mock_client_cls):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'utterances': [
                {'text': 'hello', 'start_ms': 1000, 'duration_ms': 500, 'speaker': 1, 'language': 'en'},
                {'text': 'world', 'start_ms': 2000, 'duration_ms': 300, 'speaker': 2, 'language': 'en'},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        words = modulate_prerecorded_from_bytes(b'\x00' * 100, 16000)

        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]['text'], 'hello')
        self.assertAlmostEqual(words[0]['timestamp'][0], 1.0)
        self.assertAlmostEqual(words[0]['timestamp'][1], 1.5)
        self.assertEqual(words[0]['speaker'], 'SPEAKER_00')
        self.assertEqual(words[1]['speaker'], 'SPEAKER_01')

    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    @patch('utils.stt.pre_recorded.httpx.Client')
    def test_return_language(self, mock_client_cls):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'utterances': [
                {'text': 'bonjour', 'start_ms': 0, 'duration_ms': 500, 'speaker': 1, 'language': 'fr'},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        words, lang = modulate_prerecorded_from_bytes(b'\x00' * 100, 16000, return_language=True)

        self.assertEqual(lang, 'fr')
        self.assertEqual(len(words), 1)

    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    @patch('utils.stt.pre_recorded.httpx.Client')
    def test_empty_utterances(self, mock_client_cls):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {'utterances': []}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        words = modulate_prerecorded_from_bytes(b'\x00' * 100, 16000)
        self.assertEqual(words, [])

    @patch.dict('os.environ', {}, clear=False)
    def test_missing_api_key_raises(self):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        with patch.dict('os.environ', {k: v for k, v in __import__('os').environ.items() if k != 'MODULATE_API_KEY'}):
            with self.assertRaises(ValueError):
                modulate_prerecorded_from_bytes(b'\x00' * 100, 16000)

    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    @patch('utils.stt.pre_recorded.httpx.Client')
    def test_retry_exhaustion_raises_runtime_error(self, mock_client_cls):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception('connection timeout')
        mock_client_cls.return_value = mock_client

        with self.assertRaises(RuntimeError):
            modulate_prerecorded_from_bytes(b'\x00' * 100, 16000)


class TestProcessAudioModulate(unittest.TestCase):
    @patch.dict('os.environ', {}, clear=False)
    def test_missing_api_key_raises(self):
        from utils.stt.streaming import process_audio_modulate

        loop = asyncio.new_event_loop()
        try:
            with patch.dict(
                'os.environ', {k: v for k, v in __import__('os').environ.items() if k != 'MODULATE_API_KEY'}
            ):
                with self.assertRaises(ValueError):
                    loop.run_until_complete(process_audio_modulate(lambda s: None, 16000, 'en'))
        finally:
            loop.close()


if __name__ == '__main__':
    unittest.main()
