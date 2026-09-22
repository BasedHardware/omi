#!/usr/bin/env python3
"""
Speaker Stats Analyzer

This script analyzes a transcript of speaker turns and produces
statistics such as total talk time, percentage of total time,
and a simple speech‑balance metric.

The input transcript is expected to be a JSON array where each
element represents a turn and contains at least the following
keys:

    - speaker: Identifier of the speaker (string)
    - start:   Start time of the turn in seconds (float or int)
    - end:     End time of the turn in seconds (float or int)

Example input:

[
    {"speaker": "Alice", "start": 0.0, "end": 5.2},
    {"speaker": "Bob",   "start": 5.2, "end": 10.0},
    ...
]

The output is a JSON object written to the specified output file
containing per‑speaker statistics and an overall balance metric.

Usage
-----
    python speaker_stats_analyzer.py \
        --input transcript.json \
        --output stats.json

The script performs robust error handling and writes the output
atomically (temporary file + rename) to avoid partial writes.
"""

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from typing import Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze speaker turns and compute talk‑time statistics."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to the input transcript JSON file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Path to the output statistics JSON file.",
    )
    return parser.parse_args()


def load_transcript(path: str) -> List[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in input file: {exc}")

    if not isinstance(data, list):
        raise ValueError("Transcript JSON must be an array of turns.")

    for idx, turn in enumerate(data):
        if not isinstance(turn, dict):
            raise ValueError(f"Turn at index {idx} is not an object.")
        for key in ("speaker", "start", "end"):
            if key not in turn:
                raise ValueError(f"Missing key '{key}' in turn at index {idx}.")
        if not isinstance(turn["speaker"], str):
            raise ValueError(f"Speaker must be a string (index {idx}).")
        if not isinstance(turn["start"], (int, float)) or not isinstance(
            turn["end"], (int, float)
        ):
            raise ValueError(f"Start/end must be numbers (index {idx}).")
        if turn["end"] < turn["start"]:
            raise ValueError(f"End time before start time (index {idx}).")

    return data


def compute_stats(turns: List[Dict]) -> Tuple[Dict[str, float], float]:
    """
    Returns:
        speaker_durations: mapping from speaker to total duration in seconds
        overall_balance:   difference between longest and shortest speaker
                           durations (seconds)
    """
    durations = defaultdict(float)
    for turn in turns:
        duration = turn["end"] - turn["start"]
        durations[turn["speaker"]] += duration

    if not durations:
        raise ValueError("No speaker turns found in transcript.")

    total_time = sum(durations.values())
    balance = max(durations.values()) - min(durations.values())

    return durations, total_time, balance


def build_output(
    durations: Dict[str, float], total_time: float, balance: float
) -> Dict:
    stats = {
        "speakers": [],
        "total_time_seconds": total_time,
        "balance_seconds": balance,
    }
    for speaker, dur in sorted(durations.items(), key=lambda x: x[1], reverse=True):
        stats["speakers"].append(
            {
                "speaker": speaker,
                "talk_time_seconds": dur,
                "percentage_of_total": round((dur / total_time) * 100, 2),
            }
        )
    return stats


def write_atomic(path: str, data: Dict) -> None:
    """
    Write JSON data to a temporary file and atomically replace the target.
    """
    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_name,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=4, sort_keys=True)
        tmp_path = tmp.name

    try:
        os.replace(tmp_path, path)
    except Exception as exc:
        # Clean up temp file on failure
        os.unlink(tmp_path)
        raise exc


def main() -> None:
    args = parse_args()

    try:
        turns = load_transcript(args.input)
        durations, total_time, balance = compute_stats(turns)
        output = build_output(durations, total_time, balance)
        write_atomic(args.output, output)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Speaker statistics written to {args.output}")


if __name__ == "__main__":
    main()
