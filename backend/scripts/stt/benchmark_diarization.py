#!/usr/bin/env python3
"""
Benchmark speaker diarization accuracy across providers.

Tests Deepgram, Pyannote, and AssemblyAI against ground truth.

Usage:
    python scripts/stt/benchmark_diarization.py <audio.wav> [ground_truth.json]
"""

import os
import sys
import json
import time
from collections import Counter
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv

load_dotenv()


@dataclass
class DiarizationResult:
    """Result from a diarization provider."""

    provider: str
    words: list[dict]  # [{word, start, end, speaker}]
    segments: list[dict]  # [{start, end, speaker, text}]
    num_speakers: int
    processing_time: float


def transcribe_deepgram(audio_path: str) -> DiarizationResult:
    """Get transcription with diarization from Deepgram."""
    from deepgram import DeepgramClient, PrerecordedOptions

    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY not set")

    client = DeepgramClient(api_key)

    with open(audio_path, 'rb') as f:
        audio_data = f.read()

    options = PrerecordedOptions(
        model="nova-3",
        language="en",
        smart_format=True,
        diarize=True,
        punctuate=True,
    )

    start = time.time()
    response = client.listen.rest.v("1").transcribe_file({"buffer": audio_data}, options)
    elapsed = time.time() - start

    words = []
    if response.results and response.results.channels:
        for alt in response.results.channels[0].alternatives:
            for word in alt.words:
                words.append(
                    {
                        'word': word.word,
                        'start': word.start,
                        'end': word.end,
                        'speaker': word.speaker if hasattr(word, 'speaker') else None,
                    }
                )

    # Build segments from words
    segments = []
    if words:
        current_speaker = words[0]['speaker']
        current_start = words[0]['start']
        current_words = [words[0]['word']]

        for w in words[1:]:
            if w['speaker'] != current_speaker:
                segments.append(
                    {
                        'start': current_start,
                        'end': words[words.index(w) - 1]['end'] if words.index(w) > 0 else current_start,
                        'speaker': current_speaker,
                        'text': ' '.join(current_words),
                    }
                )
                current_speaker = w['speaker']
                current_start = w['start']
                current_words = [w['word']]
            else:
                current_words.append(w['word'])

        # Last segment
        segments.append(
            {
                'start': current_start,
                'end': words[-1]['end'],
                'speaker': current_speaker,
                'text': ' '.join(current_words),
            }
        )

    num_speakers = len(set(w['speaker'] for w in words if w['speaker'] is not None))

    return DiarizationResult(
        provider="deepgram", words=words, segments=segments, num_speakers=num_speakers, processing_time=elapsed
    )


def transcribe_assemblyai(audio_path: str) -> DiarizationResult:
    """Get transcription with diarization from AssemblyAI."""
    import assemblyai as aai

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not set")

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        punctuate=True,
        format_text=True,
    )

    transcriber = aai.Transcriber()

    start = time.time()
    transcript = transcriber.transcribe(audio_path, config=config)
    elapsed = time.time() - start

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")

    words = []
    for word in transcript.words or []:
        words.append(
            {
                'word': word.text,
                'start': word.start / 1000,  # ms to seconds
                'end': word.end / 1000,
                'speaker': word.speaker,
            }
        )

    segments = []
    for utt in transcript.utterances or []:
        segments.append(
            {
                'start': utt.start / 1000,
                'end': utt.end / 1000,
                'speaker': utt.speaker,
                'text': utt.text,
            }
        )

    num_speakers = len(set(w['speaker'] for w in words if w['speaker']))

    return DiarizationResult(
        provider="assemblyai", words=words, segments=segments, num_speakers=num_speakers, processing_time=elapsed
    )


def diarize_pyannote(audio_path: str) -> DiarizationResult:
    """Get diarization from Pyannote (local)."""
    from utils.stt.pyannote_diarization import pyannote_diarize

    start = time.time()
    segments_raw = pyannote_diarize(audio_path)
    elapsed = time.time() - start

    segments = []
    for seg in segments_raw:
        segments.append(
            {
                'start': seg.start,
                'end': seg.end,
                'speaker': seg.speaker,
                'text': '',  # Pyannote doesn't do transcription
            }
        )

    num_speakers = len(set(seg.speaker for seg in segments_raw))

    return DiarizationResult(
        provider="pyannote",
        words=[],  # Pyannote doesn't provide word-level
        segments=segments,
        num_speakers=num_speakers,
        processing_time=elapsed,
    )


def compute_der(hypothesis_segments: list[dict], reference_segments: list[dict], collar: float = 0.25) -> dict:
    """
    Compute Diarization Error Rate.

    DER = (Miss + False Alarm + Confusion) / Total Reference Duration

    Args:
        hypothesis_segments: [{start, end, speaker}] from system
        reference_segments: [{start, end, speaker}] ground truth
        collar: Forgiveness collar in seconds around boundaries

    Returns:
        Dict with DER breakdown
    """
    try:
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate

        # Build reference annotation
        reference = Annotation()
        for seg in reference_segments:
            reference[Segment(seg['start'], seg['end'])] = seg['speaker']

        # Build hypothesis annotation
        hypothesis = Annotation()
        for seg in hypothesis_segments:
            hypothesis[Segment(seg['start'], seg['end'])] = str(seg['speaker'])

        # Compute DER
        metric = DiarizationErrorRate(collar=collar)
        der = metric(reference, hypothesis)

        # Get component breakdown
        components = metric.compute_components(reference, hypothesis)

        total_ref = sum(seg['end'] - seg['start'] for seg in reference_segments)

        return {
            'der': der,
            'miss_rate': components.get('missed detection', 0) / total_ref if total_ref > 0 else 0,
            'false_alarm_rate': components.get('false alarm', 0) / total_ref if total_ref > 0 else 0,
            'confusion_rate': components.get('confusion', 0) / total_ref if total_ref > 0 else 0,
            'total_ref_duration': total_ref,
        }
    except ImportError:
        print("Warning: pyannote.metrics not available, using simple comparison")
        return {'der': None, 'error': 'pyannote.metrics not installed'}


def print_results(results: list[DiarizationResult], ground_truth: Optional[list] = None):
    """Print comparison results."""
    print("\n" + "=" * 70)
    print("DIARIZATION BENCHMARK RESULTS")
    print("=" * 70)

    for r in results:
        print(f"\n--- {r.provider.upper()} ---")
        print(f"  Speakers detected: {r.num_speakers}")
        print(f"  Processing time: {r.processing_time:.2f}s")
        print(f"  Words: {len(r.words)}")
        print(f"  Segments: {len(r.segments)}")

        if r.words:
            speaker_dist = Counter(w['speaker'] for w in r.words)
            print(f"  Speaker distribution: {dict(speaker_dist)}")

        if ground_truth:
            der_result = compute_der(r.segments, ground_truth)
            if der_result.get('der') is not None:
                print(f"  DER: {der_result['der']:.1%}")
                print(f"    - Miss rate: {der_result['miss_rate']:.1%}")
                print(f"    - False alarm: {der_result['false_alarm_rate']:.1%}")
                print(f"    - Confusion: {der_result['confusion_rate']:.1%}")

    # Show sample segments
    print("\n" + "-" * 70)
    print("SAMPLE SEGMENTS (first 5 from each provider)")
    print("-" * 70)

    for r in results:
        print(f"\n{r.provider.upper()}:")
        for seg in r.segments[:5]:
            text_preview = seg.get('text', '')[:50] + '...' if len(seg.get('text', '')) > 50 else seg.get('text', '')
            print(f"  [{seg['start']:6.2f} - {seg['end']:6.2f}] Speaker {seg['speaker']}: {text_preview}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_diarization.py <audio.wav> [ground_truth.json]")
        print("\nGround truth JSON format:")
        print('  [{"start": 0.0, "end": 5.0, "speaker": "A"}, ...]')
        sys.exit(1)

    audio_path = sys.argv[1]
    ground_truth_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(audio_path):
        print(f"Error: Audio file not found: {audio_path}")
        sys.exit(1)

    print(f"Audio: {audio_path}")

    # Load ground truth if provided
    ground_truth = None
    if ground_truth_path:
        if ground_truth_path.endswith('.rttm'):
            # Parse RTTM format: SPEAKER <file> <channel> <start> <duration> <NA> <NA> <speaker_id> <NA> <NA>
            ground_truth = []
            with open(ground_truth_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts[0] == 'SPEAKER':
                        start = float(parts[3])
                        duration = float(parts[4])
                        speaker = parts[7]
                        ground_truth.append({'start': start, 'end': start + duration, 'speaker': speaker})
        else:
            with open(ground_truth_path) as f:
                data = json.load(f)
                # Handle multiple formats: raw list, or wrapped with 'segments'/'ground_truth' key
                if isinstance(data, list):
                    ground_truth = data
                elif isinstance(data, dict) and 'segments' in data:
                    ground_truth = data['segments']
                elif isinstance(data, dict) and 'ground_truth' in data:
                    ground_truth = data['ground_truth']
                else:
                    ground_truth = data
        print(f"Ground truth: {ground_truth_path} ({len(ground_truth)} segments)")

    results = []

    # Test Deepgram
    print("\n[1] Testing Deepgram...")
    try:
        results.append(transcribe_deepgram(audio_path))
        print(f"    ✓ Got {results[-1].num_speakers} speakers")
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # Test AssemblyAI
    print("\n[2] Testing AssemblyAI...")
    try:
        results.append(transcribe_assemblyai(audio_path))
        print(f"    ✓ Got {results[-1].num_speakers} speakers")
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # Test Pyannote
    print("\n[3] Testing Pyannote...")
    try:
        results.append(diarize_pyannote(audio_path))
        print(f"    ✓ Got {results[-1].num_speakers} speakers")
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # Print results
    print_results(results, ground_truth)

    # Save results
    output_path = audio_path.replace('.wav', '_benchmark.json')
    with open(output_path, 'w') as f:
        json.dump(
            {
                'audio': audio_path,
                'ground_truth': ground_truth,
                'results': [
                    {
                        'provider': r.provider,
                        'num_speakers': r.num_speakers,
                        'processing_time': r.processing_time,
                        'words': r.words,
                        'segments': r.segments,
                    }
                    for r in results
                ],
            },
            f,
            indent=2,
        )
    print(f"\nResults saved: {output_path}")


if __name__ == "__main__":
    main()
