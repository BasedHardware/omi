"""
Pyannote Speaker Diarization Modal Function

Runs pyannote/speaker-diarization-3.1 on GPU for improved speaker labeling.
Called asynchronously after Deepgram transcription to refine speaker assignments.

Usage:
    # From backend, trigger async refinement:
    modal_client.refine_diarization.spawn(recording_id, audio_url, dg_result)
"""

import io
import json
import os
from dataclasses import dataclass
from typing import List, Optional

import modal
from modal import App, Secret, Image, gpu

# Modal app configuration
app = App(name="pyannote-diarization")

# Build image with pyannote dependencies
image = (
    Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch",
        "torchaudio",
        "pyannote.audio>=3.1",
        "requests",
        "google-cloud-storage",
    )
)

# Global pipeline - loaded once, reused across requests
pipeline = None


def get_pipeline():
    """Load and cache the Pyannote pipeline on GPU."""
    global pipeline
    if pipeline is None:
        import torch
        from pyannote.audio import Pipeline

        hf_token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
        if not hf_token:
            raise ValueError("HUGGINGFACE_TOKEN not found in environment")

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token
        )

        # Move to GPU if available
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline = pipeline.to(device)
        print(f"Pyannote pipeline loaded on {device}")

    return pipeline


@dataclass
class DiarizationSegment:
    """A single diarization segment."""
    start: float
    end: float
    speaker: str


def merge_words_with_segments(
    words: List[dict],
    diarization_segments: List[DiarizationSegment],
    speaker_prefix: str = "SPEAKER_"
) -> List[dict]:
    """
    Merge Deepgram words with Pyannote speaker segments.

    For each word, find the Pyannote segment that covers its midpoint
    and assign that speaker label.

    Uses O(N+M) algorithm since both words and segments are sorted by time.

    Args:
        words: Deepgram words with {start, end, text, speaker, ...}
        diarization_segments: Pyannote segments with speaker labels
        speaker_prefix: Prefix for speaker labels (default: "SPEAKER_")

    Returns:
        Words with refined speaker labels
    """
    if not diarization_segments:
        return words

    # Sort segments by start time for efficient lookup
    sorted_segments = sorted(diarization_segments, key=lambda s: s.start)

    refined_words = []
    segment_idx = 0

    for word in words:
        word_mid = (word['start'] + word['end']) / 2.0

        # Advance segment_idx to find a potential match (O(N+M) total)
        while segment_idx < len(sorted_segments) and sorted_segments[segment_idx].end < word_mid:
            segment_idx += 1

        # Find segment covering this word's midpoint
        assigned_speaker = None
        if segment_idx < len(sorted_segments) and sorted_segments[segment_idx].start <= word_mid:
            assigned_speaker = sorted_segments[segment_idx].speaker

        # Create refined word with new speaker (or keep original)
        refined_word = word.copy()
        if assigned_speaker:
            # Normalize speaker label format
            if not assigned_speaker.startswith(speaker_prefix):
                # Extract number from SPEAKER_XX format
                speaker_num = assigned_speaker.replace("SPEAKER_", "")
                assigned_speaker = f"{speaker_prefix}{speaker_num}"
            refined_word['speaker'] = assigned_speaker
            refined_word['speaker_refined'] = True
        else:
            refined_word['speaker_refined'] = False

        refined_words.append(refined_word)

    return refined_words


def download_audio(audio_url: str) -> bytes:
    """Download audio from URL (supports GCS signed URLs)."""
    import requests

    response = requests.get(audio_url, timeout=300)
    response.raise_for_status()
    return response.content


@app.function(
    image=image,
    gpu=gpu.T4(count=1),
    timeout=600,  # 10 minute timeout
    memory=(2048, 4096),
    secrets=[
        Secret.from_name("huggingface-token"),
        Secret.from_name("envs"),
    ],
    keep_warm=1,  # Keep one instance warm for faster response
    allow_concurrent_inputs=4,
)
def refine_diarization(
    recording_id: str,
    audio_url: str,
    dg_result: dict,
    num_speakers: Optional[int] = None
) -> dict:
    """
    Refine speaker diarization using Pyannote.

    Args:
        recording_id: Unique ID for this recording/conversation
        audio_url: Signed URL to download audio file
        dg_result: Deepgram result containing:
            - words: List of {start, end, text, speaker}
            - num_speakers: Optional detected speaker count
        num_speakers: Override speaker count (hint for Pyannote)

    Returns:
        {
            "recording_id": str,
            "words": List[dict],  # Refined words with updated speakers
            "segments": List[dict],  # Pyannote segments
            "num_speakers": int,
            "status": "success" | "error",
            "error": Optional[str]
        }
    """
    import tempfile

    try:
        print(f"[{recording_id}] Starting diarization refinement")

        # Get words from Deepgram result
        words = dg_result.get("words", [])
        if not words:
            return {
                "recording_id": recording_id,
                "words": [],
                "segments": [],
                "num_speakers": 0,
                "status": "success",
                "message": "No words to process"
            }

        # Use provided speaker count or from Deepgram
        speaker_hint = num_speakers or dg_result.get("num_speakers")

        # Download audio
        print(f"[{recording_id}] Downloading audio...")
        audio_bytes = download_audio(audio_url)

        # Write to temp file (Pyannote needs file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            audio_path = f.name

        try:
            # Run Pyannote diarization
            print(f"[{recording_id}] Running Pyannote (speakers hint: {speaker_hint})...")
            pipeline = get_pipeline()

            # Build diarization params
            diarization_params = {}
            if speaker_hint:
                diarization_params["num_speakers"] = speaker_hint

            result = pipeline(audio_path, **diarization_params)

            # Handle v3.x API (returns DiarizeOutput)
            if hasattr(result, 'speaker_diarization'):
                diarization = result.speaker_diarization
            else:
                diarization = result

            # Extract segments
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append(DiarizationSegment(
                    start=turn.start,
                    end=turn.end,
                    speaker=str(speaker)
                ))

            print(f"[{recording_id}] Found {len(segments)} segments, {len(set(s.speaker for s in segments))} speakers")

            # Merge with Deepgram words
            refined_words = merge_words_with_segments(words, segments)

            return {
                "recording_id": recording_id,
                "words": refined_words,
                "segments": [{"start": s.start, "end": s.end, "speaker": s.speaker} for s in segments],
                "num_speakers": len(set(s.speaker for s in segments)),
                "status": "success"
            }

        finally:
            # Cleanup temp file
            if os.path.exists(audio_path):
                os.remove(audio_path)

    except Exception as e:
        print(f"[{recording_id}] Error: {str(e)}")
        return {
            "recording_id": recording_id,
            "words": dg_result.get("words", []),  # Return original words on error
            "segments": [],
            "num_speakers": 0,
            "status": "error",
            "error": str(e)
        }


@app.function(
    image=image,
    timeout=60,
)
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "pyannote-diarization"}


# Local entrypoint for testing
@app.local_entrypoint()
def main():
    """Test the diarization function locally."""
    print("Testing Pyannote diarization Modal function...")

    # Example test (would need real audio URL)
    result = refine_diarization.remote(
        recording_id="test-123",
        audio_url="https://example.com/test.wav",
        dg_result={
            "words": [
                {"start": 0.0, "end": 1.0, "text": "hello", "speaker": "SPEAKER_0"},
                {"start": 1.0, "end": 2.0, "text": "world", "speaker": "SPEAKER_1"},
            ],
            "num_speakers": 2
        }
    )
    print(f"Result: {result}")
