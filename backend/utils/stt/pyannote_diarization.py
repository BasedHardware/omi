"""
Pyannote speaker diarization module.

This module provides speaker diarization using pyannote.audio as a post-processing
step to improve upon Deepgram's real-time diarization.

Usage:
    from utils.stt.pyannote_diarization import pyannote_diarize, merge_with_transcript

    # Get speaker segments from audio (local or cloud)
    segments = pyannote_diarize("/path/to/audio.wav")
    # OR use cloud API
    segments = pyannote_diarize_cloud("/path/to/audio.wav")

    # Merge with existing transcript words
    refined = merge_with_transcript(deepgram_words, segments)

Requirements for local (pyannote_diarize):
    - HuggingFace token with access to pyannote/speaker-diarization-3.1
    - Accept terms at: https://huggingface.co/pyannote/speaker-diarization-3.1
    - GPU recommended for performance

Requirements for cloud (pyannote_diarize_cloud):
    - pyannote.ai API key (PYANNOTE_API_KEY env var)
    - Sign up at: https://www.pyannote.ai/
"""

import os
import time
import base64
import httpx
from typing import Optional
from dataclasses import dataclass

# PyTorch 2.6+ changed weights_only default to True, which breaks pyannote model loading
# Apply patch BEFORE any torch/pyannote imports
def _patch_torch_load():
    try:
        import torch
        _original = torch.load
        def _patched(*args, **kwargs):
            kwargs['weights_only'] = False
            return _original(*args, **kwargs)
        torch.load = _patched
    except ImportError:
        pass

_patch_torch_load()


@dataclass
class DiarizationSegment:
    """A speaker segment from diarization."""
    start: float
    end: float
    speaker: str


def pyannote_diarize_cloud(
    audio_path: str,
    api_key: Optional[str] = None,
    webhook_url: Optional[str] = None,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> list[DiarizationSegment]:
    """
    Run pyannote diarization using the pyannote.ai cloud API.

    This is easier to set up than local diarization - no GPU or model downloads needed.

    Args:
        audio_path: Path to audio file
        api_key: pyannote.ai API key (defaults to PYANNOTE_API_KEY env var)
        webhook_url: Optional webhook URL for async results
        poll_interval: Seconds between status polls (default 2s)
        timeout: Maximum wait time in seconds (default 300s)

    Returns:
        List of DiarizationSegment with speaker labels
    """
    key = api_key or os.getenv("PYANNOTE_API_KEY")
    if not key:
        raise ValueError("pyannote.ai API key required. Set PYANNOTE_API_KEY env var.")

    # Read and encode audio
    with open(audio_path, 'rb') as f:
        audio_data = base64.b64encode(f.read()).decode('utf-8')

    # Determine media type from extension
    ext = os.path.splitext(audio_path)[1].lower()
    media_types = {
        '.wav': 'audio/wav',
        '.mp3': 'audio/mpeg',
        '.flac': 'audio/flac',
        '.ogg': 'audio/ogg',
        '.webm': 'audio/webm',
    }
    media_type = media_types.get(ext, 'audio/wav')

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # Submit diarization job
    payload = {
        "data": f"data:{media_type};base64,{audio_data}"
    }
    if webhook_url:
        payload["webhook"] = webhook_url

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.pyannote.ai/v1/diarize",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        job = response.json()

    job_id = job.get("jobId")
    if not job_id:
        raise ValueError(f"No jobId in response: {job}")

    # Poll for completion
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Diarization timed out after {timeout}s")

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"https://api.pyannote.ai/v1/jobs/{job_id}",
                headers=headers,
            )
            response.raise_for_status()
            status = response.json()

        if status.get("status") == "succeeded":
            break
        elif status.get("status") == "failed":
            raise RuntimeError(f"Diarization failed: {status}")

        time.sleep(poll_interval)

    # Parse results
    segments = []
    output = status.get("output", {})
    diarization = output.get("diarization", [])

    for item in diarization:
        segments.append(DiarizationSegment(
            start=item.get("start", 0),
            end=item.get("end", 0),
            speaker=item.get("speaker", "UNKNOWN"),
        ))

    return segments


def pyannote_diarize(
    audio_path: str,
    hf_token: Optional[str] = None,
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> list[DiarizationSegment]:
    """
    Run pyannote speaker diarization on an audio file.

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.)
        hf_token: HuggingFace token (defaults to HF_TOKEN env var)
        num_speakers: Exact number of speakers (if known)
        min_speakers: Minimum number of speakers
        max_speakers: Maximum number of speakers

    Returns:
        List of DiarizationSegment with speaker labels
    """
    from pyannote.audio import Pipeline

    token = hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_ACCESS_TOKEN")
    if not token:
        raise ValueError("HuggingFace token required. Set HF_TOKEN or HUGGINGFACE_ACCESS_TOKEN env var.")

    # Load the pretrained pipeline
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=token
    )

    # Run diarization with optional speaker hints
    diarization_params = {}
    if num_speakers is not None:
        diarization_params["num_speakers"] = num_speakers
    if min_speakers is not None:
        diarization_params["min_speakers"] = min_speakers
    if max_speakers is not None:
        diarization_params["max_speakers"] = max_speakers

    result = pipeline(audio_path, **diarization_params)

    # pyannote 3.x returns DiarizeOutput with speaker_diarization attribute
    # pyannote 2.x returns Annotation directly
    if hasattr(result, 'speaker_diarization'):
        diarization = result.speaker_diarization
    else:
        diarization = result

    # Convert to segment list
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(DiarizationSegment(
            start=turn.start,
            end=turn.end,
            speaker=speaker
        ))

    return segments


def merge_with_transcript(
    words: list[dict],
    diarization_segments: list[DiarizationSegment],
    speaker_prefix: str = "SPEAKER_"
) -> list[dict]:
    """
    Merge pyannote diarization results with transcript words.

    Assigns pyannote speaker labels to words based on timestamp overlap.

    Args:
        words: List of word dicts with 'word', 'start', 'end', 'speaker' keys
        diarization_segments: Pyannote diarization output
        speaker_prefix: Prefix for speaker labels (default: "SPEAKER_")

    Returns:
        Updated words list with refined speaker assignments
    """
    if not diarization_segments:
        return words

    # Build speaker mapping (pyannote uses SPEAKER_00, SPEAKER_01, etc.)
    unique_speakers = sorted(set(seg.speaker for seg in diarization_segments))
    speaker_map = {s: f"{speaker_prefix}{i:02d}" for i, s in enumerate(unique_speakers)}

    for word in words:
        word_mid = (word.get('start', 0) + word.get('end', 0)) / 2

        # Find the diarization segment that contains this word
        for seg in diarization_segments:
            if seg.start <= word_mid <= seg.end:
                word['speaker'] = speaker_map.get(seg.speaker, seg.speaker)
                word['diarization_source'] = 'pyannote'
                break
        else:
            # No matching segment found, keep original
            word['diarization_source'] = 'original'

    return words


def compare_diarization(
    deepgram_words: list[dict],
    pyannote_segments: list[DiarizationSegment],
) -> dict:
    """
    Compare Deepgram and Pyannote diarization results.

    Returns statistics about agreement/disagreement between the two.
    """
    total_words = len(deepgram_words)
    agreements = 0
    disagreements = 0
    no_pyannote = 0

    for word in deepgram_words:
        word_mid = (word.get('start', 0) + word.get('end', 0)) / 2
        deepgram_speaker = word.get('speaker')

        # Find pyannote speaker
        pyannote_speaker = None
        for seg in pyannote_segments:
            if seg.start <= word_mid <= seg.end:
                pyannote_speaker = seg.speaker
                break

        if pyannote_speaker is None:
            no_pyannote += 1
        elif deepgram_speaker == pyannote_speaker:
            agreements += 1
        else:
            disagreements += 1

    return {
        'total_words': total_words,
        'agreements': agreements,
        'disagreements': disagreements,
        'no_pyannote_coverage': no_pyannote,
        'agreement_rate': agreements / total_words if total_words > 0 else 0,
        'deepgram_speakers': len(set(w.get('speaker') for w in deepgram_words if w.get('speaker'))),
        'pyannote_speakers': len(set(seg.speaker for seg in pyannote_segments)),
    }
