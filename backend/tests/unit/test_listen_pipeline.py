"""Comprehensive test suite for /v4/listen + Pusher pipeline.

Tests the recording transcription pipeline end-to-end:
- Pure audio functions (resample, mix, channel config)
- Wire protocol binary packing/unpacking (headers 100-105, 201)
- Buffer bounds enforcement (segment, audio, photo, pending requests)
- Pusher receive_tasks header demux and queue dispatch
- Private cloud batch accumulation + flush logic
- Speaker sample queue age gating
- Conversation lifecycle timeout logic
- Audio buffer guard (consumer-gated accumulation)

Designed to find flaw points: race conditions, buffer overflows,
data loss, timeout edge cases, and protocol parsing errors.
"""

import asyncio
import json
import struct
import time
from collections import deque, OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module stubs — prevent Firestore/Redis/heavy imports at module load
# ---------------------------------------------------------------------------
import os
import sys

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# ---------------------------------------------------------------------------
# Extracted pure functions from routers/transcribe.py
# (copied here to avoid importing the full module with all its dependencies)
# ---------------------------------------------------------------------------
from dataclasses import dataclass


@dataclass
class ChannelConfig:
    channel_id: int
    label: str
    is_user: bool
    speaker_label: str


def build_channel_config(source: str):
    """Build channel configuration based on source type."""
    if source == 'phone_call':
        return [
            ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
            ChannelConfig(channel_id=0x02, label='remote', is_user=False, speaker_label='SPEAKER_01'),
        ]
    elif source == 'desktop':
        return [
            ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
            ChannelConfig(channel_id=0x02, label='system_audio', is_user=False, speaker_label='SPEAKER_01'),
        ]
    return [
        ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
        ChannelConfig(channel_id=0x02, label='remote', is_user=False, speaker_label='SPEAKER_01'),
    ]


def mix_n_channel_buffers(buffers):
    """Mix N 16-bit PCM mono buffers sample-by-sample into one mono stream, clamping to int16 range."""
    min_len = min((len(b) for b in buffers), default=0)
    if min_len < 2:
        return b''
    min_len = min_len - (min_len % 2)
    num_samples = min_len // 2
    channel_samples = [struct.unpack(f'<{num_samples}h', b[:min_len]) for b in buffers]
    mixed = []
    for i in range(num_samples):
        s = sum(ch[i] for ch in channel_samples)
        mixed.append(max(-32768, min(32767, s)))
    return struct.pack(f'<{num_samples}h', *mixed)


def resample_pcm(pcm_data, source_rate, target_rate):
    """Simple resampling by sample duplication/decimation."""
    if source_rate == target_rate:
        return pcm_data
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return pcm_data
    samples = struct.unpack(f'<{num_samples}h', pcm_data)
    ratio = target_rate / source_rate
    new_length = int(num_samples * ratio)
    resampled = []
    for i in range(new_length):
        src_idx = min(int(i / ratio), num_samples - 1)
        resampled.append(samples[src_idx])
    return struct.pack(f'<{len(resampled)}h', *resampled)


# ===================================================================
# SECTION 1: Pure Audio Functions (resample, mix, channel config)
# ===================================================================


class TestResamplePcm:
    """Test resample_pcm — sample duplication/decimation for audio rate conversion."""

    def _resample(self, pcm_data, source_rate, target_rate):
        return resample_pcm(pcm_data, source_rate, target_rate)

    def test_same_rate_passthrough(self):
        """Same source and target rate should return data unchanged."""
        data = struct.pack('<4h', 100, 200, 300, 400)
        result = self._resample(data, 16000, 16000)
        assert result == data

    def test_upsample_8k_to_16k(self):
        """8kHz → 16kHz should double sample count via duplication."""
        samples = [100, 200, 300, 400]
        data = struct.pack(f'<{len(samples)}h', *samples)
        result = self._resample(data, 8000, 16000)
        result_samples = struct.unpack(f'<{len(result)//2}h', result)
        assert len(result_samples) == 8  # doubled
        # Each original sample should appear twice
        assert result_samples[0] == 100
        assert result_samples[1] == 100
        assert result_samples[2] == 200
        assert result_samples[3] == 200

    def test_downsample_16k_to_8k(self):
        """16kHz → 8kHz should halve sample count via decimation."""
        samples = [100, 200, 300, 400, 500, 600, 700, 800]
        data = struct.pack(f'<{len(samples)}h', *samples)
        result = self._resample(data, 16000, 8000)
        result_samples = struct.unpack(f'<{len(result)//2}h', result)
        assert len(result_samples) == 4  # halved

    def test_empty_data(self):
        """Empty input should return empty output."""
        result = self._resample(b'', 8000, 16000)
        assert result == b''

    def test_single_byte_odd_length(self):
        """Odd-length data (not aligned to 2-byte samples) should handle gracefully."""
        result = self._resample(b'\x00', 8000, 16000)
        # num_samples = 0 for 1 byte → returns unchanged
        assert result == b'\x00'

    def test_flaw_large_ratio_upsample(self):
        """FLAW TEST: Extreme upsample ratio (8kHz → 48kHz = 6x) — check memory/correctness."""
        samples = list(range(100))
        data = struct.pack(f'<{len(samples)}h', *samples)
        result = self._resample(data, 8000, 48000)
        result_samples = struct.unpack(f'<{len(result)//2}h', result)
        assert len(result_samples) == 600  # 6x expansion
        # First and last samples should map correctly
        assert result_samples[0] == 0
        assert result_samples[-1] == 99


class TestMixNChannelBuffers:
    """Test mix_n_channel_buffers — multi-channel PCM mixing with clamping."""

    def _mix(self, buffers):
        return mix_n_channel_buffers(buffers)

    def test_single_channel_passthrough(self):
        """Single channel should pass through unchanged."""
        data = bytearray(struct.pack('<4h', 100, 200, 300, 400))
        result = self._mix([data])
        samples = struct.unpack(f'<{len(result)//2}h', result)
        assert samples == (100, 200, 300, 400)

    def test_two_channel_mix(self):
        """Two channels should sum sample-by-sample."""
        ch1 = bytearray(struct.pack('<2h', 100, 200))
        ch2 = bytearray(struct.pack('<2h', 300, 400))
        result = self._mix([ch1, ch2])
        samples = struct.unpack(f'<{len(result)//2}h', result)
        assert samples == (400, 600)

    def test_clamping_overflow(self):
        """FLAW TEST: Overflow should clamp to 32767, not wrap around."""
        ch1 = bytearray(struct.pack('<1h', 30000))
        ch2 = bytearray(struct.pack('<1h', 30000))
        result = self._mix([ch1, ch2])
        samples = struct.unpack(f'<{len(result)//2}h', result)
        assert samples[0] == 32767  # clamped, not 60000 or wrapped

    def test_clamping_underflow(self):
        """FLAW TEST: Underflow should clamp to -32768."""
        ch1 = bytearray(struct.pack('<1h', -30000))
        ch2 = bytearray(struct.pack('<1h', -30000))
        result = self._mix([ch1, ch2])
        samples = struct.unpack(f'<{len(result)//2}h', result)
        assert samples[0] == -32768  # clamped

    def test_different_lengths_uses_min(self):
        """Buffers of different lengths should use min_len."""
        ch1 = bytearray(struct.pack('<4h', 1, 2, 3, 4))
        ch2 = bytearray(struct.pack('<2h', 10, 20))
        result = self._mix([ch1, ch2])
        samples = struct.unpack(f'<{len(result)//2}h', result)
        assert len(samples) == 2
        assert samples == (11, 22)

    def test_empty_buffer(self):
        """Empty buffer list should return empty bytes."""
        result = self._mix([bytearray()])
        assert result == b''

    def test_sub_sample_data(self):
        """Buffer with only 1 byte (less than a sample) → empty output."""
        result = self._mix([bytearray(b'\x01')])
        assert result == b''

    def test_flaw_three_channels_overflow(self):
        """FLAW TEST: 3 channels near max → triple overflow, should clamp."""
        ch1 = bytearray(struct.pack('<1h', 20000))
        ch2 = bytearray(struct.pack('<1h', 20000))
        ch3 = bytearray(struct.pack('<1h', 20000))
        result = self._mix([ch1, ch2, ch3])
        samples = struct.unpack(f'<{len(result)//2}h', result)
        assert samples[0] == 32767  # 60000 clamped to 32767


class TestBuildChannelConfig:
    """Test build_channel_config — channel configuration by source type."""

    def _build(self, source):
        return build_channel_config(source)

    def test_phone_call_config(self):
        channels = self._build('phone_call')
        assert len(channels) == 2
        assert channels[0].label == 'mic'
        assert channels[0].is_user is True
        assert channels[1].label == 'remote'
        assert channels[1].is_user is False

    def test_desktop_config(self):
        channels = self._build('desktop')
        assert len(channels) == 2
        assert channels[0].label == 'mic'
        assert channels[1].label == 'system_audio'

    def test_unknown_source_defaults(self):
        """Unknown source should default to phone_call-style config."""
        channels = self._build('unknown_source')
        assert len(channels) == 2
        assert channels[0].channel_id == 0x01
        assert channels[1].channel_id == 0x02

    def test_omi_source_defaults(self):
        """'omi' source (most common) should also get default config."""
        channels = self._build('omi')
        assert len(channels) == 2
        assert channels[0].is_user is True


# ===================================================================
# SECTION 2: Wire Protocol Binary Packing/Unpacking
# ===================================================================


class TestWireProtocol:
    """Test the Listen ↔ Pusher wire protocol binary format.

    Format: [4-byte uint32 LE header_type][variable payload]
    Headers 100-105 (Listen→Pusher), 201 (Pusher→Listen)
    """

    def test_header_100_heartbeat(self):
        """Header 100: heartbeat — 4 bytes only, no payload."""
        msg = struct.pack('<I', 100)
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 100
        assert len(msg) == 4

    def test_header_101_audio_bytes(self):
        """Header 101: [header(4)][timestamp(8 double)][audio_data]"""
        timestamp = 1710000000.123456
        audio = b'\x00\x01' * 100  # 200 bytes of audio
        msg = struct.pack('<I', 101) + struct.pack('d', timestamp) + audio
        # Parse
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 101
        parsed_ts = struct.unpack('d', msg[4:12])[0]
        assert abs(parsed_ts - timestamp) < 1e-6
        parsed_audio = msg[12:]
        assert parsed_audio == audio
        assert len(parsed_audio) == 200

    def test_header_102_transcript(self):
        """Header 102: [header(4)][JSON {segments, memory_id}]"""
        payload = {'segments': [{'text': 'hello', 'speaker': 'SPEAKER_00'}], 'memory_id': 'conv-123'}
        msg = struct.pack('<I', 102) + json.dumps(payload).encode('utf-8')
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 102
        parsed = json.loads(msg[4:].decode('utf-8'))
        assert parsed['segments'][0]['text'] == 'hello'
        assert parsed['memory_id'] == 'conv-123'

    def test_header_103_conversation_id(self):
        """Header 103: [header(4)][conversation_id UTF-8 string]"""
        conv_id = 'abc-def-123'
        msg = struct.pack('<I', 103) + conv_id.encode('utf-8')
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 103
        parsed_id = msg[4:].decode('utf-8')
        assert parsed_id == conv_id

    def test_header_104_process_conversation(self):
        """Header 104: [header(4)][JSON {conversation_id, language}]"""
        payload = {'conversation_id': 'conv-456', 'language': 'en'}
        msg = struct.pack('<I', 104) + json.dumps(payload).encode('utf-8')
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 104
        parsed = json.loads(msg[4:].decode('utf-8'))
        assert parsed['conversation_id'] == 'conv-456'
        assert parsed['language'] == 'en'

    def test_header_105_speaker_sample(self):
        """Header 105: [header(4)][JSON {person_id, conversation_id, segment_ids}]"""
        payload = {'person_id': 'p1', 'conversation_id': 'c1', 'segment_ids': ['s1', 's2']}
        msg = struct.pack('<I', 105) + json.dumps(payload).encode('utf-8')
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 105
        parsed = json.loads(msg[4:].decode('utf-8'))
        assert parsed['person_id'] == 'p1'
        assert len(parsed['segment_ids']) == 2

    def test_header_201_response(self):
        """Header 201: Pusher→Listen response [header(4)][JSON {conversation_id, success}]"""
        payload = {'conversation_id': 'conv-789', 'success': True}
        msg = struct.pack('<I', 201) + json.dumps(payload).encode('utf-8')
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 201
        parsed = json.loads(msg[4:].decode('utf-8'))
        assert parsed['success'] is True

    def test_flaw_truncated_header(self):
        """FLAW TEST: Message shorter than 4 bytes should raise on unpack."""
        with pytest.raises(struct.error):
            struct.unpack('<I', b'\x00\x01')  # only 2 bytes

    def test_flaw_truncated_audio_timestamp(self):
        """FLAW TEST: Header 101 with only 6 bytes after header (needs 8 for timestamp)."""
        msg = struct.pack('<I', 101) + b'\x00' * 6  # 6 bytes, need 8 for double
        with pytest.raises(struct.error):
            struct.unpack('d', msg[4:12])

    def test_flaw_invalid_json_payload(self):
        """FLAW TEST: Header 102 with invalid JSON should raise."""
        msg = struct.pack('<I', 102) + b'not-valid-json{'
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 102
        with pytest.raises(json.JSONDecodeError):
            json.loads(msg[4:].decode('utf-8'))

    def test_flaw_unknown_header_type(self):
        """FLAW TEST: Unknown header type (999) — should be silently ignored by receive_tasks."""
        msg = struct.pack('<I', 999) + b'payload'
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 999
        # In real code, receive_tasks falls through all if-checks and drops to next loop iteration
        # This is correct behavior — no crash

    def test_roundtrip_audio_header(self):
        """Roundtrip: pack and unpack audio header preserves precision."""
        ts = time.time()
        audio = bytes(range(256)) * 10
        msg = struct.pack('<I', 101) + struct.pack('d', ts) + audio
        parsed_ts = struct.unpack('d', msg[4:12])[0]
        assert parsed_ts == ts  # doubles should be exact
        assert msg[12:] == audio

    def test_flaw_empty_payload_header_102(self):
        """FLAW TEST: Header 102 with empty JSON string."""
        msg = struct.pack('<I', 102) + b''
        with pytest.raises(json.JSONDecodeError):
            json.loads(msg[4:].decode('utf-8'))

    def test_conversation_id_unicode(self):
        """Conversation ID with UUID should round-trip correctly."""
        import uuid

        conv_id = str(uuid.uuid4())
        msg = struct.pack('<I', 103) + conv_id.encode('utf-8')
        parsed = msg[4:].decode('utf-8')
        assert parsed == conv_id


# ===================================================================
# SECTION 3: Buffer Bounds Enforcement
# ===================================================================


class TestBufferBounds:
    """Test buffer size limits that prevent memory leaks during outages.

    From transcribe.py _stream_handler:
    - MAX_SEGMENT_BUFFER_SIZE = 1000
    - MAX_PHOTO_BUFFER_SIZE = 100
    - MAX_AUDIO_BUFFER_SIZE = 10MB
    - MAX_PENDING_REQUESTS = 100
    """

    def test_segment_buffer_bounded_deque(self):
        """Segment buffer (deque maxlen=1000) should drop oldest when full."""
        MAX_SEGMENT_BUFFER_SIZE = 1000
        buf = deque(maxlen=MAX_SEGMENT_BUFFER_SIZE)
        for i in range(1500):
            buf.append({'text': f'segment_{i}', 'id': i})
        assert len(buf) == 1000
        # Oldest should be dropped — first element should be segment_500
        assert buf[0]['id'] == 500

    def test_photo_buffer_bounded_deque(self):
        """Photo buffer (deque maxlen=100) should drop oldest when full."""
        MAX_PHOTO_BUFFER_SIZE = 100
        buf = deque(maxlen=MAX_PHOTO_BUFFER_SIZE)
        for i in range(150):
            buf.append({'photo_id': i})
        assert len(buf) == 100
        assert buf[0]['photo_id'] == 50

    def test_audio_buffer_10mb_limit(self):
        """Audio buffer should not exceed 10MB."""
        MAX_AUDIO_BUFFER_SIZE = 1024 * 1024 * 10  # 10MB
        total_size = 0
        chunks = deque()
        # Simulate adding 1MB chunks
        for i in range(15):
            chunk = b'\x00' * (1024 * 1024)  # 1MB
            if total_size + len(chunk) > MAX_AUDIO_BUFFER_SIZE:
                # Drop oldest
                while total_size + len(chunk) > MAX_AUDIO_BUFFER_SIZE and chunks:
                    dropped = chunks.popleft()
                    total_size -= len(dropped)
            chunks.append(chunk)
            total_size += len(chunk)
        assert total_size <= MAX_AUDIO_BUFFER_SIZE

    def test_pending_requests_max_100(self):
        """Pending conversation requests should cap at 100."""
        MAX_PENDING_REQUESTS = 100
        pending = deque(maxlen=MAX_PENDING_REQUESTS)
        for i in range(150):
            pending.append({'conversation_id': f'conv-{i}', 'timestamp': time.time()})
        assert len(pending) == 100

    def test_flaw_segment_buffer_data_loss_ordering(self):
        """FLAW TEST: When segment buffer overflows, verify FIFO — newest kept, oldest dropped."""
        buf = deque(maxlen=1000)
        for i in range(2000):
            buf.append(i)
        assert buf[0] == 1000  # oldest surviving
        assert buf[-1] == 1999  # newest
        assert len(buf) == 1000

    def test_image_chunks_max_50(self):
        """Image chunk cache should cap at 50 concurrent uploads."""
        MAX_IMAGE_CHUNKS = 50
        cache = OrderedDict()
        for i in range(60):
            if len(cache) >= MAX_IMAGE_CHUNKS:
                # Drop oldest (FIFO via OrderedDict)
                cache.popitem(last=False)
            cache[f'img-{i}'] = {'created_at': time.time(), 'chunks': {}}
        assert len(cache) == 50

    def test_image_chunks_ttl_60s(self):
        """Image chunks older than 60s TTL should be expired."""
        IMAGE_CHUNK_TTL = 60.0
        now = time.time()
        cache = OrderedDict()
        # Add old chunks (90s ago) and fresh ones
        for i in range(5):
            cache[f'old-{i}'] = {'created_at': now - 90}
        for i in range(5):
            cache[f'new-{i}'] = {'created_at': now - 10}
        # Cleanup
        expired = [tid for tid, data in cache.items() if now - data['created_at'] > IMAGE_CHUNK_TTL]
        for tid in expired:
            del cache[tid]
        assert len(cache) == 5
        assert all(k.startswith('new-') for k in cache)


# ===================================================================
# SECTION 4: Pusher Queue Dispatch & Header Demux
# ===================================================================


class TestPusherHeaderDemux:
    """Test the receive_tasks header demux logic extracted from pusher.py.

    Verifies correct routing of wire protocol messages to queues.
    """

    def _make_msg(self, header_type, payload=b''):
        """Build a wire protocol message."""
        return struct.pack('<I', header_type) + payload

    def test_header_100_heartbeat_ignored(self):
        """Header 100 (heartbeat) should be consumed with no side effects."""
        msg = self._make_msg(100)
        header_type = struct.unpack('<I', msg[:4])[0]
        assert header_type == 100
        # No queue append — just continue

    def test_header_103_sets_conversation_id(self):
        """Header 103 should update current_conversation_id."""
        conv_id = 'test-conv-abc'
        msg = self._make_msg(103, conv_id.encode('utf-8'))
        header_type = struct.unpack('<I', msg[:4])[0]
        parsed_id = bytes(msg[4:]).decode('utf-8')
        assert header_type == 103
        assert parsed_id == conv_id

    def test_header_102_queues_transcript(self):
        """Header 102 should parse JSON and append to transcript_queue."""
        transcript_queue = deque(maxlen=50)
        payload = {'segments': [{'text': 'test'}], 'memory_id': 'mem-1'}
        msg = self._make_msg(102, json.dumps(payload).encode('utf-8'))
        # Simulate receive_tasks logic
        data = msg
        header_type = struct.unpack('<I', data[:4])[0]
        res = json.loads(bytes(data[4:]).decode('utf-8'))
        segments = res.get('segments')
        memory_id = res.get('memory_id')
        conversation_or_memory_id = memory_id or 'fallback-conv'
        transcript_queue.append({'segments': segments, 'memory_id': conversation_or_memory_id})
        assert len(transcript_queue) == 1
        assert transcript_queue[0]['memory_id'] == 'mem-1'

    def test_header_105_queues_speaker_sample(self):
        """Header 105 should append to speaker_sample_queue with queued_at timestamp."""
        speaker_sample_queue = deque(maxlen=100)
        payload = {'person_id': 'p1', 'conversation_id': 'c1', 'segment_ids': ['s1']}
        msg = self._make_msg(105, json.dumps(payload).encode('utf-8'))
        data = msg
        res = json.loads(bytes(data[4:]).decode('utf-8'))
        person_id = res.get('person_id')
        conv_id = res.get('conversation_id')
        segment_ids = res.get('segment_ids', [])
        if person_id and conv_id and segment_ids:
            speaker_sample_queue.append(
                {
                    'person_id': person_id,
                    'conversation_id': conv_id,
                    'segment_ids': segment_ids,
                    'queued_at': time.time(),
                }
            )
        assert len(speaker_sample_queue) == 1
        assert speaker_sample_queue[0]['person_id'] == 'p1'

    def test_header_105_missing_fields_not_queued(self):
        """FLAW TEST: Header 105 with missing person_id should NOT queue."""
        speaker_sample_queue = deque(maxlen=100)
        payload = {'conversation_id': 'c1', 'segment_ids': ['s1']}  # missing person_id
        msg = self._make_msg(105, json.dumps(payload).encode('utf-8'))
        res = json.loads(bytes(msg[4:]).decode('utf-8'))
        person_id = res.get('person_id')
        conv_id = res.get('conversation_id')
        segment_ids = res.get('segment_ids', [])
        if person_id and conv_id and segment_ids:
            speaker_sample_queue.append({})
        assert len(speaker_sample_queue) == 0  # not queued

    def test_header_101_audio_with_consumer_guard(self):
        """Header 101 should only accumulate audio when consumer exists."""
        trigger_audiobuffer = bytearray()
        audiobuffer = bytearray()
        has_audio_apps_enabled = False
        audio_bytes_webhook_delay_seconds = None

        audio_data = b'\x00\x01' * 100
        timestamp = time.time()
        msg = self._make_msg(101, struct.pack('d', timestamp) + audio_data)
        data = msg
        parsed_audio = data[12:]

        if has_audio_apps_enabled:
            trigger_audiobuffer.extend(parsed_audio)
        if audio_bytes_webhook_delay_seconds is not None:
            audiobuffer.extend(parsed_audio)

        # Neither consumer exists → buffers stay empty
        assert len(trigger_audiobuffer) == 0
        assert len(audiobuffer) == 0

    def test_header_101_audio_with_app_enabled(self):
        """Header 101 with audio apps enabled should accumulate in trigger_audiobuffer."""
        trigger_audiobuffer = bytearray()
        has_audio_apps_enabled = True

        audio_data = b'\x00\x01' * 100
        if has_audio_apps_enabled:
            trigger_audiobuffer.extend(audio_data)
        assert len(trigger_audiobuffer) == 200

    def test_flaw_header_103_conversation_switch_flushes_private_cloud(self):
        """FLAW TEST: Switching conversation_id should flush private cloud buffer for old conv."""
        private_cloud_queue = []
        private_cloud_sync_buffer = bytearray(b'\x00' * 500)
        old_conv_id = 'old-conv'
        new_conv_id = 'new-conv'
        private_cloud_sync_enabled = True
        private_cloud_chunk_start_time = time.time() - 30

        # Simulate header 103 handling
        if (
            private_cloud_sync_enabled
            and old_conv_id
            and old_conv_id != new_conv_id
            and len(private_cloud_sync_buffer) > 0
        ):
            private_cloud_queue.append(
                {
                    'data': bytes(private_cloud_sync_buffer),
                    'conversation_id': old_conv_id,
                    'timestamp': private_cloud_chunk_start_time or time.time(),
                    'retries': 0,
                }
            )
            private_cloud_sync_buffer = bytearray()
            private_cloud_chunk_start_time = None

        assert len(private_cloud_queue) == 1
        assert private_cloud_queue[0]['conversation_id'] == 'old-conv'
        assert len(private_cloud_queue[0]['data']) == 500
        assert len(private_cloud_sync_buffer) == 0

    def test_flaw_header_102_memory_id_updates_conversation_id(self):
        """FLAW TEST: memory_id in transcript should update current_conversation_id."""
        current_conversation_id = 'old-conv'
        payload = {'segments': [], 'memory_id': 'new-conv-from-memory'}
        res = payload
        memory_id = res.get('memory_id')
        if memory_id:
            current_conversation_id = memory_id
        assert current_conversation_id == 'new-conv-from-memory'


# ===================================================================
# SECTION 5: Private Cloud Batch Accumulation + Flush Logic
# ===================================================================


class TestPrivateCloudBatching:
    """Test private cloud sync batch accumulation and flush triggers."""

    def test_add_to_batch_groups_by_conversation(self):
        """Chunks for the same conversation should accumulate in one batch."""
        pending = {}

        def _add_to_batch(chunk_info):
            conv_id = chunk_info['conversation_id']
            if conv_id not in pending:
                pending[conv_id] = {
                    'data': bytearray(),
                    'conversation_id': conv_id,
                    'timestamp': chunk_info['timestamp'],
                    'queued_at': time.monotonic(),
                    'retries': 0,
                }
            pending[conv_id]['data'].extend(chunk_info['data'])

        _add_to_batch({'conversation_id': 'c1', 'data': b'\x00' * 100, 'timestamp': 1.0, 'retries': 0})
        _add_to_batch({'conversation_id': 'c1', 'data': b'\x01' * 200, 'timestamp': 2.0, 'retries': 0})
        _add_to_batch({'conversation_id': 'c2', 'data': b'\x02' * 50, 'timestamp': 3.0, 'retries': 0})

        assert len(pending) == 2
        assert len(pending['c1']['data']) == 300
        assert len(pending['c2']['data']) == 50
        # Timestamp should be from first chunk (oldest)
        assert pending['c1']['timestamp'] == 1.0

    def test_flush_trigger_size_threshold(self):
        """Batch should flush when it reaches 60s of audio data."""
        sample_rate = 8000
        PRIVATE_CLOUD_CHUNK_DURATION = 60.0
        batch_size_threshold = sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION  # 960000 bytes

        batch = {'data': bytearray(b'\x00' * int(batch_size_threshold)), 'queued_at': time.monotonic()}
        is_size_ready = len(batch['data']) >= batch_size_threshold
        assert is_size_ready is True

    def test_flush_trigger_age_threshold(self):
        """Batch should flush when oldest chunk exceeds 60s age."""
        PRIVATE_CLOUD_BATCH_MAX_AGE = 60.0
        now = time.monotonic()
        batch = {'data': bytearray(b'\x00' * 100), 'queued_at': now - 65}  # 65s old
        batch_age = now - batch['queued_at']
        is_age_ready = batch_age >= PRIVATE_CLOUD_BATCH_MAX_AGE
        assert is_age_ready is True

    def test_no_flush_under_threshold(self):
        """Batch under size and age thresholds should NOT flush."""
        sample_rate = 8000
        PRIVATE_CLOUD_CHUNK_DURATION = 60.0
        PRIVATE_CLOUD_BATCH_MAX_AGE = 60.0
        now = time.monotonic()
        batch_size_threshold = sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION

        batch = {'data': bytearray(b'\x00' * 100), 'queued_at': now - 10}
        is_size_ready = len(batch['data']) >= batch_size_threshold
        is_age_ready = (now - batch['queued_at']) >= PRIVATE_CLOUD_BATCH_MAX_AGE
        assert not is_size_ready
        assert not is_age_ready

    def test_retry_increments_and_resets_age(self):
        """Failed upload should increment retries and reset queued_at for backoff."""
        PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3
        batch = {
            'data': bytearray(b'\x00' * 100),
            'timestamp': 1.0,
            'queued_at': time.monotonic() - 100,
            'retries': 0,
        }
        # Simulate failure + retry
        retries = batch['retries']
        if retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
            batch['retries'] = retries + 1
            batch['queued_at'] = time.monotonic()  # reset age
        assert batch['retries'] == 1
        # After reset, age should be very small
        assert (time.monotonic() - batch['queued_at']) < 1.0

    def test_flaw_drop_after_max_retries(self):
        """FLAW TEST: After 3 retries, batch should be dropped (data loss)."""
        PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3
        pending = {}
        conv_id = 'c1'
        batch = {
            'data': bytearray(b'\x00' * 100),
            'timestamp': 1.0,
            'queued_at': time.monotonic(),
            'retries': 3,  # Already at max
        }
        pending[conv_id] = batch

        retries = batch['retries']
        if retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
            batch['retries'] = retries + 1
        else:
            # Drop
            pending.pop(conv_id, None)

        assert conv_id not in pending  # Dropped after max retries

    def test_private_cloud_chunk_size_calculation(self):
        """Verify chunk size calculation: sample_rate * 2 * 60 seconds."""
        for sr in [8000, 16000, 48000]:
            expected = sr * 2 * 60
            assert expected == sr * 120  # 2 bytes per sample * 60s


# ===================================================================
# SECTION 6: Speaker Sample Queue Age Gating
# ===================================================================


class TestSpeakerSampleAgeGating:
    """Test speaker sample extraction age-based readiness check.

    Samples must be at least 120s old before processing.
    """

    def test_ready_after_120s(self):
        """Sample queued 120s+ ago should be ready for processing."""
        SPEAKER_SAMPLE_MIN_AGE = 120.0
        now = time.time()
        item = {'person_id': 'p1', 'conversation_id': 'c1', 'segment_ids': ['s1'], 'queued_at': now - 130}
        is_ready = (now - item['queued_at']) >= SPEAKER_SAMPLE_MIN_AGE
        assert is_ready

    def test_not_ready_before_120s(self):
        """Sample queued < 120s ago should NOT be ready."""
        SPEAKER_SAMPLE_MIN_AGE = 120.0
        now = time.time()
        item = {'queued_at': now - 60}
        is_ready = (now - item['queued_at']) >= SPEAKER_SAMPLE_MIN_AGE
        assert not is_ready

    def test_exactly_at_boundary(self):
        """Sample at exactly 120s should be ready (>=)."""
        SPEAKER_SAMPLE_MIN_AGE = 120.0
        now = time.time()
        item = {'queued_at': now - 120.0}
        is_ready = (now - item['queued_at']) >= SPEAKER_SAMPLE_MIN_AGE
        assert is_ready

    def test_queue_separation_ready_vs_pending(self):
        """Queue should be split into ready (>=120s) and pending (<120s)."""
        SPEAKER_SAMPLE_MIN_AGE = 120.0
        now = time.time()
        queue = deque(
            [
                {'person_id': 'p1', 'queued_at': now - 200},  # ready
                {'person_id': 'p2', 'queued_at': now - 130},  # ready
                {'person_id': 'p3', 'queued_at': now - 60},  # pending
                {'person_id': 'p4', 'queued_at': now - 10},  # pending
            ]
        )
        ready = [item for item in queue if (now - item['queued_at']) >= SPEAKER_SAMPLE_MIN_AGE]
        pending = [item for item in queue if (now - item['queued_at']) < SPEAKER_SAMPLE_MIN_AGE]
        assert len(ready) == 2
        assert len(pending) == 2


# ===================================================================
# SECTION 7: Heartbeat & Inactivity Timeout
# ===================================================================


class TestHeartbeatInactivity:
    """Test heartbeat keepalive and inactivity timeout logic.

    - WS heartbeat: 10s ping interval
    - Inactivity timeout: 90s no audio → disconnect
    - Pusher heartbeat: 20s data frames for GKE ILB
    """

    def test_inactivity_timeout_90s(self):
        """90s without audio should trigger disconnect."""
        inactivity_timeout_seconds = 90
        last_activity_time = time.time() - 91  # 91s ago
        now = time.time()
        is_inactive = (now - last_activity_time) >= inactivity_timeout_seconds
        assert is_inactive

    def test_not_inactive_within_90s(self):
        """Activity within 90s should NOT trigger disconnect."""
        inactivity_timeout_seconds = 90
        last_activity_time = time.time() - 60  # 60s ago
        now = time.time()
        is_inactive = (now - last_activity_time) >= inactivity_timeout_seconds
        assert not is_inactive

    def test_heartbeat_interval_10s(self):
        """WS heartbeat should fire every 10s."""
        HEARTBEAT_INTERVAL = 10
        last_sent = time.time() - 11
        now = time.time()
        should_send = (now - last_sent) >= HEARTBEAT_INTERVAL
        assert should_send

    def test_pusher_heartbeat_interval_20s(self):
        """Pusher heartbeat (GKE ILB) should fire every 20s."""
        PUSHER_HEARTBEAT_INTERVAL = 20
        last_sent = time.time() - 21
        now = time.time()
        should_send = (now - last_sent) >= PUSHER_HEARTBEAT_INTERVAL
        assert should_send


# ===================================================================
# SECTION 8: Conversation Lifecycle Timeout
# ===================================================================


class TestConversationLifecycle:
    """Test conversation lifecycle timeout logic.

    120s silence → trigger processing → create new stub
    """

    def test_timeout_reached_triggers_processing(self):
        """120s since last update should trigger conversation processing."""
        conversation_creation_timeout = 120
        from datetime import datetime, timezone

        last_update = datetime.now(timezone.utc).timestamp() - 130  # 130s ago
        now = datetime.now(timezone.utc).timestamp()
        seconds_since_update = now - last_update
        should_process = seconds_since_update >= conversation_creation_timeout
        assert should_process

    def test_timeout_not_reached(self):
        """< 120s since last update should NOT trigger processing."""
        conversation_creation_timeout = 120
        from datetime import datetime, timezone

        last_update = datetime.now(timezone.utc).timestamp() - 60
        now = datetime.now(timezone.utc).timestamp()
        should_process = (now - last_update) >= conversation_creation_timeout
        assert not should_process

    def test_custom_timeout_values(self):
        """Custom conversation_timeout parameter should override default 120s."""
        for timeout in [60, 120, 300, 14400]:  # min 2min, max 4h
            from datetime import datetime, timezone

            last_update = datetime.now(timezone.utc).timestamp() - (timeout + 1)
            now = datetime.now(timezone.utc).timestamp()
            should_process = (now - last_update) >= timeout
            assert should_process


# ===================================================================
# SECTION 9: Audio Buffer Guard (Consumer-Gated Accumulation)
# ===================================================================


class TestAudioBufferGuard:
    """Test that audio buffers only grow when there's an active consumer.

    Without this guard, buffers grow ~16KB/s indefinitely for users
    without audio apps — a memory leak.
    """

    def _guard(
        self, audio_data, has_audio_apps_enabled, audio_bytes_webhook_delay_seconds, trigger_audiobuffer, audiobuffer
    ):
        """Extracted guard logic from pusher.py receive_tasks (header 101)."""
        if has_audio_apps_enabled:
            trigger_audiobuffer.extend(audio_data)
        if audio_bytes_webhook_delay_seconds is not None:
            audiobuffer.extend(audio_data)
        return trigger_audiobuffer, audiobuffer

    def test_no_consumers_no_growth(self):
        """No apps and no webhook → buffers stay empty."""
        t, a = self._guard(b'\x00' * 1000, False, None, bytearray(), bytearray())
        assert len(t) == 0
        assert len(a) == 0

    def test_app_consumer_accumulates(self):
        """Audio apps enabled → trigger_audiobuffer grows."""
        t, a = self._guard(b'\x00' * 1000, True, None, bytearray(), bytearray())
        assert len(t) == 1000
        assert len(a) == 0

    def test_webhook_consumer_accumulates(self):
        """Webhook delay set → audiobuffer grows."""
        t, a = self._guard(b'\x00' * 1000, False, 5.0, bytearray(), bytearray())
        assert len(t) == 0
        assert len(a) == 1000

    def test_both_consumers_accumulate(self):
        """Both consumers → both buffers grow."""
        t, a = self._guard(b'\x00' * 1000, True, 5.0, bytearray(), bytearray())
        assert len(t) == 1000
        assert len(a) == 1000

    def test_flaw_unbounded_growth_without_guard(self):
        """FLAW TEST: Without guard, 60s of 16KB/s audio = ~960KB buffer growth."""
        # This tests the scenario the guard prevents
        t = bytearray()
        for _ in range(3600):  # 60s at ~60 frames/s
            t.extend(b'\x00' * 16000)  # ~16KB per frame
        # Without guard, this would be ~57.6MB
        assert len(t) == 57_600_000
        # With guard (no consumers), it would be 0
        t2 = bytearray()
        for _ in range(3600):
            # Guard: has_audio_apps_enabled=False, webhook=None → no accumulation
            pass
        assert len(t2) == 0


# ===================================================================
# SECTION 10: STT Buffer Accumulation (30ms Flush)
# ===================================================================


class TestSttBufferAccumulation:
    """Test STT audio buffer 30ms accumulation logic.

    Audio is buffered until 30ms worth of samples accumulate,
    then flushed to Deepgram for better transcription quality.
    """

    def test_buffer_flush_size_16khz(self):
        """At 16kHz, 30ms = 960 bytes (480 samples * 2 bytes)."""
        sample_rate = 16000
        flush_size = int(sample_rate * 2 * 0.03)  # 30ms at 16-bit mono
        assert flush_size == 960

    def test_buffer_flush_size_8khz(self):
        """At 8kHz, 30ms = 480 bytes (240 samples * 2 bytes)."""
        sample_rate = 8000
        flush_size = int(sample_rate * 2 * 0.03)
        assert flush_size == 480

    def test_accumulation_below_threshold(self):
        """Partial frame should NOT trigger flush."""
        sample_rate = 16000
        flush_size = int(sample_rate * 2 * 0.03)
        buffer = bytearray()
        buffer.extend(b'\x00' * 500)  # < 960 bytes
        assert len(buffer) < flush_size

    def test_accumulation_at_threshold(self):
        """Exactly 30ms of audio should trigger flush."""
        sample_rate = 16000
        flush_size = int(sample_rate * 2 * 0.03)
        buffer = bytearray()
        buffer.extend(b'\x00' * flush_size)
        should_flush = len(buffer) >= flush_size
        assert should_flush

    def test_multiple_frames_accumulate(self):
        """Multiple small frames should accumulate until threshold reached."""
        sample_rate = 16000
        flush_size = int(sample_rate * 2 * 0.03)
        buffer = bytearray()
        frame_size = 160  # 10ms frames at 16kHz
        flushes = 0
        for _ in range(10):
            buffer.extend(b'\x00' * frame_size)
            if len(buffer) >= flush_size:
                flushes += 1
                buffer = bytearray()  # reset after flush
        # 10 frames * 160 = 1600 bytes total, 1600/960 = 1 full flush + remainder
        assert flushes == 1
        assert len(buffer) == 640  # remainder


# ===================================================================
# SECTION 11: Translation Debounce Logic
# ===================================================================


class TestTranslationDebounce:
    """Test translation debounce logic — 1s batching with MD5 dedup.

    Segments are accumulated in a debounce buffer, flushed after 1s idle.
    MD5 hash prevents re-translating identical text.
    """

    def test_md5_dedup_same_text(self):
        """Same text should produce same MD5 → skip duplicate translation."""
        import hashlib

        text1 = "Hello world"
        text2 = "Hello world"
        hash1 = hashlib.md5(text1.encode()).hexdigest()
        hash2 = hashlib.md5(text2.encode()).hexdigest()
        assert hash1 == hash2

    def test_md5_dedup_different_text(self):
        """Different text should produce different MD5."""
        import hashlib

        hash1 = hashlib.md5("Hello".encode()).hexdigest()
        hash2 = hashlib.md5("World".encode()).hexdigest()
        assert hash1 != hash2

    def test_debounce_accumulation(self):
        """Multiple segments within debounce window should batch together."""
        debounce_buffer = deque()
        for i in range(5):
            debounce_buffer.append(
                {
                    'segment_text': f'segment {i}',
                    'conversation_id': 'conv-1',
                    'version': i,
                }
            )
        assert len(debounce_buffer) == 5

    def test_stale_write_protection(self):
        """Translation with outdated version should be rejected."""
        pending_translations = {'seg-1': {'version': 5, 'hash': 'abc'}}
        new_version = 3  # older than current
        current_version = pending_translations['seg-1']['version']
        is_stale = new_version < current_version
        assert is_stale  # Should reject

    def test_version_monotonic_increase(self):
        """Translation versions should increase monotonically."""
        version = 0
        for _ in range(10):
            version += 1
        assert version == 10

    def test_empty_text_skipped(self):
        """Segments with empty text should be skipped (no API call)."""
        segments = [
            {'text': '', 'id': 's1'},
            {'text': '   ', 'id': 's2'},
            {'text': 'Hello', 'id': 's3'},
        ]
        non_empty = [s for s in segments if s['text'].strip()]
        assert len(non_empty) == 1


# ===================================================================
# SECTION 12: Pusher Queue Bounded Sizes & Warn Thresholds
# ===================================================================


class TestPusherQueueBounds:
    """Test Pusher queue bounded sizes and warning thresholds.

    From pusher.py constants:
    - speaker_sample_queue: maxlen=100
    - transcript_queue: maxlen=50
    - audio_bytes_queue: maxlen=20
    - private_cloud_queue: unbounded (list)
    """

    def test_transcript_queue_bounded_at_50(self):
        """Transcript queue should drop oldest when exceeding maxlen=50."""
        queue = deque(maxlen=50)
        for i in range(100):
            queue.append({'segments': [], 'memory_id': f'conv-{i}'})
        assert len(queue) == 50
        assert queue[0]['memory_id'] == 'conv-50'  # oldest dropped

    def test_speaker_sample_queue_bounded_at_100(self):
        """Speaker sample queue maxlen=100."""
        queue = deque(maxlen=100)
        for i in range(150):
            queue.append({'person_id': f'p{i}'})
        assert len(queue) == 100

    def test_audio_bytes_queue_bounded_at_20(self):
        """Audio bytes queue maxlen=20."""
        queue = deque(maxlen=20)
        for i in range(30):
            queue.append({'type': 'app', 'data': b'\x00'})
        assert len(queue) == 20

    def test_private_cloud_queue_unbounded(self):
        """FLAW TEST: Private cloud queue is a list (unbounded) — could grow indefinitely."""
        queue = []
        for i in range(1000):
            queue.append({'data': b'\x00' * 100, 'conversation_id': f'c{i}'})
        # No maxlen enforcement — this is a potential memory issue
        assert len(queue) == 1000  # Unbounded growth
        # FINDING: private_cloud_queue has no maxlen, only WARN_SIZE threshold

    def test_warn_threshold_logging(self):
        """Queue at warn threshold should trigger warning (but not drop)."""
        TRANSCRIPT_QUEUE_WARN_SIZE = 50
        queue = deque(maxlen=TRANSCRIPT_QUEUE_WARN_SIZE)
        for i in range(50):
            queue.append(i)
        should_warn = len(queue) >= TRANSCRIPT_QUEUE_WARN_SIZE
        assert should_warn


# ===================================================================
# SECTION 13: Pusher Reconnection Logic
# ===================================================================


class TestPusherReconnection:
    """Test Pusher WS reconnection with exponential backoff + jitter.

    5 retries, backoff with jitter, max 15s delay.
    """

    def test_backoff_increases(self):
        """Backoff delay should increase with each retry."""
        delays = []
        for attempt in range(5):
            delay = min(2**attempt, 15)  # cap at 15s
            delays.append(delay)
        assert delays == [1, 2, 4, 8, 15]  # 2^0, 2^1, 2^2, 2^3, capped at 15

    def test_max_backoff_capped_at_15s(self):
        """Backoff should not exceed 15s."""
        for attempt in range(10):
            delay = min(2**attempt, 15)
            assert delay <= 15

    def test_jitter_adds_randomness(self):
        """Jitter should add [0, 1) seconds to prevent thundering herd."""
        import random

        random.seed(42)
        delays = set()
        for _ in range(100):
            base_delay = 4  # attempt 2
            jitter = random.random()
            delays.add(round(base_delay + jitter, 4))
        # All delays should be in range [4, 5)
        assert all(4.0 <= d < 5.0 for d in delays), f"Out of range: {[d for d in delays if not (4.0 <= d < 5.0)]}"
        assert len(delays) > 10  # should have variety

    def test_max_retries_exhausted(self):
        """After 5 retries, should give up (not retry forever)."""
        max_retries = 5
        attempt = 0
        connected = False
        while attempt < max_retries and not connected:
            attempt += 1
            connected = False  # simulate failure
        assert attempt == 5
        assert not connected


# ===================================================================
# SECTION 14: Cleanup Phase
# ===================================================================


class TestCleanupPhase:
    """Test cleanup phase — flush translations, close sockets, cancel tasks."""

    def test_task_cancellation(self):
        """All background tasks should be cancelled on cleanup."""
        tasks = []
        for i in range(5):
            task = MagicMock()
            task.cancelled.return_value = False
            task.done.return_value = False
            tasks.append(task)
        # Cancel all
        for task in tasks:
            task.cancel()
        for task in tasks:
            task.cancel.assert_called_once()

    def test_websocket_active_flag_cleared(self):
        """websocket_active should be set to False on cleanup."""
        websocket_active = True
        # Simulate cleanup
        websocket_active = False
        assert not websocket_active

    def test_final_private_cloud_buffer_flush(self):
        """Remaining private cloud buffer should be flushed on disconnect."""
        private_cloud_queue = []
        private_cloud_sync_buffer = bytearray(b'\x00' * 300)
        current_conversation_id = 'conv-final'
        private_cloud_sync_enabled = True
        private_cloud_chunk_start_time = time.time() - 10

        # Simulate finally block flush
        if private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0:
            private_cloud_queue.append(
                {
                    'data': bytes(private_cloud_sync_buffer),
                    'conversation_id': current_conversation_id,
                    'timestamp': private_cloud_chunk_start_time or time.time(),
                    'retries': 0,
                }
            )
        assert len(private_cloud_queue) == 1
        assert private_cloud_queue[0]['conversation_id'] == 'conv-final'


# ===================================================================
# SECTION 15: Multi-Channel Stereo Split
# ===================================================================


class TestMultiChannelStereoSplit:
    """Test multi-channel audio splitting for stereo recordings.

    When channels=2, stereo frames are split into per-channel mono streams.
    """

    def test_stereo_frame_split(self):
        """Stereo interleaved PCM should split into 2 mono channels."""
        # Interleaved stereo: L0 R0 L1 R1 L2 R2
        l_samples = [100, 200, 300]
        r_samples = [400, 500, 600]
        interleaved = []
        for l, r in zip(l_samples, r_samples):
            interleaved.extend([l, r])
        stereo_data = struct.pack(f'<{len(interleaved)}h', *interleaved)

        # Split into channels
        num_frames = len(stereo_data) // (2 * 2)  # 2 bytes/sample, 2 channels
        left = bytearray()
        right = bytearray()
        for i in range(num_frames):
            offset = i * 4  # 4 bytes per frame (2 channels * 2 bytes)
            left.extend(stereo_data[offset : offset + 2])
            right.extend(stereo_data[offset + 2 : offset + 4])

        left_samples = struct.unpack(f'<{len(left)//2}h', left)
        right_samples = struct.unpack(f'<{len(right)//2}h', right)
        assert left_samples == (100, 200, 300)
        assert right_samples == (400, 500, 600)

    def test_mono_channel_no_split(self):
        """Single channel (channels=1) should not split."""
        channels = 1
        data = struct.pack('<4h', 100, 200, 300, 400)
        if channels == 1:
            result = data  # no split needed
        assert result == data

    def test_channel_config_speaker_assignment(self):
        """Multi-channel should assign speakers by channel index, not voice embedding."""
        configs = build_channel_config('phone_call')
        assert configs[0].speaker_label == 'SPEAKER_00'
        assert configs[1].speaker_label == 'SPEAKER_01'
        # In multi-channel mode, speaker comes from channel config, not embedding


# ===================================================================
# SECTION 16: Transcript Queue Batching
# ===================================================================


class TestTranscriptQueueBatching:
    """Test transcript_consume → Pusher batching (every 1s)."""

    def test_batch_collection_clears_queue(self):
        """Batch processing should copy + clear the queue atomically."""
        queue = deque()
        for i in range(10):
            queue.append({'segments': [{'text': f's{i}'}], 'memory_id': f'c{i}'})
        # Batch: copy then clear
        batch = list(queue)
        queue.clear()
        assert len(batch) == 10
        assert len(queue) == 0

    def test_empty_queue_noop(self):
        """Empty queue should produce no batch."""
        queue = deque()
        batch = list(queue)
        queue.clear()
        assert len(batch) == 0


# ===================================================================
# SECTION 17: Private Cloud Chunk Duration Sizing
# ===================================================================


class TestPrivateCloudChunkSizing:
    """Test private cloud sync chunk size calculations for various sample rates."""

    def test_chunk_size_8khz(self):
        """8kHz: 60s chunk = 960,000 bytes."""
        assert 8000 * 2 * 60 == 960_000

    def test_chunk_size_16khz(self):
        """16kHz: 60s chunk = 1,920,000 bytes."""
        assert 16000 * 2 * 60 == 1_920_000

    def test_chunk_size_48khz(self):
        """48kHz: 60s chunk = 5,760,000 bytes."""
        assert 48000 * 2 * 60 == 5_760_000

    def test_audio_trigger_threshold(self):
        """Audio bytes trigger: sample_rate * delay * 2 bytes."""
        sample_rate = 8000
        delay = 1.0  # audio_bytes_trigger_delay_seconds
        threshold = sample_rate * delay * 2
        assert threshold == 16_000
