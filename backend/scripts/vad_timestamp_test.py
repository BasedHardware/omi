#!/usr/bin/env python3
"""
VAD Gate Timestamp Accuracy Test — Issue #4644

Tests that DgWallMapper correctly remaps compressed DG timestamps back to
wall-clock-relative time. Uses DG prerecorded with word-level timestamps
as ground truth.

Flow:
  1. Generate speech+silence audio with KNOWN timing (speech at predictable offsets)
  2. Send full audio to DG prerecorded → ground truth word timestamps
  3. Run audio through VAD gate → gated PCM + DgWallMapper state
  4. Send gated audio to DG prerecorded → compressed DG word timestamps
  5. Remap compressed timestamps through DgWallMapper → remapped timestamps
  6. Compare remapped vs ground truth → drift per word

Usage:
    DEEPGRAM_API_KEY=<key> python3 scripts/vad_timestamp_test.py
    DEEPGRAM_API_KEY=<key> python3 scripts/vad_timestamp_test.py --threshold 0.65
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
from gtts import gTTS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.stt.vad_gate import VADStreamingGate

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
CHUNK_MS = 30
DG_URL = 'https://api.deepgram.com/v1/listen'

# Speech segments with known silence gaps between them.
# (text, silence_after_sec) — the exact wall-clock offset of each segment
# is determined at synthesis time.
SEGMENTS = [
    ("The quick brown fox jumps over the lazy dog.", 0.5),
    ("Testing voice activity detection accuracy.", 3.0),
    ("After a long silence the timestamps must still align.", 5.0),
    ("Short gap then more words flowing continuously.", 1.0),
    ("Extended silence before this final segment.", 8.0),
    ("Last sentence to close the test.", 0.0),
]


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float


@dataclass
class SegmentTiming:
    """Timing info for one speech segment."""

    text: str
    wall_offset_sec: float  # when this segment starts in wall-clock-relative time
    silence_after_sec: float


@dataclass
class WordDrift:
    word: str
    ground_truth_start: float
    ground_truth_end: float
    remapped_start: float
    remapped_end: float
    start_drift: float  # remapped - ground_truth
    end_drift: float


def pcm_to_wav(pcm_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def synthesize_segment(text: str, lang: str, temp_dir: Path) -> bytes:
    """Synthesize one speech segment via gTTS, return PCM16 mono 16kHz."""
    mp3_path = temp_dir / f'seg_{hash(text) & 0xFFFFFFFF}.mp3'
    wav_path = temp_dir / f'seg_{hash(text) & 0xFFFFFFFF}.wav'

    gTTS(text=text, lang=lang, slow=False).save(str(mp3_path))
    subprocess.run(
        [
            'ffmpeg',
            '-y',
            '-loglevel',
            'error',
            '-i',
            str(mp3_path),
            '-ac',
            '1',
            '-ar',
            '16000',
            '-f',
            'wav',
            str(wav_path),
        ],
        check=True,
    )

    with wave.open(str(wav_path), 'rb') as wf:
        pcm = wf.readframes(wf.getnframes())
    return pcm


def make_silence(duration_sec: float) -> bytes:
    n_samples = int(SAMPLE_RATE * duration_sec)
    return b'\x00' * (n_samples * SAMPLE_WIDTH)


def build_test_audio(temp_dir: Path) -> Tuple[bytes, List[SegmentTiming]]:
    """Build test audio with known timing for each speech segment."""
    lead_silence = 0.5  # 500ms lead-in
    pcm_parts = [make_silence(lead_silence)]
    cursor_sec = lead_silence
    timings: List[SegmentTiming] = []

    for text, silence_after in SEGMENTS:
        speech_pcm = synthesize_segment(text, 'en', temp_dir)
        speech_duration = len(speech_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)

        timings.append(
            SegmentTiming(
                text=text,
                wall_offset_sec=cursor_sec,
                silence_after_sec=silence_after,
            )
        )
        print(f"  Segment at {cursor_sec:.2f}s ({speech_duration:.2f}s): {text[:50]}...")

        pcm_parts.append(speech_pcm)
        cursor_sec += speech_duration

        if silence_after > 0:
            pcm_parts.append(make_silence(silence_after))
            cursor_sec += silence_after

    # 500ms tail
    pcm_parts.append(make_silence(0.5))
    cursor_sec += 0.5

    full_pcm = b''.join(pcm_parts)
    print(f"  Total audio: {cursor_sec:.2f}s, {len(full_pcm)} bytes")
    return full_pcm, timings


def transcribe_with_words(wav_data: bytes, api_key: str, language: str = 'en') -> List[WordTimestamp]:
    """Send audio to DG prerecorded and extract word-level timestamps."""
    response = requests.post(
        DG_URL,
        params={
            'model': 'nova-2',
            'language': language,
            'smart_format': 'true',
            'utterances': 'true',
        },
        headers={
            'Authorization': f'Token {api_key}',
            'Content-Type': 'audio/wav',
        },
        data=wav_data,
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()

    words = []
    channels = result.get('results', {}).get('channels', [])
    if channels:
        alts = channels[0].get('alternatives', [])
        if alts:
            for w in alts[0].get('words', []):
                words.append(
                    WordTimestamp(
                        word=w['word'],
                        start=w['start'],
                        end=w['end'],
                    )
                )
    return words


def run_vad_gate(pcm_data: bytes, threshold: float) -> Tuple[bytes, VADStreamingGate]:
    """Run audio through VAD gate, return gated PCM and the gate (for mapper access)."""
    gate = VADStreamingGate(
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        mode='active',
        uid='timestamp-test',
        session_id=f'ts-{threshold}',
    )
    gate._speech_threshold = threshold

    chunk_bytes = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * (CHUNK_MS / 1000.0))
    wall_start = time.time()
    gated = bytearray()

    for idx in range(0, len(pcm_data), chunk_bytes):
        chunk = pcm_data[idx : idx + chunk_bytes]
        if not chunk:
            continue
        wall_time = wall_start + (idx / (SAMPLE_RATE * SAMPLE_WIDTH))
        output = gate.process_audio(chunk, wall_time)
        if output.audio_to_send:
            gated.extend(output.audio_to_send)

    gated_bytes = bytes(gated)
    gated.clear()
    return gated_bytes, gate


def match_words(gt_words: List[WordTimestamp], remap_words: List[WordTimestamp]) -> List[WordDrift]:
    """Match ground-truth words to remapped words by text similarity and compute drift."""
    drifts: List[WordDrift] = []
    remap_idx = 0

    for gt_w in gt_words:
        gt_lower = gt_w.word.lower().strip('.,!?;:')
        best_match = None
        best_dist = 999.0
        search_start = max(0, remap_idx - 2)
        search_end = min(len(remap_words), remap_idx + 5)

        for j in range(search_start, search_end):
            rm_lower = remap_words[j].word.lower().strip('.,!?;:')
            if gt_lower == rm_lower:
                best_match = j
                best_dist = 0.0
                break
            sim = SequenceMatcher(None, gt_lower, rm_lower).ratio()
            if sim > 0.7 and (1.0 - sim) < best_dist:
                best_dist = 1.0 - sim
                best_match = j

        if best_match is not None:
            rm_w = remap_words[best_match]
            drifts.append(
                WordDrift(
                    word=gt_w.word,
                    ground_truth_start=gt_w.start,
                    ground_truth_end=gt_w.end,
                    remapped_start=rm_w.start,
                    remapped_end=rm_w.end,
                    start_drift=rm_w.start - gt_w.start,
                    end_drift=rm_w.end - gt_w.end,
                )
            )
            remap_idx = best_match + 1

    return drifts


def print_drift_table(drifts: List[WordDrift], label: str) -> Dict[str, float]:
    """Print drift table and return summary stats."""
    print(f"\n{'=' * 90}")
    print(f"TIMESTAMP DRIFT: {label}")
    print(f"{'=' * 90}")
    print(f"{'Word':<20} {'GT Start':>9} {'Remap Start':>12} {'Drift':>8} {'GT End':>8} {'Remap End':>10} {'Drift':>8}")
    print('-' * 90)

    abs_start_drifts = []
    abs_end_drifts = []

    for d in drifts:
        flag = ''
        if abs(d.start_drift) > 1.0:
            flag = ' *** >1s'
        elif abs(d.start_drift) > 0.5:
            flag = ' ** >0.5s'
        print(
            f"{d.word:<20} {d.ground_truth_start:>9.3f} {d.remapped_start:>12.3f} "
            f"{d.start_drift:>+8.3f} {d.ground_truth_end:>8.3f} {d.remapped_end:>10.3f} "
            f"{d.end_drift:>+8.3f}{flag}"
        )
        abs_start_drifts.append(abs(d.start_drift))
        abs_end_drifts.append(abs(d.end_drift))

    if not abs_start_drifts:
        print("  (no matched words)")
        return {}

    stats = {
        'words_matched': len(drifts),
        'mean_start_drift': np.mean(abs_start_drifts),
        'median_start_drift': np.median(abs_start_drifts),
        'max_start_drift': np.max(abs_start_drifts),
        'p95_start_drift': np.percentile(abs_start_drifts, 95),
        'mean_end_drift': np.mean(abs_end_drifts),
        'median_end_drift': np.median(abs_end_drifts),
        'max_end_drift': np.max(abs_end_drifts),
        'p95_end_drift': np.percentile(abs_end_drifts, 95),
        'words_within_500ms': sum(1 for d in abs_start_drifts if d <= 0.5),
        'words_within_1s': sum(1 for d in abs_start_drifts if d <= 1.0),
    }

    print(f"\nSummary:")
    print(f"  Words matched: {stats['words_matched']}")
    print(
        f"  Start drift — mean: {stats['mean_start_drift']:.3f}s, "
        f"median: {stats['median_start_drift']:.3f}s, "
        f"p95: {stats['p95_start_drift']:.3f}s, "
        f"max: {stats['max_start_drift']:.3f}s"
    )
    print(
        f"  End drift   — mean: {stats['mean_end_drift']:.3f}s, "
        f"median: {stats['median_end_drift']:.3f}s, "
        f"p95: {stats['p95_end_drift']:.3f}s, "
        f"max: {stats['max_end_drift']:.3f}s"
    )
    print(
        f"  Within 500ms: {stats['words_within_500ms']}/{len(drifts)} "
        f"({stats['words_within_500ms']/len(drifts)*100:.0f}%)"
    )
    print(
        f"  Within 1.0s:  {stats['words_within_1s']}/{len(drifts)} "
        f"({stats['words_within_1s']/len(drifts)*100:.0f}%)"
    )

    return stats


def run_timestamp_test(pcm_data: bytes, threshold: float, api_key: str) -> Dict[str, float]:
    """Run one threshold test and return drift stats."""
    print(f"\n--- Threshold {threshold} ---")

    # Step 1: Ground truth — full audio to DG prerecorded with word timestamps
    full_wav = pcm_to_wav(pcm_data)
    gt_words = transcribe_with_words(full_wav, api_key)
    print(f"  Ground truth: {len(gt_words)} words")
    del full_wav

    # Step 2: Run through VAD gate
    gated_pcm, gate = run_vad_gate(pcm_data, threshold)
    metrics = gate.get_metrics()
    savings = metrics['bytes_saved_ratio'] * 100.0
    print(f"  Gated: {len(gated_pcm)} bytes ({savings:.1f}% savings)")

    if len(gated_pcm) < 100:
        print("  WARNING: gated audio too small, skipping")
        return {}

    # Step 3: Send gated audio to DG prerecorded for compressed timestamps
    gated_wav = pcm_to_wav(gated_pcm)
    gated_words = transcribe_with_words(gated_wav, api_key)
    print(f"  Gated words: {len(gated_words)} words (DG compressed time)")
    del gated_pcm, gated_wav

    # Step 4: Remap gated timestamps through DgWallMapper
    remapped_words: List[WordTimestamp] = []
    for w in gated_words:
        remapped_words.append(
            WordTimestamp(
                word=w.word,
                start=gate.dg_wall_mapper.dg_to_wall_rel(w.start),
                end=gate.dg_wall_mapper.dg_to_wall_rel(w.end),
            )
        )

    # Step 5: Match and compute drift
    drifts = match_words(gt_words, remapped_words)
    stats = print_drift_table(drifts, f"threshold={threshold}")

    # Also show raw (un-remapped) drift for comparison
    raw_drifts = match_words(gt_words, gated_words)
    raw_stats = print_drift_table(raw_drifts, f"threshold={threshold} (RAW, no remap)")

    if stats and raw_stats:
        improvement = raw_stats.get('mean_start_drift', 0) - stats.get('mean_start_drift', 0)
        print(f"\n  Remap improvement: {improvement:+.3f}s mean drift reduction")

    return stats


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description='VAD Gate Timestamp Accuracy Test')
    parser.add_argument('--threshold', type=float, default=0.65, help='VAD threshold (default: 0.65)')
    parser.add_argument('--thresholds', default=None, help='Comma-separated thresholds for sweep')
    parser.add_argument('--output', default='/tmp/vad_timestamp_results.json', help='JSON output path')
    args = parser.parse_args()

    api_key = os.environ.get('DEEPGRAM_API_KEY', '').strip()
    if not api_key:
        print("ERROR: Set DEEPGRAM_API_KEY env var")
        return 1

    thresholds = [args.threshold]
    if args.thresholds:
        thresholds = [float(t) for t in args.thresholds.split(',')]

    print("Building test audio with known timing...")
    with tempfile.TemporaryDirectory(prefix='vad_ts_') as tmp:
        pcm_data, timings = build_test_audio(Path(tmp))

    print(f"\nSegment layout:")
    for t in timings:
        print(f"  {t.wall_offset_sec:>6.2f}s: {t.text[:60]}  (silence after: {t.silence_after_sec}s)")

    all_stats = {}
    for threshold in thresholds:
        stats = run_timestamp_test(pcm_data, threshold, api_key)
        all_stats[str(threshold)] = stats

    # Final summary
    print(f"\n{'*' * 90}")
    print("CROSS-THRESHOLD SUMMARY")
    print(f"{'*' * 90}")
    print(
        f"{'Threshold':>10} | {'Words':>6} | {'Mean Drift':>11} | {'P95 Drift':>10} | {'Max Drift':>10} | {'<500ms':>7} | {'<1s':>7}"
    )
    print('-' * 90)

    for t_str, stats in all_stats.items():
        if not stats:
            print(f"{t_str:>10} | {'N/A':>6} |")
            continue
        print(
            f"{t_str:>10} | {stats['words_matched']:>6} | "
            f"{stats['mean_start_drift']:>10.3f}s | "
            f"{stats['p95_start_drift']:>9.3f}s | "
            f"{stats['max_start_drift']:>9.3f}s | "
            f"{stats['words_within_500ms']/stats['words_matched']*100:>6.0f}% | "
            f"{stats['words_within_1s']/stats['words_matched']*100:>6.0f}%"
        )

    # Save results
    output = {
        'test': 'vad_timestamp_accuracy',
        'segments': [
            {'text': t.text, 'wall_offset_sec': t.wall_offset_sec, 'silence_after': t.silence_after_sec}
            for t in timings
        ],
        'thresholds': {t_str: {k: float(v) for k, v in stats.items()} for t_str, stats in all_stats.items() if stats},
    }
    Path(args.output).write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {args.output}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
