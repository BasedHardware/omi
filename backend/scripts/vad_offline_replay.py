#!/usr/bin/env python3
"""VAD Gate Offline Replay — Issue #4644

Feeds a WAV/PCM file through the full VAD gate (Silero + energy filter)
offline and compares raw vs gated transcripts via WER.

Bypasses phone-speaker-to-mic path to test the VAD algorithm directly
on known audio input.

Usage:
    cd backend
    python scripts/vad_offline_replay.py \
        --input /tmp/vad_test/test_30s.wav \
        --ground-truth /tmp/vad_test/ground_truth.txt \
        --chunk-ms 40

Requires:
    - DEEPGRAM_API_KEY env var (or backend .env loaded)
    - jiwer (jiwer==3.0.4)
"""

import argparse
import io
import os
import struct
import sys
import time
import wave

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load .env if present (for DEEPGRAM_API_KEY)
env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value

import numpy as np
from jiwer import wer

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes
from utils.stt.vad_gate import VADStreamingGate


def read_wav(path: str):
    """Read WAV file, return (samples_int16, sample_rate, channels)."""
    with wave.open(path, 'rb') as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16)
    return samples, sr, ch


def samples_to_wav_bytes(samples: np.ndarray, sample_rate: int, channels: int = 1) -> bytes:
    """Convert int16 samples to WAV bytes for Deepgram."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def pcm_bytes_to_wav_bytes(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw PCM16 bytes in WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def transcribe(wav_bytes: bytes, sample_rate: int) -> str:
    """Transcribe WAV bytes via Deepgram batch API."""
    words = deepgram_prerecorded_from_bytes(wav_bytes, sample_rate=sample_rate, diarize=False)
    return ' '.join(w['text'] for w in words)


def main():
    parser = argparse.ArgumentParser(description='Offline VAD gate replay with transcript comparison')
    parser.add_argument('--input', required=True, help='Input WAV file')
    parser.add_argument('--ground-truth', help='Optional ground truth transcript file')
    parser.add_argument('--chunk-ms', type=int, default=40, help='Chunk size in ms (default: 40)')
    parser.add_argument('--energy-threshold', type=float, default=None, help='Override energy threshold')
    parser.add_argument('--speech-threshold', type=float, default=None, help='Override Silero speech threshold')
    parser.add_argument('--pass-threshold', type=float, default=0.20, help='WER pass threshold (default: 0.20)')
    parser.add_argument('--verbose', action='store_true', help='Print per-chunk VAD decisions')
    args = parser.parse_args()

    if not os.getenv('DEEPGRAM_API_KEY'):
        print('ERROR: DEEPGRAM_API_KEY env var required')
        sys.exit(1)

    # Read input audio
    print(f'Reading {args.input}...')
    samples, sr, channels = read_wav(args.input)
    duration_s = len(samples) / (sr * channels)
    print(f'  Sample rate: {sr} Hz, Channels: {channels}, Duration: {duration_s:.1f}s')

    # Create VAD gate in active mode (no speech profile delay)
    gate = VADStreamingGate(
        sample_rate=sr,
        channels=channels,
        mode='active',
        uid='offline-test',
        session_id='offline-replay',
    )

    # Override thresholds if specified
    if args.energy_threshold is not None:
        gate._energy_threshold = args.energy_threshold
        if args.energy_threshold > 0.0:
            gate._onset_confirm = int(os.getenv('VAD_GATE_ONSET_CONFIRM', '3'))
            gate._onset_window = int(os.getenv('VAD_GATE_ONSET_WINDOW', '5'))
        else:
            gate._onset_confirm = 1
            gate._onset_window = 1
    if args.speech_threshold is not None:
        gate._speech_threshold = args.speech_threshold

    print(f'  Energy threshold: {gate._energy_threshold}')
    print(f'  Speech threshold: {gate._speech_threshold}')
    print(f'  Onset confirm: {gate._onset_confirm}/{gate._onset_window}')
    print(f'  Pre-roll: {gate._pre_roll_ms}ms, Hangover: {gate._hangover_ms}ms')
    print()

    # Chunk audio and feed through gate
    chunk_samples = int(sr * channels * args.chunk_ms / 1000)
    raw_pcm = samples.astype(np.int16).tobytes()
    gated_pcm = bytearray()

    speech_windows = 0
    silence_windows = 0
    state_log = []

    print(f'Replaying {duration_s:.1f}s of audio in {args.chunk_ms}ms chunks...')
    t0 = time.time()
    wall = 0.0

    for offset in range(0, len(samples), chunk_samples):
        chunk = samples[offset : offset + chunk_samples]
        if len(chunk) == 0:
            break
        chunk_bytes = chunk.astype(np.int16).tobytes()
        wall += args.chunk_ms / 1000.0

        out = gate.process_audio(chunk_bytes, wall)

        if out.audio_to_send:
            gated_pcm.extend(out.audio_to_send)

        if out.is_speech:
            speech_windows += 1
        else:
            silence_windows += 1

        chunk_time_s = offset / (sr * channels)
        if args.verbose:
            rms = float(np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2)))
            print(
                f'  t={chunk_time_s:6.2f}s  state={out.state.value:8s}  '
                f'speech={out.is_speech}  rms={rms:.5f}  gated_bytes={len(out.audio_to_send)}'
            )

        state_log.append((chunk_time_s, out.state.value, out.is_speech))

    elapsed = time.time() - t0
    gated_bytes = bytes(gated_pcm)
    gated_duration = len(gated_bytes) / (sr * channels * 2)
    savings = (1.0 - gated_duration / duration_s) * 100.0

    print(f'Replay done in {elapsed:.2f}s (real-time factor: {duration_s / elapsed:.1f}x)')
    print()
    print(f'Raw audio:     {duration_s:.1f}s ({len(raw_pcm)} bytes)')
    print(f'Gated audio:   {gated_duration:.1f}s ({len(gated_bytes)} bytes)')
    print(f'Savings:       {savings:.1f}%')
    print(f'Speech chunks: {speech_windows}, Silence chunks: {silence_windows}')
    print()

    # State timeline summary
    print('State timeline (1s windows):')
    for sec in range(int(duration_s)):
        states_in_window = [s for t, s, _ in state_log if sec <= t < sec + 1]
        speech_in_window = [sp for t, _, sp in state_log if sec <= t < sec + 1]
        speech_pct = sum(speech_in_window) / len(speech_in_window) * 100 if speech_in_window else 0
        dominant = max(set(states_in_window), key=states_in_window.count) if states_in_window else '?'
        bar = '#' if speech_pct > 50 else '.' if speech_pct > 0 else ' '
        print(f'  {sec:3d}s: {dominant:8s} speech={speech_pct:5.1f}% {bar}')
    print()

    # Transcribe both
    print('Transcribing raw audio...')
    raw_wav = samples_to_wav_bytes(samples, sr, channels)
    raw_transcript = transcribe(raw_wav, sr)
    del raw_wav

    print('Transcribing gated audio...')
    if len(gated_bytes) > 0:
        gated_wav = pcm_bytes_to_wav_bytes(gated_bytes, sr, channels)
        gated_transcript = transcribe(gated_wav, sr)
        del gated_wav
    else:
        gated_transcript = ''

    print()
    print(f'--- Raw transcript ({len(raw_transcript.split())} words) ---')
    print(raw_transcript[:500])
    print()
    print(f'--- Gated transcript ({len(gated_transcript.split())} words) ---')
    print(gated_transcript[:500] if gated_transcript else '(empty)')
    print()

    # WER: raw vs gated
    if raw_transcript.strip() and gated_transcript.strip():
        wer_raw_gated = wer(raw_transcript, gated_transcript)
    elif not raw_transcript.strip():
        wer_raw_gated = 0.0
        print('WARNING: Raw transcript empty')
    else:
        wer_raw_gated = 1.0

    print(f'WER (raw vs gated): {wer_raw_gated:.4f} ({wer_raw_gated * 100:.1f}%)')

    # WER against ground truth if provided
    if args.ground_truth and os.path.exists(args.ground_truth):
        with open(args.ground_truth) as f:
            gt = f.read().strip()
        if gt:
            wer_raw_gt = wer(gt.lower(), raw_transcript.lower())
            wer_gated_gt = wer(gt.lower(), gated_transcript.lower()) if gated_transcript.strip() else 1.0
            print(f'WER (ground truth vs raw):   {wer_raw_gt:.4f} ({wer_raw_gt * 100:.1f}%)')
            print(f'WER (ground truth vs gated): {wer_gated_gt:.4f} ({wer_gated_gt * 100:.1f}%)')
            print()
            print(f'--- Ground truth ---')
            print(gt[:500])
            print()

    passed = wer_raw_gated <= args.pass_threshold
    status = 'PASS' if passed else 'FAIL'
    print(f'Threshold:  {args.pass_threshold:.0%}')
    print(f'RESULT:     {status}')

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
