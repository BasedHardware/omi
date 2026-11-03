import asyncio
import functools
import gc
import math
import os
import time
import uuid
import logging
import io as _io
import wave as _wave

import soundfile as sf
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, cast

gc.disable()

from fastapi import FastAPI, Form, UploadFile, File, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from prometheus_client import make_asgi_app  # type: ignore[reportUnknownVariableType]  # prometheus_client partially typed

from gpu_worker import GPUWorker, AudioDurationExceededError
from batch_engine import BatchEngine, QueueFullError, QueueTimeoutError

# The image build overwrites omi_logging_config.py with backend/utils/logging_config.py.
# Importing utils.logging_config in the NeMo process hits NeMo's utils package.
from omi_logging_config import configure_split_stream_logging, quiet_repetitive_nemo_logs
from transcribe import (
    detect_language_from_text,
    transcribe_file,
    transcribe_file_v2,
    set_gpu_worker,
    INFERENCE_MODE,
    _transcribe_from_gpu_result,  # type: ignore[reportPrivateUsage,reportUnknownVariableType]  # upstream transcribe partially typed
)
from stream_handler import StreamSession, warmup_rnnt_decoder
from admission import StreamAdmissionController
from bounded_audio import submit_audio
import language_gate

# INFO/DEBUG to stdout, WARNING+ to stderr. Also quiets httpx/httpcore.
# The internal HTTP LB already logs every request (successes sampled, errors in
# full), so Uvicorn's per-request access line is a duplicate.
configure_split_stream_logging(level=logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
# nemo_logger does not propagate. Drop only the per-batch timestamps INFO and
# the two repetitive Lhotse dataloader warnings; other NeMo errors still emit.
quiet_repetitive_nemo_logs()
logger = logging.getLogger(__name__)

_ASR_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_AUDIO_LEN_BUCKETS = (1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200, 18000, 36000)

ACTIVE_STREAMS = Gauge('parakeet_active_streams', 'Active /v3/stream WebSocket connections')
ACTIVE_BATCH = Gauge('parakeet_active_batch_requests', 'Active batch transcription requests')
PENDING_REQUESTS = Gauge('parakeet_batch_pending_requests', 'Pending requests in batch engine queue')
LANE_PENDING = Gauge('parakeet_batch_lane_pending_requests', 'Pending batch requests by lane', ['lane'])
LANE_OLDEST = Gauge('parakeet_batch_lane_oldest_pending_seconds', 'Age of oldest queued GPU quantum', ['lane'])
SERVICE_RTF = Histogram(
    'parakeet_service_seconds_per_audio_second',
    'GPU batch service seconds / summed audio seconds; excludes upload, queue, diarization',
    ['lane'],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
LANE_QUEUE_WAIT = Histogram(
    'parakeet_batch_lane_queue_wait_seconds',
    'Time waiting before GPU batch assembly by lane',
    ['lane'],
    buckets=_ASR_BUCKETS,
)
LANE_REFUSALS = Counter(
    'parakeet_batch_lane_refusals_total', 'Batch queue refusals by lane and reason', ['lane', 'reason']
)
REQUEST_DURATION = Histogram(
    'parakeet_request_duration_seconds',
    'Request latency',
    ['endpoint'],
    buckets=_ASR_BUCKETS,
)
STREAM_DURATION = Histogram(
    'parakeet_stream_duration_seconds',
    'WebSocket stream session duration',
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
)
BATCH_SIZE_HIST = Histogram(
    'parakeet_batch_size',
    'Number of files per GPU batch',
    buckets=[1, 2, 4, 8, 16, 32, 64],
)
RTFX = Gauge('parakeet_rtfx', 'Real-time factor of last request (audio_duration / processing_time)')
AUDIO_DURATION = Histogram(
    'parakeet_audio_duration_seconds',
    'Input audio length distribution',
    buckets=_AUDIO_LEN_BUCKETS,
)
QUEUE_DURATION = Histogram(
    'parakeet_queue_duration_seconds',
    'Time spent waiting in queue before batch assembly',
    buckets=_ASR_BUCKETS,
)
INFERENCE_DURATION = Histogram(
    'parakeet_inference_duration_seconds',
    'Pure GPU inference time excluding queue and post-processing',
    buckets=_ASR_BUCKETS,
)
GPU_OOM_TOTAL = Counter('parakeet_gpu_oom_total', 'CUDA out-of-memory events')
GPU_FATAL_ERRORS_TOTAL = Counter(
    'parakeet_gpu_fatal_errors_total',
    'Fatal CUDA errors that make a Parakeet GPU worker unavailable',
)
REQUESTS_TOTAL = Counter('parakeet_requests_total', 'Total requests by status', ['endpoint', 'status'])
PRERECORDED_REQUESTS = Counter(
    'parakeet_prerecorded_requests_total', 'Pre-recorded requests excluding live windowed TDT', ['status']
)

LID_REQUESTS = Counter('parakeet_language_id_requests_total', 'Language gate requests', ['status'])
LID_ROUTES = Counter('parakeet_language_id_routes_total', 'Language gate verdicts', ['route', 'bucket'])
LID_DURATION = Histogram(
    'parakeet_language_id_duration_seconds', 'Language gate wall time including GPU queue', buckets=_ASR_BUCKETS
)
OUTPUT_LANGUAGE = Counter(
    'parakeet_output_language_total',
    'Text language of /v2 transcripts with at least 24 letters; non-P25 output is the wrong-language alarm',
    ['bucket'],
)
_LID_MAX_INFLIGHT = 16
# Callers send at most 30 s; anything far larger is a misuse and must not be decoded into RAM.
_LID_MAX_UPLOAD_BYTES = 16 * 1024 * 1024
_lid_inflight = 0
_OUTPUT_ALARM_MIN_LETTERS = 24
_LANGUAGE_BUCKETS = frozenset({'en', 'ja', 'zh', 'ko', 'vi', 'hi', 'ar', 'th'})


def language_bucket(code: str) -> str:
    """Closed label set: en, other_p25, the paid languages seen in prod, or other."""
    code = (code or '').split('-')[0].lower()
    if code in _LANGUAGE_BUCKETS:
        return code
    return 'other_p25' if code in language_gate.PARAKEET_LANGUAGES else 'other'


def _record_output_language(result: Dict[str, Any]) -> None:
    text = result.get('text') or ''
    if sum(ch.isalpha() for ch in text) < _OUTPUT_ALARM_MIN_LETTERS:
        return
    detected = result.get('detected_language')
    if detected is None:
        # /v1 (voice messages, undiarized prerecorded) carries no language field.
        detected = detect_language_from_text(text)
    OUTPUT_LANGUAGE.labels(bucket=language_bucket(str(detected or ''))).inc()


def _record_output_language_quietly(result: Dict[str, Any]) -> None:
    try:
        _record_output_language(result)
    except Exception:
        pass


gpu_worker: Optional[GPUWorker] = None
batch_engine: Optional[BatchEngine] = None
stream_admission: Optional[StreamAdmissionController] = None
start_time: float = 0
_diarize_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="diarize")
_io_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file-io")
_lid_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="language-id")
_max_file_duration_sec = float(os.getenv("PARAKEET_MAX_FILE_DURATION", "0"))
_packing_enabled = os.getenv('PARAKEET_PACKING_ENABLED', 'false').lower() == 'true'
_LIVE_QUEUE_BUDGET_CAP_SECONDS = 8.0
_TIMEOUT_HEADER = "X-Omi-STT-Timeout-Seconds"


def _get_audio_duration_from_bytes(data: bytes) -> float:
    try:
        info = cast(Any, sf.info(_io.BytesIO(data)))  # type: ignore[reportUnknownMemberType]  # soundfile partially typed
        return info.duration
    except Exception:
        pass
    try:
        with _wave.open(_io.BytesIO(data), 'rb') as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        if _max_file_duration_sec > 0:
            return float('inf')
        return 0.0


def _duration_limit_detail(audio_dur: float) -> str:
    if math.isinf(audio_dur):
        return "Cannot determine audio duration"
    return f"Audio duration {audio_dur:.0f}s exceeds limit ({_max_file_duration_sec:.0f}s)"


def _on_batch_complete(queue_durations: List[float], inference_seconds: float, batch_size: int) -> None:
    for qd in queue_durations:
        QUEUE_DURATION.observe(qd)
    INFERENCE_DURATION.observe(inference_seconds)
    BATCH_SIZE_HIST.observe(batch_size)


def _on_gpu_oom() -> None:
    GPU_OOM_TOTAL.inc()


def _on_fatal_cuda_error(_reason: str) -> None:
    GPU_FATAL_ERRORS_TOTAL.inc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gpu_worker, batch_engine, stream_admission, start_time
    start_time = time.monotonic()
    stream_admission = StreamAdmissionController.from_env(os.environ)

    os.makedirs("_temp", exist_ok=True)

    if INFERENCE_MODE != "nim":
        gpu_worker = GPUWorker(on_fatal_cuda_error=_on_fatal_cuda_error)
        gpu_worker.start()
        set_gpu_worker(gpu_worker)

        batch_engine = BatchEngine(
            gpu_worker=gpu_worker,
            max_batch_size=int(os.getenv("PARAKEET_MAX_BATCH_SIZE", "32")),
            max_wait_seconds=float(os.getenv("PARAKEET_BATCH_WAIT_SECONDS", "0.002")),
            max_queue_depth=int(os.getenv("PARAKEET_MAX_QUEUE_DEPTH", "4096")),
            on_batch_complete=_on_batch_complete,
            on_queue_wait=lambda lane, seconds: LANE_QUEUE_WAIT.labels(lane=lane).observe(seconds),
            on_gpu_oom=_on_gpu_oom,
            vram_safety_factor=float(os.getenv("PARAKEET_VRAM_SAFETY_FACTOR", "0.8")),
            vram_bytes_per_t2=float(os.getenv("PARAKEET_VRAM_BYTES_PER_T2", "136.6")),
            starvation_timeout_sec=float(os.getenv("PARAKEET_STARVATION_TIMEOUT", "5.0")),
            max_inflight=int(os.getenv("PARAKEET_MAX_INFLIGHT", "2")),
            packing=_packing_enabled,
            on_service_time=lambda lane, seconds, audio: (
                SERVICE_RTF.labels(lane=lane).observe(seconds / audio) if audio > 0 else None
            ),
        )
        await batch_engine.start()
        # Scrapes must refresh gauges even when nobody polls /batch/metrics.
        # The snapshot is produced on the owning event loop, never on the
        # prometheus ASGI worker thread (which must not mutate asyncio futures).
        app.state.pressure_task = asyncio.create_task(_refresh_pressure_metrics())
        logger.info("Server started, GPU model loading in background...")
    else:
        logger.info("Parakeet ASR server ready (NIM mode)")

    warmup_rnnt_decoder()
    yield

    logger.info("Shutting down...")
    if batch_engine:
        app.state.pressure_task.cancel()
        try:
            await app.state.pressure_task
        except asyncio.CancelledError:
            pass
    if batch_engine:
        await batch_engine.stop()
    if gpu_worker:
        gpu_worker.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/metrics", cast(Any, make_asgi_app()))


async def _refresh_pressure_metrics() -> None:
    while True:
        if batch_engine is not None:
            snapshot = batch_engine.pressure_snapshot()
            PENDING_REQUESTS.set(snapshot['pending_requests'])
            for lane in ('live', 'backfill'):
                LANE_PENDING.labels(lane=lane).set(snapshot[f'{lane}_pending_requests'])
                LANE_OLDEST.labels(lane=lane).set(snapshot[f'{lane}_oldest_pending_seconds'])
        await asyncio.sleep(0.1)


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@app.post("/v1/transcribe", response_model=None)
async def transcribe(request: Request, file: UploadFile = File(...)) -> JSONResponse | Dict[str, Any]:
    surface = request.headers.get('X-Omi-STT-Surface')
    lane = 'live' if surface == 'live-window' or (_packing_enabled and surface == 'live-stream') else 'backfill'
    prerecorded = lane == 'backfill'
    request_start = time.monotonic()
    if gpu_worker is not None and not gpu_worker.is_ready:
        LANE_REFUSALS.labels(lane=lane, reason='not_ready').inc()
        REQUESTS_TOTAL.labels(endpoint="v1_transcribe", status="error").inc()
        if prerecorded:
            PRERECORDED_REQUESTS.labels(status='error').inc()
        return JSONResponse(status_code=503, content={"detail": "Model loading, try again shortly"})
    queue_deadline: Optional[float] = None
    if lane == 'live':
        budget = _LIVE_QUEUE_BUDGET_CAP_SECONDS
        supplied_raw = request.headers.get(_TIMEOUT_HEADER)
        if supplied_raw is not None:
            try:
                supplied = float(supplied_raw)
            except ValueError:
                supplied = float('nan')
            if not math.isfinite(supplied) or supplied <= 0:
                LANE_REFUSALS.labels(lane=lane, reason='invalid_timeout').inc()
                REQUESTS_TOTAL.labels(endpoint="v1_transcribe", status="error").inc()
                return JSONResponse(status_code=400, content={"detail": f"Invalid {_TIMEOUT_HEADER} budget"})
            budget = min(budget, supplied)
        queue_deadline = request_start + budget
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    audio_dur = 0.0
    status = "success"
    loop = asyncio.get_running_loop()
    file_written = False
    submit_called = False
    write_orphaned = False
    try:
        data = await file.read()
        audio_dur = _get_audio_duration_from_bytes(data)
        if _max_file_duration_sec > 0 and audio_dur > _max_file_duration_sec:
            status = "rejected"
            LANE_REFUSALS.labels(lane=lane, reason='duration').inc()
            return JSONResponse(
                status_code=413,
                content={"detail": _duration_limit_detail(audio_dur)},
            )
        if audio_dur > 0 and math.isfinite(audio_dur):
            AUDIO_DURATION.observe(audio_dur)
        write_work = _io_pool.submit(_write_file, file_path, data)
        try:
            await asyncio.wrap_future(write_work)
            file_written = True
        except asyncio.CancelledError:
            write_orphaned = True
            write_work.add_done_callback(lambda _f, p=file_path: _remove_file(p))
            raise
        except Exception:
            file_written = True
            raise

        if batch_engine is not None:
            submit_called = True
            result = await submit_audio(
                batch_engine,
                file_path,
                _io_pool,
                packing=_packing_enabled,
                owns_file=True,
                lane=lane,
                queue_deadline=queue_deadline,
            )
            body = _transcribe_from_gpu_result(result)
            if prerecorded:
                # langdetect is CPU work; keep it off the event loop and off the response path.
                _io_pool.submit(_record_output_language_quietly, body)
            return JSONResponse(content=body)
        else:
            result = await loop.run_in_executor(_diarize_pool, transcribe_file, file_path)
            return result
    except QueueFullError:
        status = "error"
        LANE_REFUSALS.labels(lane=lane, reason='queue_full').inc()
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
    except QueueTimeoutError:
        status = "error"
        LANE_REFUSALS.labels(lane=lane, reason='queue_timeout').inc()
        return JSONResponse(
            status_code=503,
            content={"detail": "Queued transcription request expired — try again", "error": "queue_timeout"},
            headers={"X-Omi-STT-Error": "queue_timeout"},
        )
    except AudioDurationExceededError as e:
        status = "rejected"
        LANE_REFUSALS.labels(lane=lane, reason='duration').inc()
        return JSONResponse(status_code=413, content={"detail": str(e)})
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.monotonic() - t0
        REQUEST_DURATION.labels(endpoint="v1_transcribe").observe(elapsed)
        REQUESTS_TOTAL.labels(endpoint="v1_transcribe", status=status).inc()
        if prerecorded:
            PRERECORDED_REQUESTS.labels(status=status).inc()
        if status == "success" and audio_dur > 0 and elapsed > 0:
            RTFX.set(audio_dur / elapsed)
        ACTIVE_BATCH.dec()
        if batch_engine is not None:
            PENDING_REQUESTS.set(batch_engine.pressure_snapshot()['pending_requests'])
        if not submit_called and not write_orphaned and (file_written or batch_engine is None):
            await loop.run_in_executor(_io_pool, _remove_file, file_path)


@app.post("/v2/transcribe", response_model=None)
async def transcribe_v2(
    file: UploadFile = File(...),
    diarize: bool = Form(True),
    num_speakers: Optional[int] = Form(None, gt=0),
    min_speakers: Optional[int] = Form(None, gt=0),
    max_speakers: Optional[int] = Form(None, gt=0),
) -> JSONResponse | Dict[str, Any]:
    if gpu_worker is not None and not gpu_worker.is_ready:
        REQUESTS_TOTAL.labels(endpoint="v2_transcribe", status="error").inc()
        PRERECORDED_REQUESTS.labels(status='error').inc()
        return JSONResponse(status_code=503, content={"detail": "Model loading, try again shortly"})
    if min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        REQUESTS_TOTAL.labels(endpoint="v2_transcribe", status="error").inc()
        PRERECORDED_REQUESTS.labels(status='error').inc()
        return JSONResponse(
            status_code=422,
            content={"detail": f"min_speakers ({min_speakers}) cannot exceed max_speakers ({max_speakers})"},
        )
    if num_speakers is not None and (min_speakers is not None or max_speakers is not None):
        # An exact count and a range are contradictory requests. Rejecting is
        # consistent with min > max above; silently preferring one would leave the
        # caller believing a bound they set was honoured.
        REQUESTS_TOTAL.labels(endpoint="v2_transcribe", status="error").inc()
        PRERECORDED_REQUESTS.labels(status='error').inc()
        return JSONResponse(
            status_code=422,
            content={"detail": "num_speakers cannot be combined with min_speakers or max_speakers"},
        )
    speaker_bounds: Dict[str, Optional[int]] = {
        "num_speakers": num_speakers,
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
    }
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    ACTIVE_BATCH.inc()
    t0 = time.monotonic()
    audio_dur = 0.0
    status = "success"
    loop = asyncio.get_running_loop()
    try:
        data = await file.read()
        audio_dur = _get_audio_duration_from_bytes(data)
        if _max_file_duration_sec > 0 and audio_dur > _max_file_duration_sec:
            status = "rejected"
            return JSONResponse(
                status_code=413,
                content={"detail": _duration_limit_detail(audio_dur)},
            )
        if audio_dur > 0 and math.isfinite(audio_dur):
            AUDIO_DURATION.observe(audio_dur)
        await loop.run_in_executor(_io_pool, _write_file, file_path, data)

        if batch_engine is not None:
            PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
            gpu_result = await submit_audio(batch_engine, file_path, _io_pool, packing=_packing_enabled)
            PENDING_REQUESTS.set(len(batch_engine._pending))  # type: ignore[reportPrivateUsage]  # batch_engine internal queue
            result = cast(
                Dict[str, Any],
                await loop.run_in_executor(
                    _diarize_pool,
                    cast(
                        Any,
                        functools.partial(
                            transcribe_file_v2, file_path, gpu_result=gpu_result, diarize=diarize, **speaker_bounds
                        ),
                    ),
                ),
            )
        else:
            result = cast(
                Dict[str, Any],
                await loop.run_in_executor(
                    _diarize_pool,
                    cast(Any, functools.partial(transcribe_file_v2, file_path, diarize=diarize, **speaker_bounds)),
                ),
            )
        _record_output_language_quietly(result)
        return result
    except QueueFullError:
        status = "error"
        return JSONResponse(status_code=503, content={"detail": "Server overloaded — try again later"})
    except AudioDurationExceededError as e:
        status = "rejected"
        return JSONResponse(status_code=413, content={"detail": str(e)})
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.monotonic() - t0
        REQUEST_DURATION.labels(endpoint="v2_transcribe").observe(elapsed)
        REQUESTS_TOTAL.labels(endpoint="v2_transcribe", status=status).inc()
        PRERECORDED_REQUESTS.labels(status=status).inc()
        if status == "success" and audio_dur > 0 and elapsed > 0:
            RTFX.set(audio_dur / elapsed)
        ACTIVE_BATCH.dec()
        await loop.run_in_executor(_io_pool, _remove_file, file_path)


def _decode_for_language(data: bytes) -> Any:
    samples, sample_rate = cast(Any, sf.read(_io.BytesIO(data), dtype='float32', always_2d=False))  # type: ignore[reportUnknownMemberType]  # soundfile partially typed
    return language_gate.to_mono_16k(samples, int(sample_rate))


@app.post("/v2/language", response_model=None)
async def language_v2(file: UploadFile = File(...)) -> JSONResponse | Dict[str, Any]:
    """Spoken-language gate: does this audio belong on Parakeet-25? Never decodes text."""
    global _lid_inflight
    model = gpu_worker.language_id_model if gpu_worker is not None else None
    if gpu_worker is None or not gpu_worker.is_ready or model is None:
        LID_REQUESTS.labels(status='unavailable').inc()
        return JSONResponse(
            status_code=503, content={"detail": "Language gate unavailable", "error": "lid_unavailable"}
        )
    if _lid_inflight >= _LID_MAX_INFLIGHT:
        LID_REQUESTS.labels(status='busy').inc()
        return JSONResponse(status_code=503, content={"detail": "Language gate busy", "error": "lid_busy"})
    _lid_inflight += 1
    t0 = time.monotonic()
    status = 'error'
    loop = asyncio.get_running_loop()
    try:
        data = await file.read()
        if len(data) > _LID_MAX_UPLOAD_BYTES:
            status = 'too_large'
            return JSONResponse(status_code=413, content={"detail": "Probe too large", "error": "too_large"})
        try:
            samples = await loop.run_in_executor(_io_pool, _decode_for_language, data)
        except Exception:
            status = 'bad_audio'
            return JSONResponse(status_code=422, content={"detail": "Unreadable audio", "error": "bad_audio"})
        del data
        seconds = len(samples) / language_gate.SAMPLE_RATE
        if seconds < language_gate.MIN_SECONDS:
            verdict = language_gate.decide({}, seconds, model)
        else:
            probabilities = await loop.run_in_executor(_lid_pool, gpu_worker.submit_language_sync, samples)
            verdict = language_gate.decide(probabilities, seconds, model)
        status = 'success'
        LID_ROUTES.labels(route=verdict.route, bucket=language_bucket(verdict.language)).inc()
        return verdict.as_dict()
    except Exception as e:
        # Callers treat any non-200 as "gate unavailable" and keep their vendor path.
        logger.error("Language gate request failed (exception_type=%s)", type(e).__name__)
        return JSONResponse(status_code=503, content={"detail": "Language gate failed", "error": "lid_error"})
    finally:
        _lid_inflight -= 1
        LID_DURATION.observe(time.monotonic() - t0)
        LID_REQUESTS.labels(status=status).inc()


_WS_RECEIVE_TIMEOUT = 30.0


@app.websocket("/v3/stream")
async def stream_transcribe(
    websocket: WebSocket,
    sample_rate: int = Query(16000),
    vad_threshold: float = Query(None),
    hangover_s: float = Query(None),
):
    await websocket.accept()
    if gpu_worker is not None and not gpu_worker.is_ready:
        REQUESTS_TOTAL.labels(endpoint='v3_stream', status='error').inc()
        await websocket.close(code=1013, reason='service_not_ready')
        return
    if stream_admission is None:
        logger.error('v3/stream admission unavailable')
        await websocket.close(code=1011, reason='service_not_ready')
        return
    decision = stream_admission.try_acquire()
    if decision.lease is None:
        REQUESTS_TOTAL.labels(endpoint='v3_stream', status=decision.reason).inc()
        await websocket.close(code=1013, reason=decision.reason)
        return

    session: Optional[StreamSession] = None
    active_gauge_owned = False
    finalize_requested = False
    t0 = time.monotonic()
    try:
        session = StreamSession(sample_rate=sample_rate, vad_threshold=vad_threshold, hangover_s=hangover_s)
        ACTIVE_STREAMS.inc()
        active_gauge_owned = True
        await websocket.send_json({'type': 'ready'})
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=_WS_RECEIVE_TIMEOUT)
            except asyncio.TimeoutError:
                continue

            if msg.get("type") == "websocket.disconnect":
                # A client hanging up is an expected lifecycle event, not a
                # server fault. Starlette delivers the hang-up as a normal
                # message and then raises 'Cannot call "receive" once a
                # disconnect message has been received.' if the loop re-arms,
                # so every clean client disconnect used to end the session on
                # this generic RuntimeError and log a v3/stream ERROR (prod
                # 2026-09: ~42/30m). Break to the normal finalization path
                # instead, like every other backend websocket receive loop.
                break

            if "bytes" in msg:
                segments = cast(List[Any], await session.feed(msg["bytes"]))
                for seg in segments:
                    await websocket.send_json(seg)
            elif "text" in msg:
                if msg["text"] == "finalize":
                    finalize_requested = True
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"v3/stream error: {e}")
        try:
            await websocket.close(code=1011, reason='stream_initialization_failed')
        except Exception:
            pass
    finally:
        try:
            if session is not None:
                final_segments = cast(List[Any], await session.flush())
                for seg in final_segments:
                    try:
                        await websocket.send_json(seg)
                    except Exception:
                        break
                else:
                    # Finish only after every tail segment was delivered. A
                    # handler return alone can drop TCP without a close frame.
                    if finalize_requested:
                        await websocket.close(code=1000)
        except Exception as e:
            logger.error(f"v3/stream flush error: {e}")
        finally:
            try:
                if session is not None:
                    session.cleanup()
            except Exception as e:
                logger.error(f"v3/stream cleanup error: {e}")
            finally:
                if active_gauge_owned:
                    ACTIVE_STREAMS.dec()
                    STREAM_DURATION.observe(time.monotonic() - t0)
                decision.lease.release()


@app.get("/health", response_model=None)
async def health_check() -> JSONResponse | Dict[str, Any]:
    if gpu_worker is not None:
        ready = gpu_worker.is_ready
        fatal_cuda_reason = gpu_worker.fatal_cuda_reason
        body = {
            "status": "healthy" if ready else "unhealthy" if fatal_cuda_reason is not None else "loading",
            "ready": ready,
            "uptime_seconds": round(time.monotonic() - start_time, 1),
        }
        if fatal_cuda_reason is not None:
            body["reason"] = fatal_cuda_reason
        if not ready:
            return JSONResponse(status_code=503, content=body)
        return body
    return {"status": "healthy"}


@app.get("/batch/metrics")
async def batch_metrics() -> Dict[str, Any]:
    if batch_engine is not None:
        metrics = dict(batch_engine.metrics)
        metrics.update(batch_engine.pressure_snapshot())
        PENDING_REQUESTS.set(metrics['pending_requests'])
        for lane in ('live', 'backfill'):
            LANE_PENDING.labels(lane=lane).set(metrics[f'{lane}_pending_requests'])
        return metrics
    return {}
