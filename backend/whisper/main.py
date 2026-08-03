"""On-prem multilingual STT server (faster-whisper / CTranslate2).

Exposes the OpenAI-compatible ``POST /v1/audio/transcriptions`` surface the parakeet gateway calls
in NIM mode (``PARAKEET_INFERENCE_MODE=nim`` + ``NIM_INFERENCE_URL=http://whisper:8000/v1``). The
gateway sends a multipart ``file`` plus an optional ``language`` form field (omitted => auto-detect;
a concrete BCP-47 code => forced) and reads back ``{"text", "segments":[{"text","start","end"}]}``.
ADR-0037 makes this the default on-prem STT engine (99 languages, CTranslate2, runs on commodity
GPUs incl. Blackwell/sm_120). Models are pre-provisioned into the HF cache on the internal network.
"""

import io
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from faster_whisper import WhisperModel

MODEL = os.getenv("WHISPER_MODEL", "large-v3")
DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
# int8_float16 keeps large-v3 ~1.5GB on GPU and is the CTranslate2 mode validated on sm_120 (NLLB).
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16")
BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
# When set, load the model from this directory instead of the HF cache (HF_HOME) — useful for a
# fully pre-provisioned, egress-free volume layout.
DOWNLOAD_ROOT = os.getenv("WHISPER_MODEL_DIR") or None

app = FastAPI()

_model = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE_TYPE, download_root=DOWNLOAD_ROOT)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "model": MODEL, "device": DEVICE, "compute_type": COMPUTE_TYPE}


@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile = File(...), language: Optional[str] = Form(default=None)) -> Dict[str, Any]:
    audio_bytes = await file.read()
    # Omit/blank/"auto"/"multi" => let faster-whisper auto-detect (it rejects those as an enum).
    lang = (language or "").strip()
    detect = None if lang.lower() in ("", "auto", "multi") else lang

    segments_iter, info = _model.transcribe(
        io.BytesIO(audio_bytes),
        language=detect,
        beam_size=BEAM_SIZE,
        vad_filter=True,
    )
    segments: List[Dict[str, Any]] = []
    parts: List[str] = []
    for seg in segments_iter:
        segments.append({"text": seg.text, "start": float(seg.start), "end": float(seg.end)})
        parts.append(seg.text)
    return {"text": "".join(parts).strip(), "segments": segments, "language": info.language}
