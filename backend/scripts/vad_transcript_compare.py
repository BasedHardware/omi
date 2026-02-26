#!/usr/bin/env python3
"""VAD Gate Transcript Quality Comparison — Issue #4644

Compares raw vs gated audio transcripts to verify the VAD gate
doesn't drop meaningful speech. Transcribes both PCM files via
Deepgram batch API and computes Word Error Rate (WER).

Usage:
    python scripts/vad_transcript_compare.py \
        --raw /tmp/vad_capture/<session>_raw.pcm \
        --gated /tmp/vad_capture/<session>_gated.pcm \
        --sample-rate 16000

Requires:
    - DEEPGRAM_API_KEY env var
    - jiwer (already in requirements: jiwer==3.0.4)
"""

import argparse
import io
import os
import struct
import sys
import wave

# Add backend to path so we can import utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jiwer import wer

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes


def pcm_to_wav(pcm_path: str, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM16 file in a WAV header for Deepgram batch API."""
    with open(pcm_path, 'rb') as f:
        pcm_data = f.read()

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)

    return buf.getvalue()


def transcribe(wav_bytes: bytes, sample_rate: int) -> str:
    """Transcribe WAV bytes via Deepgram and return plain text."""
    words = deepgram_prerecorded_from_bytes(wav_bytes, sample_rate=sample_rate, diarize=False)
    return ' '.join(w['text'] for w in words)


def compute_duration_sec(pcm_path: str, sample_rate: int, channels: int = 1, sample_width: int = 2) -> float:
    """Compute audio duration from PCM file size."""
    size = os.path.getsize(pcm_path)
    return size / (sample_rate * channels * sample_width)


def main():
    parser = argparse.ArgumentParser(description='Compare raw vs gated VAD audio transcripts')
    parser.add_argument('--raw', required=True, help='Path to raw PCM file (all audio)')
    parser.add_argument('--gated', required=True, help='Path to gated PCM file (speech only)')
    parser.add_argument('--sample-rate', type=int, default=16000, help='Audio sample rate (default: 16000)')
    parser.add_argument('--channels', type=int, default=1, help='Number of audio channels (default: 1)')
    parser.add_argument('--pass-threshold', type=float, default=0.20, help='WER threshold for pass (default: 0.20)')
    args = parser.parse_args()

    if not os.getenv('DEEPGRAM_API_KEY'):
        print('ERROR: DEEPGRAM_API_KEY env var required')
        sys.exit(1)

    for path in (args.raw, args.gated):
        if not os.path.exists(path):
            print(f'ERROR: File not found: {path}')
            sys.exit(1)

    raw_duration = compute_duration_sec(args.raw, args.sample_rate, args.channels)
    gated_duration = compute_duration_sec(args.gated, args.sample_rate, args.channels)
    savings_pct = (1.0 - gated_duration / raw_duration) * 100.0 if raw_duration > 0 else 0.0

    print(f'Raw audio:   {raw_duration:.1f}s ({os.path.getsize(args.raw)} bytes)')
    print(f'Gated audio: {gated_duration:.1f}s ({os.path.getsize(args.gated)} bytes)')
    print(f'Savings:     {savings_pct:.1f}%')
    print()

    print('Transcribing raw audio...')
    raw_wav = pcm_to_wav(args.raw, args.sample_rate, args.channels)
    raw_transcript = transcribe(raw_wav, args.sample_rate)
    del raw_wav

    print('Transcribing gated audio...')
    gated_wav = pcm_to_wav(args.gated, args.sample_rate, args.channels)
    gated_transcript = transcribe(gated_wav, args.sample_rate)
    del gated_wav

    raw_words = raw_transcript.split()
    gated_words = gated_transcript.split()

    print()
    print(f'--- Raw transcript ({len(raw_words)} words) ---')
    print(raw_transcript[:500])
    if len(raw_transcript) > 500:
        print(f'... ({len(raw_transcript)} chars total)')
    print()
    print(f'--- Gated transcript ({len(gated_words)} words) ---')
    print(gated_transcript[:500])
    if len(gated_transcript) > 500:
        print(f'... ({len(gated_transcript)} chars total)')
    print()

    if not raw_transcript.strip():
        print('WARNING: Raw transcript is empty — cannot compute WER')
        print('RESULT: SKIP (no reference transcript)')
        sys.exit(0)

    if not gated_transcript.strip():
        print('WARNING: Gated transcript is empty')
        word_error_rate = 1.0
    else:
        word_error_rate = wer(raw_transcript, gated_transcript)

    passed = word_error_rate <= args.pass_threshold
    status = 'PASS' if passed else 'FAIL'

    print(f'WER:         {word_error_rate:.4f} ({word_error_rate * 100:.1f}%)')
    print(f'Threshold:   {args.pass_threshold:.0%}')
    print(f'Word diff:   {len(raw_words)} raw → {len(gated_words)} gated ({len(gated_words) - len(raw_words):+d})')
    print(f'RESULT:      {status}')

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
