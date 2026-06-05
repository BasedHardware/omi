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

    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=10.0)) as client:
            resp = client.post(
                f"{_nim_url}/v1/transcribe",
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
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
