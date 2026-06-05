import os
import logging

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
INFERENCE_MODE = os.getenv("PARAKEET_INFERENCE_MODE", "nemo")

_model = None
_nim_url = None


def _init_nemo():
    global _model
    import nemo.collections.asr as nemo_asr

    logger.info(f"Loading NeMo model: {MODEL_NAME}")
    _model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL_NAME)
    _model.eval()
    logger.info("NeMo model loaded")


def _init_nim():
    global _nim_url
    _nim_url = os.getenv("NIM_INFERENCE_URL", "http://localhost:9000")
    logger.info(f"NIM inference endpoint: {_nim_url}")


if INFERENCE_MODE == "nim":
    _init_nim()
else:
    _init_nemo()


def transcribe_file(file_path: str):
    """Transcribe a 16 kHz mono audio file.

    Returns: {"text": str, "segments": [{"text", "start", "end"}, ...]}
    """
    if INFERENCE_MODE == "nim":
        return _transcribe_nim(file_path)
    return _transcribe_nemo(file_path)


def transcribe_file_v2(file_path: str, diarize: bool = True):
    """V2: transcribe with optional speaker diarization.

    Returns: {"text": str, "segments": [{"text", "start", "end", "speaker"}, ...]}
    Speaker labels are "SPEAKER_0", "SPEAKER_1", etc.
    Diarization uses embedding-based cosine clustering via HOSTED_SPEAKER_EMBEDDING_API_URL.
    """
    return _transcribe_v2_with_diarization(file_path, diarize=diarize)


SPEAKER_EMBEDDING_URL = os.getenv("HOSTED_SPEAKER_EMBEDDING_API_URL", "")
SPEAKER_MATCH_THRESHOLD = float(os.getenv("PARAKEET_SPEAKER_THRESHOLD", "0.45"))
MIN_SEGMENT_DURATION = 0.6


def _transcribe_nemo(file_path: str):
    hyps = _model.transcribe([file_path], timestamps=True)
    hyp = hyps[0]
    text = getattr(hyp, "text", None) or ""

    segments = []
    timestamp = getattr(hyp, "timestamp", None) or {}
    for s in timestamp.get("segment", []) or []:
        segments.append(
            {
                "text": s.get("segment", ""),
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
            }
        )
    if not segments and text:
        segments = [{"text": text, "start": 0.0, "end": 0.0}]

    return {"text": text, "segments": segments}


def _transcribe_nim(file_path: str):
    import httpx

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    nim_language = os.getenv("NIM_LANGUAGE", "multi")

    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=10.0)) as client:
            resp = client.post(
                f"{_nim_url}/v1/audio/transcriptions",
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"language": nim_language},
            )
        resp.raise_for_status()
        data = resp.json()

        text = data.get("text", "") or ""
        segments = []
        for s in data.get("segments", []) or []:
            segments.append(
                {
                    "text": s.get("text", s.get("segment", "")),
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                }
            )
        if not segments and text:
            segments = [{"text": text, "start": 0.0, "end": 0.0}]

        return {"text": text, "segments": segments}
    except Exception as e:
        logger.error(f"NIM transcribe error: {e}")
        raise


def _transcribe_v2_with_diarization(file_path: str, diarize: bool = True):
    base = transcribe_file(file_path)

    if not diarize or not SPEAKER_EMBEDDING_URL:
        for seg in base["segments"]:
            seg["speaker"] = "SPEAKER_0"
        return base

    import httpx
    import io
    import numpy as np
    import wave as _wave
    from scipy.spatial.distance import cdist

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    centroids = []
    counts = []

    for seg in base["segments"]:
        seg_dur = seg["end"] - seg["start"]
        if seg_dur < MIN_SEGMENT_DURATION:
            seg["speaker"] = f"SPEAKER_{len(centroids) - 1}" if centroids else "SPEAKER_0"
            continue

        try:
            seg_wav = _extract_segment_wav(audio_bytes, seg["start"], seg["end"])
            if len(seg_wav) < 1000:
                seg["speaker"] = f"SPEAKER_{len(centroids) - 1}" if centroids else "SPEAKER_0"
                continue

            emb = _get_embedding(seg_wav)
            if emb is None:
                seg["speaker"] = f"SPEAKER_{len(centroids) - 1}" if centroids else "SPEAKER_0"
                continue

            best_i, best_dist = -1, 1e9
            for i, c in enumerate(centroids):
                d = float(cdist(emb, c, metric="cosine")[0, 0])
                if d < best_dist:
                    best_i, best_dist = i, d

            if best_i >= 0 and best_dist < SPEAKER_MATCH_THRESHOLD:
                n = counts[best_i]
                centroids[best_i] = (centroids[best_i] * n + emb) / (n + 1)
                counts[best_i] = n + 1
                seg["speaker"] = f"SPEAKER_{best_i}"
            else:
                centroids.append(emb)
                counts.append(1)
                seg["speaker"] = f"SPEAKER_{len(centroids) - 1}"

        except Exception as e:
            logger.warning(f"Diarization failed for segment {seg['start']:.1f}-{seg['end']:.1f}: {e}")
            seg["speaker"] = f"SPEAKER_{len(centroids) - 1}" if centroids else "SPEAKER_0"

    return base


def _extract_segment_wav(wav_bytes: bytes, start: float, end: float) -> bytes:
    import io
    import wave as _wave

    buf = io.BytesIO(wav_bytes)
    with _wave.open(buf, "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        start_frame = int(start * sr)
        end_frame = int(end * sr)
        wf.setpos(min(start_frame, wf.getnframes()))
        pcm = wf.readframes(end_frame - start_frame)

    out = io.BytesIO()
    with _wave.open(out, "wb") as wf:
        wf.setnchannels(nch)
        wf.setsampwidth(sw)
        wf.setframerate(sr)
        wf.writeframes(pcm)
    return out.getvalue()


def _get_embedding(wav_bytes: bytes):
    import httpx
    import numpy as np

    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)) as client:
            resp = client.post(
                f"{SPEAKER_EMBEDDING_URL}/v2/embedding",
                files={"file": ("segment.wav", wav_bytes, "audio/wav")},
            )
        resp.raise_for_status()
        result = resp.json()

        if isinstance(result, list):
            emb = np.array(result, dtype=np.float32)
        else:
            emb = np.array(result["embedding"], dtype=np.float32)

        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return emb
    except Exception as e:
        logger.warning(f"Embedding extraction failed: {e}")
        return None
