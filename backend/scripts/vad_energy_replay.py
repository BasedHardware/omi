#!/usr/bin/env python3
"""Offline replay of captured PCM through the energy pre-filter.

Reads raw PCM16 audio, splits into windows, computes RMS per window,
and reports filter rate, RMS distribution, and percentiles at a given
energy threshold. Used for tuning VAD_GATE_ENERGY_THRESHOLD without
running live sessions.

Usage:
    python scripts/vad_energy_replay.py --pcm /tmp/vad_capture/session.pcm --threshold 0.05
    python scripts/vad_energy_replay.py --pcm /tmp/vad_capture/session.pcm --threshold 0.03 0.05 0.07 0.1
"""

import argparse
import os
import sys

import numpy as np


def compute_rms_windows(pcm_path: str, sample_rate: int, channels: int, window_ms: int) -> np.ndarray:
    """Read PCM16 file and compute RMS for each window."""
    data = np.fromfile(pcm_path, dtype=np.int16)
    float_data = data.astype(np.float32) / 32768.0

    # Convert to mono if stereo
    if channels == 2:
        float_data = float_data.reshape(-1, 2).mean(axis=1)

    window_samples = int(sample_rate * window_ms / 1000)
    n_windows = len(float_data) // window_samples
    if n_windows == 0:
        print(f'ERROR: File too short for even one {window_ms}ms window ({len(float_data)} samples)', file=sys.stderr)
        sys.exit(1)

    # Trim to complete windows
    float_data = float_data[: n_windows * window_samples]
    windows = float_data.reshape(n_windows, window_samples)
    rms_values = np.sqrt(np.mean(windows * windows, axis=1))
    return rms_values


def report(rms_values: np.ndarray, thresholds: list, window_ms: int) -> None:
    """Print RMS distribution and filter rates for each threshold."""
    total = len(rms_values)
    duration_sec = total * window_ms / 1000.0

    print(f'=== RMS Energy Analysis ===')
    print(f'Windows:    {total} ({window_ms}ms each)')
    print(f'Duration:   {duration_sec:.1f}s')
    print()

    # Distribution
    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print('RMS Distribution:')
    for p in percentiles:
        val = np.percentile(rms_values, p)
        print(f'  P{p:02d}: {val:.6f}')
    print(f'  Min: {rms_values.min():.6f}')
    print(f'  Max: {rms_values.max():.6f}')
    print(f'  Mean: {rms_values.mean():.6f}')
    print(f'  Std:  {rms_values.std():.6f}')
    print()

    # Filter rates per threshold
    print(f'{"Threshold":>12}  {"Filtered":>10}  {"Passed":>10}  {"Filter%":>10}')
    print(f'{"-"*12}  {"-"*10}  {"-"*10}  {"-"*10}')
    for th in thresholds:
        filtered = int(np.sum(rms_values < th))
        passed = total - filtered
        pct = filtered / total * 100.0
        print(f'{th:>12.4f}  {filtered:>10}  {passed:>10}  {pct:>9.1f}%')

    print()

    # Histogram (text-based)
    print('RMS Histogram (log scale buckets):')
    bins = [0.0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]
    counts, _ = np.histogram(rms_values, bins=bins)
    max_count = max(counts) if max(counts) > 0 else 1
    for i, count in enumerate(counts):
        bar_len = int(50 * count / max_count)
        bar = '#' * bar_len
        print(f'  [{bins[i]:.3f}, {bins[i + 1]:.3f})  {count:>7}  {bar}')


def main():
    parser = argparse.ArgumentParser(description='Replay captured PCM through energy filter analysis')
    parser.add_argument('--pcm', required=True, help='Path to raw PCM16 LE file')
    parser.add_argument(
        '--threshold', type=float, nargs='+', default=[0.03, 0.05, 0.07, 0.1], help='Energy thresholds to evaluate'
    )
    parser.add_argument('--sample-rate', type=int, default=16000, help='Sample rate (default: 16000)')
    parser.add_argument('--channels', type=int, default=1, help='Number of channels (default: 1)')
    parser.add_argument('--window-ms', type=int, default=32, help='Window size in ms (default: 32)')
    args = parser.parse_args()

    if not os.path.exists(args.pcm):
        print(f'ERROR: File not found: {args.pcm}', file=sys.stderr)
        sys.exit(1)

    file_size = os.path.getsize(args.pcm)
    print(f'File: {args.pcm} ({file_size:,} bytes)')
    print(f'Config: {args.sample_rate}Hz, {args.channels}ch, {args.window_ms}ms windows')
    print()

    rms_values = compute_rms_windows(args.pcm, args.sample_rate, args.channels, args.window_ms)
    report(rms_values, sorted(args.threshold), args.window_ms)


if __name__ == '__main__':
    main()
