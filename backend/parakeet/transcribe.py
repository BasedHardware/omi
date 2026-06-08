import io
import os
import logging
import wave as _wave

import httpx
import numpy as np
from langdetect import detect as langdetect_detect
from langdetect.lang_detect_exception import LangDetectException
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)

BATCH_MODEL_NAME = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
STREAM_MODEL_NAME = os.getenv("PARAKEET_STREAM_MODEL", "")
INFERENCE_MODE = os.getenv("PARAKEET_INFERENCE_MODE", "nemo")

_batch_model = None
_stream_model = None
_nim_url = None


try:
    import nemo.collections.asr as nemo_asr
except ImportError:
    nemo_asr = None


def _load_nemo_model(model_name: str):
    if nemo_asr is None:
        raise RuntimeError("nemo_toolkit[asr] is not installed")

    logger.info(f"Loading NeMo model: {model_name}")

    model_classes = [
        nemo_asr.models.ASRModel,
    ]
    try:
        model_classes.insert(0, nemo_asr.models.EncDecRNNTBPEModel)
    except AttributeError:
        pass
    try:
        model_classes.insert(0, nemo_asr.models.EncDecCTCModelBPE)
    except AttributeError:
        pass
    try:
        model_classes.insert(0, nemo_asr.models.EncDecMultiTaskModel)
    except AttributeError:
        pass

    import torch

    use_bf16 = os.getenv("PARAKEET_BF16", "1") == "1" and torch.cuda.is_available() and torch.cuda.is_bf16_supported()

    last_err = None
    for cls in model_classes:
        try:
            logger.info(f"Trying {cls.__name__}.from_pretrained({model_name})")
            model = cls.from_pretrained(model_name=model_name, map_location="cpu")
            if use_bf16:
                logger.info(f"Converting {model_name} to BF16 (halves GPU memory)")
                model = model.to(torch.bfloat16)
            model = model.cuda() if torch.cuda.is_available() else model
            model.eval()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info(f"Model {model_name} loaded via {cls.__name__} (bf16={use_bf16})")
            return model
        except (TypeError, Exception) as e:
            last_err = e
            logger.warning(f"{cls.__name__} failed for {model_name}: {e}")
            continue

    raise RuntimeError(f"Could not load model {model_name} with any NeMo class: {last_err}")


def _init_nemo():
    global _batch_model, _stream_model

    _batch_model = _load_nemo_model(BATCH_MODEL_NAME)

    if not STREAM_MODEL_NAME:
        raise RuntimeError("PARAKEET_STREAM_MODEL env var is required")
    _stream_model = _load_nemo_model(STREAM_MODEL_NAME)


def _init_nim():
    global _nim_url
    _nim_url = os.getenv("NIM_INFERENCE_URL", "http://localhost:9000")
    logger.info(f"NIM inference endpoint: {_nim_url}")


if INFERENCE_MODE == "nim":
    _init_nim()
else:
    _init_nemo()

_model = _batch_model


def transcribe_file(file_path: str):
    """Transcribe a 16 kHz mono audio file.

    Returns: {"text": str, "segments": [{"text", "start", "end"}, ...]}
    """
    if INFERENCE_MODE == "nim":
        return _transcribe_nim(file_path)
    return _transcribe_nemo(file_path)


def transcribe_file_v2(file_path: str, diarize: bool = True):
    """V2: transcribe with speaker diarization and language detection.

    Returns: {"text": str, "segments": [...], "detected_language": str}
    Segments include "speaker" labels (SPEAKER_0, SPEAKER_1, etc).
    Language detected via langdetect from transcribed text.
    """
    result = _transcribe_v2_with_diarization(file_path, diarize=diarize)
    result["detected_language"] = detect_language_from_text(result.get("text", ""))
    return result


SPEAKER_EMBEDDING_URL = os.getenv("HOSTED_SPEAKER_EMBEDDING_API_URL", "")
SPEAKER_MATCH_THRESHOLD = float(os.getenv("PARAKEET_SPEAKER_THRESHOLD", "0.45"))
MIN_SEGMENT_DURATION = 0.6


def detect_language_from_text(text: str) -> str:
    if not text or len(text.strip()) < 10:
        return 'en'
    try:
        return langdetect_detect(text)
    except LangDetectException:
        return 'en'


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
