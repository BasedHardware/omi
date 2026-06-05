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
    """
    if INFERENCE_MODE == "nim":
        return _transcribe_nim_v2(file_path, diarize=diarize)
    return _transcribe_nemo_v2(file_path, diarize=diarize)


_diar_model = None
DIARIZATION_MODEL = os.getenv("PARAKEET_DIARIZATION_MODEL", "")


def _get_diarization_model():
    global _diar_model
    if _diar_model is not None:
        return _diar_model
    if not DIARIZATION_MODEL:
        return None
    try:
        from nemo.collections.asr.models import ClusteringDiarizer, NeuralDiarizer

        logger.info(f"Loading diarization model: {DIARIZATION_MODEL}")
        _diar_model = NeuralDiarizer.from_pretrained(model_name=DIARIZATION_MODEL)
        logger.info("Diarization model loaded")
        return _diar_model
    except Exception as e:
        logger.warning(f"Could not load diarization model {DIARIZATION_MODEL}: {e}")
        return None


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


def _transcribe_nemo_v2(file_path: str, diarize: bool = True):
    base = _transcribe_nemo(file_path)

    if not diarize:
        for seg in base["segments"]:
            seg["speaker"] = "SPEAKER_0"
        return base

    diar = _get_diarization_model()
    if diar is None:
        for seg in base["segments"]:
            seg["speaker"] = "SPEAKER_0"
        return base

    try:
        diar_result = diar.diarize(audio=[file_path])
        speaker_turns = []
        if diar_result and len(diar_result) > 0:
            for turn in diar_result[0]:
                speaker_turns.append(
                    {
                        "start": float(turn.start),
                        "end": float(turn.end),
                        "speaker": turn.speaker if hasattr(turn, "speaker") else "SPEAKER_0",
                    }
                )

        for seg in base["segments"]:
            seg_mid = (seg["start"] + seg["end"]) / 2
            best_speaker = "SPEAKER_0"
            for turn in speaker_turns:
                if turn["start"] <= seg_mid <= turn["end"]:
                    best_speaker = turn["speaker"]
                    break
            seg["speaker"] = best_speaker

    except Exception as e:
        logger.warning(f"NeMo diarization failed, defaulting to SPEAKER_0: {e}")
        for seg in base["segments"]:
            seg["speaker"] = "SPEAKER_0"

    return base


def _transcribe_nim_v2(file_path: str, diarize: bool = True):
    import httpx

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    nim_language = os.getenv("NIM_LANGUAGE", "multi")

    try:
        data = {"language": nim_language}
        if diarize:
            data["diarize"] = "true"

        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=10.0)) as client:
            resp = client.post(
                f"{_nim_url}/v1/audio/transcriptions",
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data=data,
            )
        resp.raise_for_status()
        result = resp.json()

        text = result.get("text", "") or ""
        segments = []
        for s in result.get("segments", []) or []:
            seg = {
                "text": s.get("text", s.get("segment", "")),
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
                "speaker": s.get("speaker", "SPEAKER_0"),
            }
            segments.append(seg)
        if not segments and text:
            segments = [{"text": text, "start": 0.0, "end": 0.0, "speaker": "SPEAKER_0"}]

        return {"text": text, "segments": segments}
    except Exception as e:
        logger.error(f"NIM v2 transcribe error: {e}")
        raise
