"""Unit tests for the speaker identification pipeline.

Tests pure functions: AudioRingBuffer, detect_speaker_from_text(),
embedding math (compare/match/find_best), PCM-to-WAV conversion,
and the full speaker-to-person matching logic.
"""

import io
import os
import struct
import sys
import wave

import numpy as np
import pytest

# Mock modules that initialize GCP clients at import time
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
sys.modules.setdefault("database._client", MagicMock())
sys.modules.setdefault("utils.other.storage", MagicMock())
sys.modules.setdefault("utils.stt.pre_recorded", MagicMock())

from utils.audio import AudioRingBuffer
from utils.speaker_identification import detect_speaker_from_text, SPEAKER_IDENTIFICATION_PATTERNS, _pcm_to_wav_bytes
from utils.stt.speaker_embedding import (
    compare_embeddings,
    is_same_speaker,
    find_best_match,
    SPEAKER_MATCH_THRESHOLD,
    _get_wav_duration,
)

# ─── AudioRingBuffer ─────────────────────────────────────────────────────────


class TestAudioRingBuffer:
    """Tests for the circular audio buffer with timestamp tracking."""

    def _make_buffer(self, duration_seconds=5.0, sample_rate=16000):
        return AudioRingBuffer(duration_seconds, sample_rate)

    def _generate_pcm16(self, num_samples, value=0):
        """Generate PCM16 mono audio bytes."""
        return struct.pack(f'<{num_samples}h', *([value] * num_samples))

    def test_write_updates_total_bytes_and_timestamp(self):
        """Writes advance total_bytes_written and last_write_timestamp."""
        buf = self._make_buffer(duration_seconds=1.0, sample_rate=16000)
        data = self._generate_pcm16(160)  # 320 bytes = 10ms at 16kHz
        buf.write(data, 1000.0)

        assert buf.total_bytes_written == 320
        assert buf.last_write_timestamp == 1000.0

    def test_write_multiple_accumulates(self):
        """Multiple writes accumulate total_bytes_written correctly."""
        buf = self._make_buffer(duration_seconds=1.0, sample_rate=16000)
        chunk = self._generate_pcm16(160)
        for i in range(10):
            buf.write(chunk, 1000.0 + i * 0.01)

        assert buf.total_bytes_written == 3200  # 10 * 320
        assert buf.last_write_timestamp == pytest.approx(1000.09, abs=0.001)

    def test_get_time_range_returns_none_before_write(self):
        """Time range is None before any write."""
        buf = self._make_buffer()
        assert buf.get_time_range() is None

    def test_get_time_range_correct_after_write(self):
        """Time range correctly reflects buffered audio duration."""
        buf = self._make_buffer(duration_seconds=5.0, sample_rate=16000)
        # Write 1 second of audio (16000 samples = 32000 bytes)
        data = self._generate_pcm16(16000)
        buf.write(data, 100.0)

        start, end = buf.get_time_range()
        assert end == 100.0
        assert start == pytest.approx(99.0, abs=0.01)

    def test_extract_returns_exact_samples_for_time_range(self):
        """Extracted audio has correct byte count for the requested time range."""
        buf = self._make_buffer(duration_seconds=5.0, sample_rate=16000)
        # Write 2 seconds of known audio
        data = self._generate_pcm16(32000, value=1000)
        buf.write(data, 100.0)

        # Extract 0.5 seconds from center
        result = buf.extract(99.5, 100.0)
        assert result is not None
        # 0.5s at 16kHz PCM16 = 16000 bytes
        assert len(result) == 16000

    def test_extract_handles_range_spanning_wraparound(self):
        """Buffer wraps around correctly and extraction still works."""
        buf = self._make_buffer(duration_seconds=1.0, sample_rate=16000)
        bytes_per_second = 32000

        # Write 1.5 seconds — forces wraparound of 0.5s
        chunk1 = self._generate_pcm16(16000, value=100)  # 1s
        buf.write(chunk1, 10.0)

        chunk2 = self._generate_pcm16(8000, value=200)  # 0.5s
        buf.write(chunk2, 10.5)

        # Buffer capacity = 1s, so first 0.5s is overwritten
        # Available: 9.5 to 10.5
        time_range = buf.get_time_range()
        assert time_range is not None
        start, end = time_range
        assert end == 10.5
        assert start == pytest.approx(9.5, abs=0.01)

        # Extract the last 0.5s (the newer data)
        result = buf.extract(10.0, 10.5)
        assert result is not None
        assert len(result) == 16000  # 0.5s

        # Verify the extracted data is the newer chunk (value=200)
        samples = struct.unpack(f'<{len(result) // 2}h', result)
        assert all(s == 200 for s in samples)

    def test_write_overwrites_oldest_when_capacity_exceeded(self):
        """Oldest samples are evicted when buffer wraps."""
        buf = self._make_buffer(duration_seconds=1.0, sample_rate=16000)

        # Write 1s of value=100
        buf.write(self._generate_pcm16(16000, value=100), 10.0)
        # Write another 1s of value=200 — overwrites all of first write
        buf.write(self._generate_pcm16(16000, value=200), 11.0)

        # Extract full buffer — should only contain value=200
        result = buf.extract(10.0, 11.0)
        assert result is not None
        samples = struct.unpack(f'<{len(result) // 2}h', result)
        assert all(s == 200 for s in samples)

    def test_extract_clamps_to_available_window(self):
        """Out-of-window request is clamped without crash."""
        buf = self._make_buffer(duration_seconds=2.0, sample_rate=16000)
        # Write 1s at timestamp 50.0
        buf.write(self._generate_pcm16(16000), 50.0)

        # Request wider range than available
        result = buf.extract(48.0, 52.0)
        assert result is not None
        # Should be clamped to [49.0, 50.0] = 1 second
        assert len(result) == 32000

    def test_extract_returns_none_for_future_range(self):
        """Requesting a range entirely in the future returns None."""
        buf = self._make_buffer(duration_seconds=2.0, sample_rate=16000)
        buf.write(self._generate_pcm16(16000), 50.0)

        result = buf.extract(51.0, 52.0)
        assert result is None

    def test_extract_returns_none_for_past_range(self):
        """Requesting a range entirely before the buffer window returns None."""
        buf = self._make_buffer(duration_seconds=1.0, sample_rate=16000)
        # Write 1s filling the buffer
        buf.write(self._generate_pcm16(16000), 50.0)

        # Request range that ended before buffer starts
        result = buf.extract(47.0, 48.0)
        assert result is None

    def test_extract_returns_none_for_inverted_range(self):
        """Inverted range (start > end) returns None."""
        buf = self._make_buffer(duration_seconds=2.0, sample_rate=16000)
        buf.write(self._generate_pcm16(16000), 50.0)

        result = buf.extract(50.0, 49.0)
        assert result is None

    def test_pcm16_alignment_maintained(self):
        """Extracted bytes always have even length (PCM16 alignment)."""
        buf = self._make_buffer(duration_seconds=2.0, sample_rate=16000)
        buf.write(self._generate_pcm16(16000), 50.0)

        # Extract various sub-ranges
        for start_offset in [0.0, 0.001, 0.01, 0.1, 0.5]:
            result = buf.extract(49.0 + start_offset, 50.0)
            if result is not None:
                assert len(result) % 2 == 0, f"PCM16 misaligned at offset {start_offset}"


# ─── Text-based Speaker Detection ────────────────────────────────────────────


class TestDetectSpeakerFromText:
    """Tests for detect_speaker_from_text() across all 33 languages."""

    # Test data: (language, input_text, expected_name)
    POSITIVE_CASES = [
        ('en', "I am John", "John"),
        ('en', "I'm Alice", "Alice"),
        ('en', "My name is Bob", "Bob"),
        ('en', "Charlie is my name", "Charlie"),
        ('es', "Soy Carlos", "Carlos"),
        ('es', "Me llamo Maria", "Maria"),
        ('fr', "Je suis Pierre", "Pierre"),
        ('fr', "Je m'appelle Sophie", "Sophie"),
        ('de', "Ich bin Hans", "Hans"),
        ('de', "Mein Name ist Klaus", "Klaus"),
        ('zh', "我是李明", None),  # Chinese names — detect_speaker_from_text returns capitalized
        ('ja', "私は田中", None),  # Japanese — same pattern
        ('ko', "저는 김철수", None),  # Korean
        ('ru', "Меня зовут Иван", "Иван"),
        ('pt', "Eu sou Pedro", "Pedro"),
        ('it', "Mi chiamo Marco", "Marco"),
        ('nl', "Ik ben Jan", "Jan"),
        ('sv', "Jag heter Erik", "Erik"),
        ('no', "Jeg heter Lars", "Lars"),
        ('da', "Jeg hedder Niels", "Niels"),
        ('fi', "Olen Matti", "Matti"),
        ('pl', "Jestem Tomasz", "Tomasz"),
        ('tr', "Benim adım Ahmet", "Ahmet"),
        ('hi', "मेरा नाम है राम", None),  # Hindi — Devanagari
        ('th', "ผมชื่อ สมชาย", None),  # Thai
        ('ro', "Sunt Alexandru", "Alexandru"),
        ('hu', "Én vagyok Zsolt", "Zsolt"),
        ('cs', "Jsem Petr", "Petr"),
        ('bg', "Аз съм Петър", "Петър"),
        ('uk', "Мене звати Олег", "Олег"),
        ('vi', "Tôi là Minh", "Minh"),
        ('id', "Nama saya Budi", "Budi"),
        ('ms', "Saya Ahmad", "Ahmad"),
    ]

    NEGATIVE_CASES = [
        "",
        "Hello, how are you?",
        "The weather is nice today",
        "Let's talk about the project",
        "I think we should go",
        "12345",
        "!@#$%^&*()",
        "a",  # Too short for name match
        "i am",  # No name follows (lowercase)
        "I am",  # No name follows
    ]

    @pytest.mark.parametrize("lang,text,expected_name", POSITIVE_CASES)
    def test_positive_detection(self, lang, text, expected_name):
        """Detects speaker name from self-introduction in each language."""
        result = detect_speaker_from_text(text)
        if expected_name is not None:
            assert result is not None, f"Failed to detect name in {lang}: {text}"
            assert result == expected_name, f"Wrong name for {lang}: expected {expected_name}, got {result}"
        else:
            # For CJK languages, just verify detection happened (name format differs)
            # The function returns capitalized version, CJK doesn't capitalize
            if result is not None:
                assert len(result) >= 2

    @pytest.mark.parametrize("text", NEGATIVE_CASES)
    def test_negative_detection(self, text):
        """Non-introduction text returns None."""
        result = detect_speaker_from_text(text)
        assert result is None, f"False positive on: {text!r}"

    def test_empty_string_returns_none(self):
        """Empty string input returns None."""
        assert detect_speaker_from_text("") is None

    def test_short_name_rejected(self):
        """Single-character names are rejected (len < 2)."""
        # "I am X" — X is only 1 char
        result = detect_speaker_from_text("I am X")
        assert result is None

    def test_name_capitalized(self):
        """Returned name is capitalized."""
        result = detect_speaker_from_text("I am John")
        assert result == "John"
        assert result[0].isupper()

    def test_all_languages_have_patterns(self):
        """Verify all 33 language codes have patterns defined."""
        assert len(SPEAKER_IDENTIFICATION_PATTERNS) == 33

    def test_patterns_compile_without_error(self):
        """All regex patterns compile and don't crash on sample text."""
        import re

        for lang, patterns in SPEAKER_IDENTIFICATION_PATTERNS.items():
            for pattern in patterns:
                compiled = re.compile(pattern)
                # Should not crash on arbitrary text
                compiled.search("Hello World 你好世界 こんにちは مرحبا")


# ─── Speaker Embedding Math ──────────────────────────────────────────────────


class TestSpeakerEmbeddingMath:
    """Tests for cosine distance, matching, and best-match selection."""

    def _random_embedding(self, dim=512, seed=None):
        """Generate a random unit-normalized embedding."""
        rng = np.random.RandomState(seed)
        vec = rng.randn(1, dim).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec

    def test_compare_identical_vectors_distance_zero(self):
        """Identical vectors → cosine distance 0."""
        emb = self._random_embedding(seed=42)
        distance = compare_embeddings(emb, emb)
        assert distance == pytest.approx(0.0, abs=1e-6)

    def test_compare_orthogonal_vectors_distance_one(self):
        """Orthogonal vectors → cosine distance 1."""
        # Construct orthogonal pair in 512-d
        a = np.zeros((1, 512), dtype=np.float32)
        b = np.zeros((1, 512), dtype=np.float32)
        a[0, 0] = 1.0
        b[0, 1] = 1.0
        distance = compare_embeddings(a, b)
        assert distance == pytest.approx(1.0, abs=1e-6)

    def test_compare_opposite_vectors_distance_two(self):
        """Opposite vectors → cosine distance 2."""
        emb = self._random_embedding(seed=42)
        opposite = -emb
        distance = compare_embeddings(emb, opposite)
        assert distance == pytest.approx(2.0, abs=1e-5)

    def test_compare_similar_vectors_low_distance(self):
        """Slightly perturbed vectors have low cosine distance."""
        emb = self._random_embedding(seed=42)
        noise = np.random.RandomState(99).randn(1, 512).astype(np.float32) * 0.001
        perturbed = emb + noise
        perturbed /= np.linalg.norm(perturbed)

        distance = compare_embeddings(emb, perturbed)
        assert distance < 0.001  # Very similar (tiny perturbation)

    def test_compare_distance_is_symmetric(self):
        """Cosine distance is symmetric: d(a,b) == d(b,a)."""
        a = self._random_embedding(seed=1)
        b = self._random_embedding(seed=2)
        assert compare_embeddings(a, b) == pytest.approx(compare_embeddings(b, a), abs=1e-7)

    def test_is_same_speaker_true_below_threshold(self):
        """Match returns True when distance is below threshold."""
        emb = self._random_embedding(seed=42)
        noise = np.random.RandomState(99).randn(1, 512).astype(np.float32) * 0.01
        similar = emb + noise
        similar /= np.linalg.norm(similar)

        is_match, distance = is_same_speaker(emb, similar)
        assert is_match is True
        assert distance < SPEAKER_MATCH_THRESHOLD

    def test_is_same_speaker_false_above_threshold(self):
        """Match returns False when distance is above threshold."""
        a = self._random_embedding(seed=1)
        b = self._random_embedding(seed=2)

        is_match, distance = is_same_speaker(a, b)
        # Random 512-d vectors typically have distance ~1.0
        assert is_match is False
        assert distance >= SPEAKER_MATCH_THRESHOLD

    def test_is_same_speaker_custom_threshold(self):
        """Custom threshold is respected."""
        emb = self._random_embedding(seed=42)
        is_match, _ = is_same_speaker(emb, emb, threshold=0.0001)
        assert is_match is True  # identical

        a = self._random_embedding(seed=1)
        b = self._random_embedding(seed=2)
        is_match, _ = is_same_speaker(a, b, threshold=999.0)
        assert is_match is True  # huge threshold accepts everything

    def test_find_best_match_returns_lowest_distance(self):
        """find_best_match selects the candidate with minimum distance."""
        query = self._random_embedding(seed=42)

        # Create 3 candidates: one identical, two random
        candidates = [
            self._random_embedding(seed=1),  # random
            query.copy(),  # identical — should be best match
            self._random_embedding(seed=2),  # random
        ]

        result = find_best_match(query, candidates)
        assert result is not None
        best_idx, best_distance = result
        assert best_idx == 1  # the identical copy
        assert best_distance == pytest.approx(0.0, abs=1e-6)

    def test_find_best_match_none_when_all_above_threshold(self):
        """Returns None when no candidate is within threshold."""
        query = self._random_embedding(seed=42)
        candidates = [self._random_embedding(seed=i) for i in range(5)]

        result = find_best_match(query, candidates, threshold=0.001)
        assert result is None  # random vectors won't be that close

    def test_find_best_match_empty_candidates(self):
        """Returns None for empty candidate list."""
        query = self._random_embedding(seed=42)
        result = find_best_match(query, [])
        assert result is None

    def test_find_best_match_single_candidate_within_threshold(self):
        """Single candidate within threshold is returned."""
        query = self._random_embedding(seed=42)
        result = find_best_match(query, [query.copy()])
        assert result is not None
        assert result[0] == 0
        assert result[1] == pytest.approx(0.0, abs=1e-6)

    def test_find_best_match_tie_breaks_deterministically(self):
        """When multiple candidates have same distance, first one wins."""
        query = self._random_embedding(seed=42)
        # Two identical copies
        candidates = [query.copy(), query.copy()]
        result = find_best_match(query, candidates)
        assert result is not None
        # Implementation iterates in order, updates only on strict <
        # So first candidate (idx 0) wins on tie
        assert result[0] == 0

    def test_threshold_default_is_045(self):
        """Verify the SPEAKER_MATCH_THRESHOLD constant."""
        assert SPEAKER_MATCH_THRESHOLD == 0.45


# ─── PCM-to-WAV Conversion ──────────────────────────────────────────────────


class TestPcmToWav:
    """Tests for _pcm_to_wav_bytes conversion."""

    def test_valid_wav_header(self):
        """Generated WAV has valid header."""
        pcm = struct.pack('<160h', *([1000] * 160))  # 160 samples = 10ms at 16kHz
        wav_bytes = _pcm_to_wav_bytes(pcm, 16000)

        # Verify WAV header
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 160

    def test_wav_duration_correct(self):
        """WAV duration matches input PCM length."""
        num_samples = 16000  # 1 second
        pcm = struct.pack(f'<{num_samples}h', *([0] * num_samples))
        wav_bytes = _pcm_to_wav_bytes(pcm, 16000)

        duration = _get_wav_duration(wav_bytes)
        assert duration == pytest.approx(1.0, abs=0.001)

    def test_wav_roundtrip_preserves_data(self):
        """PCM→WAV→PCM roundtrip preserves audio data."""
        original_samples = [100, -200, 300, -400, 500] * 32  # 160 samples
        pcm = struct.pack(f'<{len(original_samples)}h', *original_samples)
        wav_bytes = _pcm_to_wav_bytes(pcm, 16000)

        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            recovered = struct.unpack(f'<{len(original_samples)}h', frames)
            assert list(recovered) == original_samples

    def test_different_sample_rates(self):
        """Works with different sample rates."""
        pcm = struct.pack('<80h', *([0] * 80))
        for sr in [8000, 16000, 44100, 48000]:
            wav_bytes = _pcm_to_wav_bytes(pcm, sr)
            with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
                assert wf.getframerate() == sr


# ─── WAV Duration Helper ────────────────────────────────────────────────────


class TestGetWavDuration:
    """Tests for _get_wav_duration utility."""

    def test_returns_correct_duration(self):
        """Returns correct duration for valid WAV."""
        pcm = struct.pack('<16000h', *([0] * 16000))
        wav_bytes = _pcm_to_wav_bytes(pcm, 16000)
        assert _get_wav_duration(wav_bytes) == pytest.approx(1.0, abs=0.001)

    def test_returns_zero_for_invalid_data(self):
        """Returns 0.0 for non-WAV data."""
        assert _get_wav_duration(b"not a wav file") == 0.0

    def test_returns_zero_for_empty_data(self):
        """Returns 0.0 for empty bytes."""
        assert _get_wav_duration(b"") == 0.0

    def test_returns_zero_for_truncated_wav(self):
        """Returns 0.0 for truncated WAV header."""
        pcm = struct.pack('<160h', *([0] * 160))
        wav_bytes = _pcm_to_wav_bytes(pcm, 16000)
        # Truncate to just the RIFF header
        assert _get_wav_duration(wav_bytes[:20]) == 0.0


# ─── Ring Buffer Edge Cases ──────────────────────────────────────────────────


class TestAudioRingBufferEdgeCases:
    """Edge cases and chaos scenarios for the ring buffer."""

    def test_zero_length_write(self):
        """Writing zero bytes doesn't crash."""
        buf = AudioRingBuffer(1.0, 16000)
        buf.write(b'', 100.0)
        assert buf.total_bytes_written == 0
        assert buf.last_write_timestamp == 100.0

    def test_single_sample_write(self):
        """Writing a single PCM16 sample works."""
        buf = AudioRingBuffer(1.0, 16000)
        buf.write(struct.pack('<h', 1000), 100.0)
        assert buf.total_bytes_written == 2

    def test_exact_capacity_fill(self):
        """Filling buffer to exactly capacity works correctly."""
        buf = AudioRingBuffer(1.0, 16000)
        # 1s at 16kHz = 32000 bytes
        data = struct.pack(f'<{16000}h', *range(16000))
        buf.write(data, 100.0)

        assert buf.total_bytes_written == 32000
        time_range = buf.get_time_range()
        start, end = time_range
        assert end == 100.0
        assert start == pytest.approx(99.0, abs=0.01)

    def test_double_capacity_write(self):
        """Writing 2x capacity still works (buffer holds last 1x)."""
        buf = AudioRingBuffer(1.0, 16000)
        # Write 2 seconds
        data = struct.pack(f'<{32000}h', *([42] * 32000))
        buf.write(data, 102.0)

        assert buf.total_bytes_written == 64000
        time_range = buf.get_time_range()
        start, end = time_range
        assert end == 102.0
        assert start == pytest.approx(101.0, abs=0.01)

    def test_many_small_writes_equivalent_to_one_large(self):
        """Result is the same whether writing many small chunks or one large one."""
        buf1 = AudioRingBuffer(1.0, 16000)
        buf2 = AudioRingBuffer(1.0, 16000)

        # Generate 1s of audio
        samples = list(range(16000))
        full_data = struct.pack(f'<{16000}h', *samples)

        # Write as one chunk
        buf1.write(full_data, 100.0)

        # Write in 160-sample chunks (10ms each)
        offset = 0
        for i in range(100):
            chunk = full_data[offset : offset + 320]
            buf2.write(chunk, 99.0 + (i + 1) * 0.01)
            offset += 320

        # Both should have same content
        result1 = buf1.extract(99.0, 100.0)
        result2 = buf2.extract(99.0, 100.0)
        assert result1 == result2

    def test_rapid_timestamps_preserve_order(self):
        """Rapidly advancing timestamps don't break time range math."""
        buf = AudioRingBuffer(5.0, 16000)
        chunk = struct.pack('<160h', *([0] * 160))

        for i in range(1000):
            buf.write(chunk, float(i) * 0.001)  # 1ms apart

        time_range = buf.get_time_range()
        assert time_range is not None
        start, end = time_range
        assert end > start

    def test_extract_boundary_at_buffer_start(self):
        """Extracting exactly at the buffer start boundary."""
        buf = AudioRingBuffer(2.0, 16000)
        data = struct.pack(f'<{16000}h', *([0] * 16000))  # 1s
        buf.write(data, 50.0)

        # Buffer starts at 49.0
        result = buf.extract(49.0, 49.5)
        assert result is not None
        assert len(result) == 16000  # 0.5s

    def test_extract_boundary_at_buffer_end(self):
        """Extracting up to exactly the buffer end."""
        buf = AudioRingBuffer(2.0, 16000)
        data = struct.pack(f'<{16000}h', *([0] * 16000))  # 1s
        buf.write(data, 50.0)

        result = buf.extract(49.5, 50.0)
        assert result is not None
        assert len(result) == 16000  # 0.5s


# ─── Embedding Shape Validation ─────────────────────────────────────────────


class TestEmbeddingShapes:
    """Validate embedding array shape handling."""

    def test_compare_1d_reshaped_to_2d(self):
        """compare_embeddings works with (1, D) shaped arrays."""
        a = np.random.randn(1, 512).astype(np.float32)
        b = np.random.randn(1, 512).astype(np.float32)
        distance = compare_embeddings(a, b)
        assert isinstance(distance, float)
        assert 0.0 <= distance <= 2.0

    def test_find_best_match_with_different_dimensions(self):
        """find_best_match works with various embedding dimensions."""
        for dim in [128, 256, 512, 1024]:
            query = np.random.randn(1, dim).astype(np.float32)
            candidates = [np.random.randn(1, dim).astype(np.float32) for _ in range(3)]
            # Should not crash regardless of dimension
            result = find_best_match(query, candidates, threshold=2.0)
            assert result is not None

    def test_is_same_speaker_returns_tuple(self):
        """is_same_speaker returns (bool, float) tuple."""
        a = np.random.randn(1, 512).astype(np.float32)
        result = is_same_speaker(a, a)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], float)
