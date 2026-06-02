import os
import logging

import nemo.collections.asr as nemo_asr

logger = logging.getLogger(__name__)

# parakeet-tdt-0.6b-v3 = multilingual (25 European languages); v2 = English-only (better recall).
MODEL_NAME = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")

logger.info(f"Loading Parakeet model: {MODEL_NAME}")
_model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL_NAME)
_model.eval()
logger.info("Parakeet model loaded")


def transcribe_file(file_path: str):
    """Transcribe a 16 kHz mono audio file with Parakeet.

    Returns: {"text": str, "segments": [{"text", "start", "end"}, ...]}
    """
    hyps = _model.transcribe([file_path], timestamps=True)
    hyp = hyps[0]
    text = getattr(hyp, "text", None) or str(hyp)

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
    # Fall back to a single segment if the model didn't return segment-level timestamps.
    if not segments and text:
        segments = [{"text": text, "start": 0.0, "end": 0.0}]

    return {"text": text, "segments": segments}
