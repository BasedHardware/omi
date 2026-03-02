#!/usr/bin/env python3
"""
VAD Gate Live Test — Issue #4644

Tests the VAD gate with real speech audio against DG prerecorded as ground truth.
Generates speech+silence audio, runs through VAD gate at various thresholds,
streams gated audio to DG WebSocket, and compares transcripts against
DG prerecorded (full audio) as the quality judge.

Usage:
    DEEPGRAM_API_KEY=xxx python3 scripts/vad_live_test.py
    DEEPGRAM_API_KEY=xxx python3 scripts/vad_live_test.py --thresholds 0.3,0.4,0.5,0.6,0.7
"""

import asyncio
import io
import json
import os
import struct
import sys
import time
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
import numpy as np
import websockets

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.stt.vad_gate import VADStreamingGate, GatedDeepgramSocket, DgWallMapper

DG_API_KEY = os.environ.get('DEEPGRAM_API_KEY', '')
SAMPLE_RATE = 16000
CHANNELS = 1

# Test audio segments: (text, silence_after_sec)
TEST_SEGMENTS = [
    ("The quick brown fox jumps over the lazy dog.", 3.0),
    ("This is a test of the voice activity detection system.", 5.0),
    ("After a long pause, speech resumes with more content.", 2.0),
    ("Whispered words should also be detected by the system.", 8.0),
    ("Final segment after extended silence to test keepalive.", 0.0),
]


@dataclass
class ThresholdResult:
    threshold: float
    gate_transcript: str
    ground_truth: str
    similarity: float  # 0.0 to 1.0
    bytes_sent: int
    bytes_received: int
    savings_pct: float
    chunks_total: int
    chunks_speech: int
    chunks_silence: int
    keepalive_count: int
    finalize_count: int
    finalize_errors: int
    duration_sec: float


def generate_test_audio(volume_db: float = 0.0, noise_db: float = -999.0) -> Tuple[bytes, float]:
    """Generate test audio with speech segments separated by silence.

    Args:
        volume_db: Adjust speech volume (negative = quieter, simulates soft speakers)
        noise_db: Background noise level in dBFS (e.g. -30 for moderate noise)

    Returns (pcm_bytes, total_duration_sec, wav_bytes)
    """
    from gtts import gTTS
    from pydub import AudioSegment

    all_audio = AudioSegment.silent(duration=500, frame_rate=SAMPLE_RATE)  # 500ms lead-in

    for text, silence_sec in TEST_SEGMENTS:
        # Generate speech via gTTS
        tts = gTTS(text=text, lang='en')
        mp3_buf = io.BytesIO()
        tts.write_to_fp(mp3_buf)
        mp3_buf.seek(0)

        speech = AudioSegment.from_mp3(mp3_buf)
        speech = speech.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS).set_sample_width(2)

        # Adjust volume to simulate quiet/loud speakers
        if volume_db != 0.0:
            speech = speech + volume_db

        all_audio += speech

        if silence_sec > 0:
            silence = AudioSegment.silent(duration=int(silence_sec * 1000), frame_rate=SAMPLE_RATE)
            all_audio += silence

    all_audio += AudioSegment.silent(duration=500, frame_rate=SAMPLE_RATE)  # 500ms tail

    # Add background noise if requested
    if noise_db > -100:
        # Generate white noise at the specified level
        noise_samples = np.random.normal(0, 1, len(all_audio.get_array_of_samples())).astype(np.float64)
        # Scale to target dBFS
        noise_rms = 10 ** (noise_db / 20.0) * 32768
        noise_samples = (noise_samples / np.std(noise_samples) * noise_rms).astype(np.int16)
        noise_bytes = noise_samples.tobytes()
        noise_seg = AudioSegment(data=noise_bytes, sample_width=2, frame_rate=SAMPLE_RATE, channels=CHANNELS)
        all_audio = all_audio.overlay(noise_seg)

    # Export as raw PCM
    pcm_data = all_audio.raw_data
    duration = len(all_audio) / 1000.0
    label = f"vol={volume_db:+.0f}dB"
    if noise_db > -100:
        label += f" noise={noise_db:.0f}dBFS"
    print(f"Generated test audio ({label}): {duration:.1f}s, {len(pcm_data)} bytes")

    # Also save as WAV for DG prerecorded
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)
    wav_data = wav_buf.getvalue()

    return pcm_data, duration, wav_data


async def get_ground_truth(wav_data: bytes) -> str:
    """Send full audio to DG prerecorded API as ground truth."""
    print("Getting ground truth from DG prerecorded API...")
    url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language=en"
    headers = {
        "Authorization": f"Token {DG_API_KEY}",
        "Content-Type": "audio/wav",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, content=wav_data)
        resp.raise_for_status()
        result = resp.json()

    transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
    print(f"Ground truth ({len(transcript)} chars): {transcript[:120]}...")
    return transcript


async def stream_gated_audio(pcm_data: bytes, threshold: float) -> Tuple[str, dict]:
    """Run audio through VAD gate, send gated output to DG prerecorded, return transcript + metrics."""

    gate = VADStreamingGate(
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        mode='active',
        uid='live-test',
        session_id=f'threshold-{threshold}',
    )
    gate._speech_threshold = threshold

    # Chunk audio into 30ms frames and run through gate
    chunk_size = int(SAMPLE_RATE * CHANNELS * 2 * 0.03)  # 30ms of PCM16
    gated_audio = bytearray()

    wall_start = time.time()
    for i in range(0, len(pcm_data), chunk_size):
        chunk = pcm_data[i : i + chunk_size]
        if len(chunk) < chunk_size:
            break
        wall_time = wall_start + (i // chunk_size) * 0.03
        gate_out = gate.process_audio(chunk, wall_time)
        if gate_out.audio_to_send:
            gated_audio.extend(gate_out.audio_to_send)

    # Convert gated PCM to WAV for DG prerecorded
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(gated_audio))
    wav_data = wav_buf.getvalue()

    # Send gated audio to DG prerecorded for transcription
    url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language=en"
    headers = {
        "Authorization": f"Token {DG_API_KEY}",
        "Content-Type": "audio/wav",
    }

    transcript = ""
    if len(gated_audio) > 100:  # Only if we have meaningful audio
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, content=wav_data)
            resp.raise_for_status()
            result = resp.json()
        transcript = result['results']['channels'][0]['alternatives'][0]['transcript']

    metrics = gate.get_metrics()
    return transcript, metrics


def text_similarity(a: str, b: str) -> float:
    """Compute normalized text similarity (0.0 to 1.0)."""
    a_clean = a.lower().strip()
    b_clean = b.lower().strip()
    if not a_clean or not b_clean:
        return 0.0
    return SequenceMatcher(None, a_clean, b_clean).ratio()


async def run_threshold_test(pcm_data: bytes, threshold: float, ground_truth: str, duration: float) -> ThresholdResult:
    """Run a single threshold test."""
    print(f"\n--- Testing threshold={threshold} ---")
    transcript, metrics = await stream_gated_audio(pcm_data, threshold)
    similarity = text_similarity(transcript, ground_truth)

    result = ThresholdResult(
        threshold=threshold,
        gate_transcript=transcript,
        ground_truth=ground_truth,
        similarity=similarity,
        bytes_sent=metrics['bytes_sent'],
        bytes_received=metrics['bytes_received'],
        savings_pct=metrics['bytes_saved_ratio'] * 100,
        chunks_total=metrics['chunks_total'],
        chunks_speech=metrics['chunks_speech'],
        chunks_silence=metrics['chunks_silence'],
        keepalive_count=metrics['keepalive_count'],
        finalize_count=metrics['finalize_count'],
        finalize_errors=metrics['finalize_errors'],
        duration_sec=duration,
    )

    print(f"  Transcript ({len(transcript)} chars): {transcript[:100]}...")
    print(f"  Similarity: {similarity:.1%}")
    print(f"  Savings: {result.savings_pct:.1f}%")
    print(
        f"  Chunks: {metrics['chunks_total']} total, {metrics['chunks_speech']} speech, {metrics['chunks_silence']} silence"
    )
    print(
        f"  Keepalives: {metrics['keepalive_count']}, Finalizes: {metrics['finalize_count']}, Errors: {metrics['finalize_errors']}"
    )

    return result


async def run_scenario(label: str, thresholds: List[float], volume_db: float = 0.0, noise_db: float = -999.0):
    """Run a full threshold sweep for one audio scenario."""
    print(f"\n{'#' * 100}")
    print(f"# SCENARIO: {label}")
    print(f"{'#' * 100}")

    pcm_data, duration, wav_data = generate_test_audio(volume_db=volume_db, noise_db=noise_db)
    ground_truth = await get_ground_truth(wav_data)

    results: List[ThresholdResult] = []
    for threshold in thresholds:
        try:
            result = await run_threshold_test(pcm_data, threshold, ground_truth, duration)
            results.append(result)
        except Exception as e:
            print(f"  ERROR at threshold={threshold}: {e}")

    # Summary table
    print(f"\n{'=' * 100}")
    print(f"RESULTS: {label}")
    print(f"{'=' * 100}")
    print(
        f"{'Threshold':>10} | {'Similarity':>10} | {'Savings%':>8} | {'Speech':>7} | {'Silence':>7} | {'KA':>4} | {'Fin':>4} | {'Err':>4}"
    )
    print("-" * 100)

    best_result = None
    best_score = -1.0

    for r in results:
        savings_norm = min(r.savings_pct / 80.0, 1.0)
        composite = r.similarity * 0.7 + savings_norm * 0.3
        marker = ""
        if composite > best_score:
            best_score = composite
            best_result = r
            marker = " <-- BEST"

        print(
            f"{r.threshold:>10.2f} | {r.similarity:>9.1%} | {r.savings_pct:>7.1f}% | "
            f"{r.chunks_speech:>7} | {r.chunks_silence:>7} | {r.keepalive_count:>4} | "
            f"{r.finalize_count:>4} | {r.finalize_errors:>4}{marker}"
        )

    if best_result:
        print(
            f"\n  BEST for {label}: threshold={best_result.threshold}, "
            f"quality={best_result.similarity:.1%}, savings={best_result.savings_pct:.1f}%"
        )

    return results, best_result


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='VAD Gate Live Test')
    parser.add_argument('--thresholds', default='0.3,0.4,0.5,0.6,0.7,0.8,0.9', help='Comma-separated thresholds')
    args = parser.parse_args()

    if not DG_API_KEY:
        print("ERROR: Set DEEPGRAM_API_KEY env var")
        sys.exit(1)

    thresholds = [float(t) for t in args.thresholds.split(',')]

    # Test multiple audio conditions
    scenarios = [
        ("Normal speech (0dB)", 0.0, -999.0),
        ("Quiet speech (-12dB)", -12.0, -999.0),
        ("Very quiet speech (-20dB)", -20.0, -999.0),
        ("Normal + moderate noise (-30dBFS)", 0.0, -30.0),
        ("Quiet + noise (-12dB, -35dBFS)", -12.0, -35.0),
    ]

    all_results = {}
    all_bests = {}
    for label, vol, noise in scenarios:
        results, best = await run_scenario(label, thresholds, volume_db=vol, noise_db=noise)
        all_results[label] = results
        all_bests[label] = best

    # Final cross-scenario summary
    print(f"\n{'*' * 100}")
    print("CROSS-SCENARIO SUMMARY")
    print(f"{'*' * 100}")
    print(f"{'Scenario':<45} | {'Best Threshold':>14} | {'Quality':>8} | {'Savings':>8}")
    print("-" * 100)

    threshold_scores = {}
    for label, best in all_bests.items():
        if best:
            print(f"{label:<45} | {best.threshold:>14.2f} | {best.similarity:>7.1%} | {best.savings_pct:>7.1f}%")
            # Accumulate per-threshold scores across scenarios
            for r in all_results[label]:
                if r.threshold not in threshold_scores:
                    threshold_scores[r.threshold] = []
                savings_norm = min(r.savings_pct / 80.0, 1.0)
                composite = r.similarity * 0.7 + savings_norm * 0.3
                threshold_scores[r.threshold].append(composite)

    # Find best overall threshold (highest average composite)
    print(f"\n{'Threshold':>10} | {'Avg Score':>10} | {'Min Quality':>11}")
    print("-" * 50)
    best_overall_threshold = None
    best_overall_score = -1.0
    for t in sorted(threshold_scores.keys()):
        scores = threshold_scores[t]
        avg = sum(scores) / len(scores)
        # Get min quality across scenarios
        min_qual = min(r.similarity for label in all_results for r in all_results[label] if r.threshold == t)
        marker = ""
        if avg > best_overall_score and min_qual >= 0.90:
            best_overall_score = avg
            best_overall_threshold = t
            marker = " <-- BEST"
        print(f"{t:>10.2f} | {avg:>9.3f} | {min_qual:>10.1%}{marker}")

    print(f"\nRECOMMENDED THRESHOLD: {best_overall_threshold}")
    print(f"  Average composite: {best_overall_score:.3f}")
    print(f"  Constraint: min quality >= 90% across all scenarios")

    # Save full results
    results_path = '/tmp/vad_threshold_results.json'
    with open(results_path, 'w') as f:
        json.dump(
            {
                'recommended_threshold': best_overall_threshold,
                'scenarios': {
                    label: [
                        {
                            'threshold': r.threshold,
                            'similarity': r.similarity,
                            'savings_pct': r.savings_pct,
                            'transcript': r.gate_transcript,
                            'bytes_sent': r.bytes_sent,
                            'bytes_received': r.bytes_received,
                            'chunks_speech': r.chunks_speech,
                            'chunks_silence': r.chunks_silence,
                        }
                        for r in results
                    ]
                    for label, results in all_results.items()
                },
            },
            f,
            indent=2,
        )
    print(f"\nFull results saved to {results_path}")


if __name__ == '__main__':
    asyncio.run(main())
