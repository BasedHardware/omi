```python
#!/usr/bin/env python3
"""
Speaker Stats Analyzer

This script analyzes a transcript to calculate speaker turns, talk time percentages,
and speech balance metrics.

Usage:
    python speaker_stats_analyzer.py <input_file> [--output_file <output_file>]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
import os

def parse_timestamp(timestamp_str):
    """Parse a timestamp string into seconds."""
    try:
        if ':' in timestamp_str:
            parts = list(map(int, timestamp_str.split(':')))
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            elif len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return float(timestamp_str)
    except ValueError:
        return 0.0

def analyze_speakers(input_file):
    """Analyze speaker turns and talk time."""
    speaker_turns = []
    speaker_durations = defaultdict(float)
    total_duration = 0.0
    current_speaker = None
    start_time = 0.0

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to match speaker format: [00:01:23] Speaker: Hello
        match = re.match(r'\[(.*?)\]\s*(.*?):\s*(.*)', line)
        if match:
            timestamp_str, speaker, text = match.groups()
            timestamp = parse_timestamp(timestamp_str)

            if current_speaker is not None:
                # Calculate duration of previous turn
                duration = timestamp - start_time
                speaker_turns.append({
                    'speaker': current_speaker,
                    'start': start_time,
                    'end': timestamp,
                    'duration': duration,
                    'text': text
                })
                speaker_durations[current_speaker] += duration
                total_duration += duration

            current_speaker = speaker
            start_time = timestamp

    # Add the last turn if it exists
    if current_speaker is not None and len(lines) > 0:
        # Use a very large end time for the last turn
        duration = start_time + 1  # Default to 1 second if no more timestamps
        speaker_turns.append({
            'speaker': current_speaker,
            'start': start_time,
            'end': start_time + duration,
            'duration': duration,
            'text': ""  # No text after last timestamp
        })
        speaker_durations[current_speaker] += duration
        total_duration += duration

    # Calculate percentages
    speaker_percentages = {
        speaker: (duration / total_duration * 100) if total_duration > 0 else 0
        for speaker, duration in speaker_durations.items()
    }

    # Calculate balance metrics
    num_speakers = len(speaker_durations)
    if num_speakers > 0:
        avg_duration = total_duration / num_speakers
        max_duration = max(speaker_durations.values())
        min_duration = min(speaker_durations.values())
        balance_ratio = max_duration / min_duration if min_duration > 0 else float('inf')
    else:
        avg_duration = 0
        max_duration = 0
        min_duration = 0
        balance_ratio = 0

    return {
        'total_duration': total_duration,
        'speaker_turns': speaker_turns,
        'speaker_durations': dict(speaker_durations),
        'speaker_percentages': speaker_percentages,
        'num_speakers': num_speakers,
        'avg_duration_per_speaker': avg_duration,
        'max_duration_by_speaker': max_duration,
        'min_duration_by_speaker': min_duration,
        'balance_ratio': balance_ratio,
        'analysis_timestamp': datetime.now().isoformat()
    }

def save_results(results, output_file):
    """Save analysis results to a JSON file with atomic replacement."""
    temp_file = f"{output_file}.tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        # Atomic replacement
        if os.name == 'posix':
            os.replace(temp_file, output_file)
        elif os.name == 'nt':
            if os.path.exists(output_file):
                os.remove(output_file)
            os.rename(temp_file, output_file)
        else:
            # Fallback for other OS
            if os.path.exists(output_file):
                os.remove(output_file)
            os.rename(temp_file, output_file)
            
    except Exception as e:
        print(f"Error saving results: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description='Analyze speaker turns, talk time percentages, and speech balance metrics.'
    )
    parser.add_argument('input_file', help='Input transcript file')
    parser.add_argument(
        '--output_file', 
        default='speaker_stats.json',
        help='Output JSON file for results (default: speaker_stats.json)'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        sys.exit(1)
    
    results = analyze_speakers(args.input_file)
    save_results(results, args.output_file)
    
    print(f"Analysis complete. Results saved to {args.output_file}")
    print(f"Total duration: {results['total_duration']:.2f} seconds")
    print(f"Number of speakers: {results['num_speakers']}")
    print("Speaker percentages:")
    for speaker, percentage in results['speaker_percentages'].items():
        print(f"  {speaker}: {percentage:.1f}%")
    print(f"Balance ratio (max/min): {results['balance_ratio']:.2f}")

if __name__ == '__main__':
    main()
```