import io
import os
import logging
import wave as _wave
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
import numpy as np
from langdetect import detect as _langdetect_detect_raw  # type: ignore[reportUnknownVariableType]  # langdetect ships partial type info
from langdetect.lang_detect_exception import LangDetectException
from scipy.cluster.hierarchy import fcluster, linkage
from speaker_math import SPEAKER_CLUSTERING_MAX_SPEAKERS, cosine_distance as cosine_distance

logger = logging.getLogger(__name__)

BATCH_MODEL_NAME: str = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
STREAM_MODEL_NAME: str = os.getenv("PARAKEET_STREAM_MODEL", "")
INFERENCE_MODE: str = os.getenv("PARAKEET_INFERENCE_MODE", "nemo")

_stream_model: Optional[Any] = None
_nim_url: Optional[str] = None
_gpu_worker: Optional[Any] = None

try:
    import nemo.collections.asr as _nemo_asr  # type: ignore[reportMissingImports]  # nemo_toolkit not installed in dev venv
except ImportError:
    _nemo_asr = None

try:
    import torch as _torch_mod  # type: ignore[reportMissingImports]  # torch not installed in dev venv
except ImportError:
    _torch_mod = None

# Untyped / uninstalled libraries aliased as Any so member access does not
# cascade into reportUnknownMemberType warnings.
nemo_asr: Any = _nemo_asr
_torch: Any = cast(Any, _torch_mod)
# langdetect ships partial type information; alias to Any for a clean str return.
langdetect_detect: Any = cast(Any, _langdetect_detect_raw)


def has_builtin_embedding() -> bool:
    return bool(_gpu_worker is not None and _gpu_worker.is_ready and _gpu_worker._embedding_model is not None)


def wav_bytes_to_waveform(wav_bytes: bytes) -> Tuple[Any, int]:
    buf = io.BytesIO(wav_bytes)
    with _wave.open(buf, "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        pcm = wf.readframes(wf.getnframes())

    if sw == 1:
        samples = np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    elif sw == 2:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        samples = np.frombuffer(pcm, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sw} bytes")
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)
    waveform: Any = _torch.from_numpy(samples).unsqueeze(0)
    return waveform, sr


def set_gpu_worker(worker: Any) -> None:
    global _gpu_worker
    _gpu_worker = worker


def report_gpu_inference_error(error: BaseException) -> bool:
    if _gpu_worker is None:
        return False
    reporter: Any = getattr(_gpu_worker, "report_inference_error", None)
    if reporter is None:
        return False
    return bool(reporter(error))


def _load_nemo_model(model_name: str) -> Any:
    if nemo_asr is None:
        raise RuntimeError("nemo_toolkit[asr] is not installed")

    logger.info(f"Loading NeMo model: {model_name}")

    model_classes: List[Any] = [
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

    use_bf16: Any = (
        os.getenv("PARAKEET_BF16", "1") == "1" and _torch.cuda.is_available() and _torch.cuda.is_bf16_supported()
    )

    last_err: Optional[BaseException] = None
    for cls in model_classes:
        try:
            logger.info(f"Trying {cls.__name__}.from_pretrained({model_name})")
            model: Any = cls.from_pretrained(model_name=model_name, map_location="cpu")
            if use_bf16:
                logger.info(f"Converting {model_name} to BF16 (halves GPU memory)")
                model = model.to(_torch.bfloat16)
            model = model.cuda() if _torch.cuda.is_available() else model
            model.eval()
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache()
            logger.info(f"Model {model_name} loaded via {cls.__name__} (bf16={use_bf16})")
            return model
        except (TypeError, Exception) as e:
            last_err = e
            logger.warning(f"{cls.__name__} failed for {model_name}: {e}")
            continue

    raise RuntimeError(f"Could not load model {model_name} with any NeMo class: {last_err}")


def _init_stream_model() -> None:
    global _stream_model
    if not STREAM_MODEL_NAME:
        logger.info("No PARAKEET_STREAM_MODEL set, streaming will be unavailable")
        return
    _stream_model = _load_nemo_model(STREAM_MODEL_NAME)


def _init_nim() -> None:
    global _nim_url
    _nim_url = os.getenv("NIM_INFERENCE_URL", "http://localhost:9000")
    logger.info(f"NIM inference endpoint: {_nim_url}")


if INFERENCE_MODE == "nim":
    _init_nim()
else:
    _init_stream_model()


def _transcribe_from_gpu_result(result: Dict[str, Any]) -> Dict[str, Any]:
    text: Any = result.get("text", "")
    segments: List[Dict[str, Any]] = []
    timestamp: Any = result.get("timestamp", {})
    for s in cast(List[Any], timestamp.get("segment", []) or []):
        seg: Dict[str, Any] = cast(Dict[str, Any], s)
        segments.append(
            {
                "text": seg.get("segment", ""),
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
            }
        )
    if not segments and text:
        segments = [{"text": text, "start": 0.0, "end": 0.0}]
    return {"text": text, "segments": segments}


def transcribe_file(file_path: str) -> Dict[str, Any]:
    if INFERENCE_MODE == "nim":
        return _transcribe_nim(file_path)
    return _transcribe_via_gpu_worker(file_path)


def _transcribe_via_gpu_worker(file_path: str) -> Dict[str, Any]:
    if _gpu_worker is None:
        raise RuntimeError("GPU worker not initialized — call set_gpu_worker() first")
    results: List[Dict[str, Any]] = cast(
        List[Dict[str, Any]],
        _gpu_worker.submit_sync({"audio_paths": [file_path], "timestamps": True, "batch_size": 1}),
    )
    if results and len(results) > 0:
        return _transcribe_from_gpu_result(results[0])
    return {"text": "", "segments": []}


def transcribe_file_v2(
    file_path: str,
    gpu_result: Optional[Dict[str, Any]] = None,
    diarize: bool = True,
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> Dict[str, Any]:
    if gpu_result is not None:
        base: Dict[str, Any] = _transcribe_from_gpu_result(gpu_result)
    else:
        base = transcribe_file(file_path)

    if diarize:
        base = _diarize_segments(
            file_path, base, num_speakers=num_speakers, min_speakers=min_speakers, max_speakers=max_speakers
        )
    else:
        for seg in base["segments"]:
            seg["speaker"] = "SPEAKER_0"

    base["detected_language"] = detect_language_from_text(base.get("text", ""))
    return base


SPEAKER_EMBEDDING_URL: str = os.getenv("HOSTED_SPEAKER_EMBEDDING_API_URL", "")
MIN_SEGMENT_DURATION = 0.6

# Average-linkage AHC cuts the dendrogram on cophenetic merge height — the mean
# distance between two whole clusters. The online path's SPEAKER_CLUSTERING_THRESHOLD
# bounds a different quantity, the distance from one embedding to one drifting
# centroid, so its value does not transfer. Measured on the VoxConverse test subset
# (backend/tests/container/voxconverse): 0.55 cuts 3+ speaker DER from 0.174 to 0.130
# while leaving 1-2 speaker DER unchanged, and every value in 0.40-0.55 beats 0.60.
SPEAKER_AHC_THRESHOLD = float(os.getenv("PARAKEET_SPEAKER_AHC_THRESHOLD", "0.55"))


def detect_language_from_text(text: str) -> str:
    if not text or len(text.strip()) < 10:
        return 'en'
    try:
        return cast(str, langdetect_detect(text))
    except LangDetectException:
        return 'en'


def _transcribe_nim(file_path: str) -> Dict[str, Any]:

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
        data: Dict[str, Any] = cast(Dict[str, Any], resp.json())

        text: Any = data.get("text", "") or ""
        segments: List[Dict[str, Any]] = []
        for s in cast(List[Any], data.get("segments", []) or []):
            seg: Dict[str, Any] = cast(Dict[str, Any], s)
            segments.append(
                {
                    "text": seg.get("text", seg.get("segment", "")),
                    "start": float(seg.get("start", 0.0)),
                    "end": float(seg.get("end", 0.0)),
                }
            )
        if not segments and text:
            segments = [{"text": text, "start": 0.0, "end": 0.0}]

        return {"text": text, "segments": segments}
    except Exception as e:
        logger.error(f"NIM transcribe error: {e}")
        raise


def _diarize_segments(
    file_path: str,
    base: Dict[str, Any],
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> Dict[str, Any]:
    """Label every segment with a speaker using offline agglomerative clustering.

    Embeddings for all eligible segments are collected first, then partitioned in
    a single pass. Clustering the whole file at once makes the partition
    independent of segment order; the previous online centroid matching could not
    be, because each match folded the segment into a running mean. Those centroids
    drifted as noisy segments merged, so a third speaker arriving late was absorbed
    into whichever centroid had drifted nearest instead of opening its own cluster.
    """
    segments: List[Dict[str, Any]] = base["segments"]

    if not SPEAKER_EMBEDDING_URL and not has_builtin_embedding():
        for seg in segments:
            seg["speaker"] = "SPEAKER_0"
        return base

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    # SPEAKER_0 is the floor for every segment: anything too short to embed, and
    # any failure below, keeps it unless clustering resolves something better.
    for seg in segments:
        seg["speaker"] = "SPEAKER_0"

    embeddings: List[Any] = []
    embedded_indices: List[int] = []

    for index, seg in enumerate(segments):
        if seg["end"] - seg["start"] < MIN_SEGMENT_DURATION:
            continue

        try:
            seg_wav = _extract_segment_wav(audio_bytes, seg["start"], seg["end"])
            if len(seg_wav) < 1000:
                continue

            vector = _embedding_vector(_get_embedding(seg_wav))
            if vector is None:
                continue

            embeddings.append(vector)
            embedded_indices.append(index)
        except Exception as e:
            logger.warning(f"Diarization failed for segment {seg['start']:.1f}-{seg['end']:.1f}: {e}")

    if not embeddings:
        return base

    try:
        labels = _cluster_embeddings(embeddings, num_speakers, min_speakers, max_speakers)
    except Exception as e:
        logger.warning(f"Speaker clustering failed; every segment stays SPEAKER_0: {e}")
        return base

    _assign_speaker_labels(segments, embedded_indices, labels)
    return base


def _embedding_vector(embedding: Any) -> Optional[Any]:
    """Flatten an embedding into a finite, non-zero 1-D vector, or None."""
    if embedding is None:
        return None

    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if vector.size == 0 or not bool(np.all(np.isfinite(vector))):
        return None
    if float(np.linalg.norm(vector)) <= 0.0:
        # Cosine distance is undefined against a zero vector: scipy returns NaN
        # for the pair, which propagates through linkage into every cluster.
        return None
    return vector


def _cluster_embeddings(
    embeddings: List[Any],
    num_speakers: Optional[int],
    min_speakers: Optional[int],
    max_speakers: Optional[int],
) -> List[int]:
    """Partition embeddings with average-linkage AHC over cosine distance."""
    total = len(embeddings)
    if total == 1:
        # linkage() requires at least two observations.
        return [0]

    if num_speakers is not None and (min_speakers is not None or max_speakers is not None):
        logger.warning(f"num_speakers={num_speakers} takes precedence over min_speakers/max_speakers")

    tree = linkage(np.vstack(embeddings), method="average", metric="cosine")

    if num_speakers is not None:
        return _cut_to_count(tree, num_speakers, total)

    labels = [int(label) for label in fcluster(tree, t=SPEAKER_AHC_THRESHOLD, criterion="distance")]
    found = len(set(labels))

    if min_speakers is not None and found < min_speakers:
        labels = _cut_to_count(tree, min_speakers, total)
        found = len(set(labels))

    # An explicit max_speakers is the caller's ceiling. Without one, the
    # configured cap still bounds the partition, as it did for the online path.
    ceiling = max_speakers if max_speakers is not None else SPEAKER_CLUSTERING_MAX_SPEAKERS
    if found > ceiling:
        labels = _cut_to_count(tree, ceiling, total)

    return labels


def _cut_to_count(tree: Any, count: int, total: int) -> List[int]:
    """Cut the dendrogram into `count` clusters, clamped to [1, total]."""
    bounded = max(1, min(count, total))
    return [int(label) for label in fcluster(tree, t=bounded, criterion="maxclust")]


def _assign_speaker_labels(segments: List[Dict[str, Any]], embedded_indices: List[int], labels: List[int]) -> None:
    """Write SPEAKER_N onto every segment, renumbered by first appearance.

    scipy's cluster ids are arbitrary, so they are renumbered in order of first
    appearance: SPEAKER_0 is the first voice heard. That is what the online path
    produced and what downstream speaker identification reads.
    """
    ordinals: Dict[int, int] = {}
    for label in labels:
        if label not in ordinals:
            ordinals[label] = len(ordinals)

    speaker_by_segment: Dict[int, int] = {index: ordinals[label] for index, label in zip(embedded_indices, labels)}
    centers = [(segments[index]["start"] + segments[index]["end"]) / 2.0 for index in embedded_indices]

    for index, seg in enumerate(segments):
        if index in speaker_by_segment:
            seg["speaker"] = f"SPEAKER_{speaker_by_segment[index]}"
            continue

        # Too short to embed: inherit from the nearest clustered segment in time,
        # rather than from whichever speaker happened to be created most recently.
        center = (seg["start"] + seg["end"]) / 2.0
        nearest = min(range(len(centers)), key=lambda k: abs(centers[k] - center))
        seg["speaker"] = f"SPEAKER_{speaker_by_segment[embedded_indices[nearest]]}"


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


def _get_embedding(wav_bytes: bytes) -> Any:
    if has_builtin_embedding():
        emb = _get_embedding_builtin(wav_bytes)
        if emb is not None:
            return emb
    if SPEAKER_EMBEDDING_URL:
        return _get_embedding_http(wav_bytes)
    return None


def _get_embedding_builtin(wav_bytes: bytes) -> Any:
    try:
        waveform, sample_rate = wav_bytes_to_waveform(wav_bytes)
        dur = waveform.shape[1] / sample_rate
        if dur < MIN_SEGMENT_DURATION:
            return None
        emb: Any = cast(Any, _gpu_worker).submit_embedding_sync({"waveform": waveform, "sample_rate": sample_rate})
        if emb is None:
            return None
        emb = np.array(emb, dtype=np.float32)
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return emb
    except Exception as e:
        logger.warning(f"Built-in embedding failed: {e}")
        return None


def _get_embedding_http(wav_bytes: bytes) -> Any:
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)) as client:
            resp = client.post(
                f"{SPEAKER_EMBEDDING_URL}/v2/embedding",
                files={"file": ("segment.wav", wav_bytes, "audio/wav")},
            )
        resp.raise_for_status()
        result: Any = resp.json()

        if isinstance(result, list):
            emb = np.array(result, dtype=np.float32)
        else:
            emb = np.array(result["embedding"], dtype=np.float32)

        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return emb
    except Exception as e:
        logger.warning(f"HTTP embedding failed: {e}")
        return None
