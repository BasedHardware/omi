"""
DER regression gate -- run INSIDE the built container with GPU.

Generates synthetic multi-speaker audio, passes pre-built segment
boundaries to transcribe_file_v2 (bypassing GPU worker), and tests
that the diarization pipeline produces DER below the regression threshold.

No external dependencies (no Deepgram, no L2 audio files, no GCS).
Uses synthesized two-speaker audio with distinct frequency profiles.

Usage (inside container, GPU required):
    python -m pytest tests/container/test_parakeet_der_gate.py -v -s

Or standalone:
    python tests/container/test_parakeet_der_gate.py
"""

import io
import json
import math
import os
import struct
import sys
import tempfile
import wave

import numpy as np
import pytest

DER_THRESHOLD = 12.0
SAMPLE_RATE = 16000
SEGMENT_DURATION = 5.0
NUM_SEGMENTS_PER_SPEAKER = 3
TOTAL_SPEAKERS = 2


def _generate_tone(freq_hz, duration_s, sample_rate=SAMPLE_RATE, amplitude=0.3):
    """Generate a sine wave tone at given frequency."""
    n_samples = int(duration_s * sample_rate)
    t = np.arange(n_samples) / sample_rate
    samples = (amplitude * np.sin(2 * math.pi * freq_hz * t)).astype(np.float32)
    return (samples * 32767).astype(np.int16)


def _generate_two_speaker_wav():
    """Create WAV with two alternating 'speakers' using different frequency profiles.

    Speaker 0: 200 Hz fundamental + harmonics (male-like)
    Speaker 1: 350 Hz fundamental + harmonics (female-like)
    """
    speaker_freqs = [
        [200, 400, 600],
        [350, 700, 1050],
    ]

    all_samples = []
    ground_truth = []
    t_offset = 0.0

    for seg_idx in range(NUM_SEGMENTS_PER_SPEAKER * TOTAL_SPEAKERS):
        spk_idx = seg_idx % TOTAL_SPEAKERS
        freqs = speaker_freqs[spk_idx]

        segment = np.zeros(int(SEGMENT_DURATION * SAMPLE_RATE), dtype=np.float32)
        for f in freqs:
            tone = _generate_tone(f, SEGMENT_DURATION, amplitude=0.15)
            segment += tone.astype(np.float32)

        segment = np.clip(segment, -32767, 32767).astype(np.int16)
        all_samples.append(segment)

        ground_truth.append(
            {
                "start": t_offset,
                "end": t_offset + SEGMENT_DURATION,
                "speaker": f"SPEAKER_{spk_idx}",
            }
        )
        t_offset += SEGMENT_DURATION

    combined = np.concatenate(all_samples)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(combined.tobytes())

    return buf.getvalue(), ground_truth, t_offset


def _compute_der(ref_turns, hyp_turns, total_duration, collar=0.25):
    """Frame-level DER computation with collar."""
    resolution = 0.01
    num_frames = int(total_duration / resolution) + 1

    ref_labels = [""] * num_frames
    hyp_labels = [""] * num_frames

    for turn in ref_turns:
        s = int(turn["start"] / resolution)
        e = int(turn["end"] / resolution)
        for i in range(max(0, s), min(num_frames, e)):
            ref_labels[i] = turn["speaker"]

    for turn in hyp_turns:
        s = int(turn["start"] / resolution)
        e = int(turn["end"] / resolution)
        for i in range(max(0, s), min(num_frames, e)):
            hyp_labels[i] = turn["speaker"]

    scored_frames = set()
    for turn in ref_turns:
        s = int((turn["start"] + collar) / resolution)
        e = int((turn["end"] - collar) / resolution)
        for i in range(max(0, s), min(num_frames, e)):
            scored_frames.add(i)

    if not scored_frames:
        return 0.0

    ref_speakers = set(t["speaker"] for t in ref_turns)
    hyp_speakers = set(t["speaker"] for t in hyp_turns)
    mapping = _best_speaker_mapping(ref_labels, hyp_labels, hyp_speakers, scored_frames)

    miss = fa = confusion = 0
    for i in scored_frames:
        r = ref_labels[i]
        h = hyp_labels[i]
        mapped_h = mapping.get(h, h) if h else ""
        if r and not h:
            miss += 1
        elif not r and h:
            fa += 1
        elif r and h and r != mapped_h:
            confusion += 1

    return round((miss + fa + confusion) / len(scored_frames) * 100, 1)


def _best_speaker_mapping(ref_labels, hyp_labels, hyp_speakers, scored_frames):
    from collections import defaultdict

    overlap = defaultdict(lambda: defaultdict(int))
    for i in scored_frames:
        r, h = ref_labels[i], hyp_labels[i]
        if r and h:
            overlap[h][r] += 1

    mapping = {}
    used = set()
    for h in sorted(overlap, key=lambda x: -max(overlap[x].values()) if overlap[x] else 0):
        best = max(overlap[h], key=overlap[h].get)
        if best not in used:
            mapping[h] = best
            used.add(best)
    return mapping


def _build_gpu_result(ground_truth, total_dur):
    """Build a synthetic gpu_result dict matching _transcribe_from_gpu_result format.

    Bypasses the GPU worker (not available in raw pytest) so we only test diarization.
    """
    segments = []
    for gt in ground_truth:
        segments.append(
            {
                "segment": f"speaker {gt['speaker']} segment",
                "start": gt["start"],
                "end": gt["end"],
            }
        )
    return {
        "text": " ".join(s["segment"] for s in segments),
        "timestamp": {"segment": segments},
    }


try:
    import torch

    _has_gpu = torch.cuda.is_available()
except ImportError:
    _has_gpu = False


@pytest.mark.skipif(not _has_gpu, reason="No GPU")
class TestDERRegressionGate:
    """DER must stay below threshold with built-in embedding model."""

    def test_builtin_diarization_der_below_threshold(self):
        from gpu_worker import GPUWorker
        from transcribe import has_builtin_embedding, set_gpu_worker, transcribe_file_v2

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)
        set_gpu_worker(worker)
        tmp_path = None
        try:
            assert has_builtin_embedding(), "Built-in embedding model failed to load on GPU worker"

            wav_bytes, ground_truth, total_dur = _generate_two_speaker_wav()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name

            os.environ.pop("HOSTED_SPEAKER_EMBEDDING_API_URL", None)
            gpu_result = _build_gpu_result(ground_truth, total_dur)
            result = transcribe_file_v2(tmp_path, gpu_result=gpu_result, diarize=True)

            hyp_turns = []
            for seg in result["segments"]:
                hyp_turns.append(
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "speaker": seg.get("speaker", "SPEAKER_0"),
                    }
                )

            der = _compute_der(ground_truth, hyp_turns, total_dur)
            print(f"\n  DER: {der}% (threshold: {DER_THRESHOLD}%)")
            print(f"  Ref speakers: {TOTAL_SPEAKERS}, Hyp speakers: {len(set(s['speaker'] for s in hyp_turns))}")
            print(f"  Segments: {len(result['segments'])}")

            assert der <= DER_THRESHOLD, (
                f"DER {der}% exceeds threshold {DER_THRESHOLD}%. " f"Diarization quality has regressed."
            )
        finally:
            if tmp_path:
                os.unlink(tmp_path)
            worker.stop()

    def test_single_speaker_no_false_splits(self):
        """Single-speaker audio should not be split into multiple speakers."""
        from gpu_worker import GPUWorker
        from transcribe import has_builtin_embedding, set_gpu_worker, transcribe_file_v2

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)
        set_gpu_worker(worker)
        tmp_path = None
        try:
            if not has_builtin_embedding():
                pytest.skip("Model not available")

            tone = _generate_tone(250, 5.0)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(tone.tobytes())

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(buf.getvalue())
                tmp_path = f.name

            os.environ.pop("HOSTED_SPEAKER_EMBEDDING_API_URL", None)
            gpu_result = {
                "text": "single speaker test",
                "timestamp": {
                    "segment": [{"segment": "single speaker test", "start": 0.0, "end": 5.0}],
                },
            }
            result = transcribe_file_v2(tmp_path, gpu_result=gpu_result, diarize=True)
            assert len(result["segments"]) > 0, "Expected at least one segment"
            speakers = set(s.get("speaker", "SPEAKER_0") for s in result["segments"])
            assert len(speakers) <= 1, f"Single-speaker audio was split into {len(speakers)} speakers: {speakers}"
        finally:
            if tmp_path:
                os.unlink(tmp_path)
            worker.stop()


if __name__ == "__main__":
    print(f"DER Regression Gate (threshold: {DER_THRESHOLD}%)")
    print(f"Generating {TOTAL_SPEAKERS}-speaker synthetic audio...")

    wav_bytes, ground_truth, total_dur = _generate_two_speaker_wav()
    print(f"  Duration: {total_dur}s, Segments: {len(ground_truth)}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp_path = f.name

    try:
        from gpu_worker import GPUWorker
        from transcribe import has_builtin_embedding, set_gpu_worker, transcribe_file_v2

        worker = GPUWorker()
        worker.start()
        worker.wait_ready(timeout=300)
        set_gpu_worker(worker)
        if not has_builtin_embedding():
            print("FAIL: Built-in embedding model did not load on GPU worker")
            worker.stop()
            sys.exit(1)

        os.environ.pop("HOSTED_SPEAKER_EMBEDDING_API_URL", None)
        gpu_result = _build_gpu_result(ground_truth, total_dur)
        result = transcribe_file_v2(tmp_path, gpu_result=gpu_result, diarize=True)

        hyp_turns = [
            {"start": s["start"], "end": s["end"], "speaker": s.get("speaker", "SPEAKER_0")} for s in result["segments"]
        ]

        der = _compute_der(ground_truth, hyp_turns, total_dur)
        n_speakers = len(set(s["speaker"] for s in hyp_turns))

        print(f"\n  DER: {der}% (threshold: {DER_THRESHOLD}%)")
        print(f"  Detected speakers: {n_speakers} (expected: {TOTAL_SPEAKERS})")
        print(f"  Result: {'PASS' if der <= DER_THRESHOLD else 'FAIL'}")

        worker.stop()
        sys.exit(0 if der <= DER_THRESHOLD else 1)
    finally:
        os.unlink(tmp_path)
