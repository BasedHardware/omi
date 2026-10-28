"""Local model adapters. Models are explicitly constructed once at worker startup.

Do not import the existing Parakeet GPUWorker here: it owns a second GPU thread
and loads unrelated embedding models. This chain is the sole model owner.
"""

from collections import OrderedDict
import io
from copy import deepcopy
from contextlib import nullcontext
from typing import TypeGuard
import math
import wave
from typing import Any, Callable
import numpy as np

try:
    import torch  # type: ignore[reportMissingImports]  # Optional GPU runtime dependency, absent in backend venv
except ImportError:
    torch = None

try:
    from omegaconf import OmegaConf, open_dict  # type: ignore[reportMissingImports]  # Optional GPU runtime dependency
except ImportError:
    OmegaConf = None
    open_dict = None

from config.batch_pipeline_providers import provider_config
from config.batch_pipeline_empty_asr import safety_net_enabled
from diarizer.batch_pipeline import (
    PipelineWorker,
    SAMPLE_RATE,
    crop_model_vad_spans,
    padded_retry_fits,
    padded_retry_seconds,
    validate_words,
)
from diarizer.batch_pipeline_context import capture_stream
from diarizer.batch_pipeline_flight import FlightPyannote, diarization_payload
from utils.batch_pipeline.audio import INTAKE_CONTEXT_VERSION, read_context
from utils.batch_pipeline import leaf_timings


def pin_parakeet_decoding(model):
    """Persist eager decoding across NeMo's first timestamp initialization.

    A one-shot disable_cuda_graphs() is insufficient: transcribe(timestamps=True)
    rebuilds decoding from cfg. Set both options before that reconstruction.
    """
    config = deepcopy(model.cfg.decoding)
    # Some checkpoints use a structured DictConfig with initially absent fields.
    # Unlock only the copied decoding config; leave the live model config alone
    # until NeMo installs the complete strategy in one operation.
    editing = (
        open_dict(config)
        if OmegaConf is not None and open_dict is not None and OmegaConf.is_config(config)
        else nullcontext()
    )
    with editing:
        config.compute_timestamps = True
        config.greedy.use_cuda_graph_decoder = False
    model.change_decoding_strategy(config, verbose=False)
    model.decoding.decoding.disable_cuda_graphs()
    assert_eager_decoding(model)


def assert_eager_decoding(model):
    computer = model.decoding.decoding.decoding_computer
    if computer.allow_cuda_graphs is not False or computer.full_graph is not None:
        raise RuntimeError('worker CUDA graph policy violated; restart required')


class ParakeetWords:
    def __init__(self, model, *, enforce_eager=False):
        self.model = model
        self.enforce_eager = enforce_eager

    def transcribe_batch(self, samples):
        if self.enforce_eager:
            assert_eager_decoding(self.model)
        # NeMo accepts float32 16kHz arrays: no file write, read or second decode.
        hypotheses = self.model.transcribe(
            samples,
            batch_size=len(samples),
            timestamps=True,
            return_hypotheses=True,
            num_workers=0,
            verbose=False,
        )
        if self.enforce_eager:
            assert_eager_decoding(self.model)
        result = []
        for hypothesis in hypotheses:
            entries = hypothesis.timestamp.get('word', [])
            words = [{'word': w['word'], 'timestamp': [float(w['start']), float(w['end'])]} for w in entries]
            if hypothesis.text.strip() and not words and not safety_net_enabled():
                raise ValueError('Parakeet returned text without word clocks')
            result.append(words)
        return result

    def recover_empty(self, samples, max_padded_seconds, *, before_dispatch=None, after_dispatch=None):
        """One full-capture, single-item retry with synthetic silence at both edges.

        TDT can emit all blanks for a fragment starting mid-utterance. Retain
        all real samples, remove VAD cuts/core ownership, and change decoder
        context without changing model policy. Bound the extra GPU quantum to
        120s and the existing padded budget. Larger units remain held for the
        fenced legacy recovery path; never truncate them to fit the retry.
        """
        duration = len(samples) / SAMPLE_RATE
        left = 2 * SAMPLE_RATE
        right = max(2 * SAMPLE_RATE, 8 * SAMPLE_RATE - len(samples) - left)
        padded_seconds = padded_retry_seconds(samples)
        if not padded_retry_fits(samples, max_padded_seconds):
            # Never return an empty hypothesis for audio that exceeded the
            # padded recovery bound and was never submitted to the model.
            return None
        padded = np.pad(samples, (left, right))
        if before_dispatch is not None and not before_dispatch():
            return None  # Retain raw work without spending a provider-failure attempt.
        hypotheses = self.transcribe_batch([padded])
        if after_dispatch is not None:
            after_dispatch(padded_seconds)
        if len(hypotheses) != 1:
            raise ValueError('provider recovery result cardinality mismatch')
        words = validate_words(hypotheses[0], padded_seconds)
        result = []
        for word in words:
            start, end = [t - 2 for t in word['timestamp']]
            # Only the real capture owns words. Synthetic padding can never
            # establish speech; intersect edge-straddling clocks with capture.
            if 0 <= (start + end) / 2 < duration:
                result.append({**word, 'timestamp': [max(0, start), min(duration, end)]})
        return validate_words(result, duration)


class PyannoteDiarizer:
    def __init__(self, model, *, timings_of: Callable[[], Any] | None = None):
        self.model = model
        self.timings_of = timings_of or (lambda: None)

    def __call__(self, samples):
        if torch is None:
            raise RuntimeError('pyannote adapter requires the GPU runtime with torch')
        with leaf_timings.active(self.timings_of()), leaf_timings.embedding_hook(self.model), torch.inference_mode():
            output = self.model({'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': 16000})
        return diarization_payload(output)


class PyannoteVAD:
    def __init__(self, model):
        self.model = model

    def __call__(self, samples):
        if torch is None:
            raise RuntimeError('pyannote adapter requires the GPU runtime with torch')
        with torch.inference_mode():
            output = self.model({'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': 16000})
        return crop_model_vad_spans(
            [(float(t.start), float(t.end)) for t in output.get_timeline().support()], len(samples) / 16000
        )


class StagedAudio:
    """Fetch+decode staged audio once, keeping each unit's capture-stream identity.

    The authenticated intake context frozen in the staged WAV names the source,
    device and lock the per-unit chunk identity was built from. Record-lane
    audio carries no intake context; its conversation is its stream.
    """

    MAX_PENDING = 256

    def __init__(self, fetch_audio, *, timings_of: Callable[[], Any] | None = None):
        self.fetch_audio = fetch_audio
        self.timings_of = timings_of or (lambda: None)
        self._streams: OrderedDict[str, str | None] = OrderedDict()
        self._languages: OrderedDict[str, str | None] = OrderedDict()

    def decode(self, item):
        with leaf_timings.active(self.timings_of()):
            body = self.fetch_audio(item)
            return self._decode(item, body)

    def _decode(self, item, body):
        try:
            context = read_context(body)
        except Exception:
            context = None
        self._streams[item.segment_id] = capture_stream(item, context)
        self._languages[item.segment_id] = stt_language(
            context,
            duration_seconds=item.duration_seconds,
            expected_owner_id=item.owner_id,
            expected_segment_id=item.segment_id,
        )
        for pending in (self._streams, self._languages):
            while len(pending) > self.MAX_PENDING:
                pending.popitem(last=False)
        return leaf_timings.call('decode', decode_pcm16_wav, body)

    def stream(self, item):
        stream = self._streams.pop(item.segment_id, None)
        return ('shadow:' + stream) if item.shadow and stream else stream

    def language(self, item):
        """Intake's resolved STT language ('' unknown); None when intake did not record one."""
        return self._languages.pop(item.segment_id, None)


MAX_SELF_LID_PROBE_SECONDS = 30.0
# Earlier intake persisted the language endpoint's millisecond-rounded duration.
SELF_LID_DURATION_TOLERANCE_SECONDS = 0.0005 + 1 / 16000 + 1e-9


def _finite_number(value: object) -> TypeGuard[int | float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _valid_self_lid_context(context, *, duration_seconds, expected_owner_id, expected_segment_id) -> bool:
    """Bind self-LID permission to the authenticated upload that produced the unit."""
    if (
        isinstance(context.get('version'), bool)
        or not isinstance(context.get('version'), int)
        or context.get('version') != INTAKE_CONTEXT_VERSION
        or not isinstance(expected_owner_id, str)
        or not expected_owner_id
        or context.get('owner_id') != expected_owner_id
        or not isinstance(expected_segment_id, str)
        or not expected_segment_id
        or context.get('segment_id') != expected_segment_id
        or not isinstance(context.get('source'), str)
        or not context['source'].strip()
        or any(not isinstance(context.get(key), str) or not context[key].strip() for key in ('job_id', 'content_id'))
        or not _finite_number(duration_seconds)
        or duration_seconds <= 0
    ):
        return False

    probe_seconds = context.get('stt_language_probe_seconds')
    if not _finite_number(probe_seconds) or not 0 < probe_seconds <= MAX_SELF_LID_PROBE_SECONDS:
        return False
    expected_probe_seconds = min(float(duration_seconds), MAX_SELF_LID_PROBE_SECONDS)
    return abs(probe_seconds - expected_probe_seconds) <= SELF_LID_DURATION_TOLERANCE_SECONDS


def stt_language(
    context,
    *,
    duration_seconds=None,
    expected_owner_id=None,
    expected_segment_id=None,
):
    if not isinstance(context, dict) or 'stt_language' not in context:
        return None
    value = context['stt_language']
    if not isinstance(value, str):
        return None
    from config.prerecorded_language import (
        MIN_AUDIO_LID_CONFIDENCE,
        audio_lid_confidence_floor,
        language_class,
        self_lid_confidence_floor,
    )

    evidence = context.get('stt_language_evidence')
    confidence = context.get('stt_language_confidence')
    classification = language_class(value)

    if evidence == 'self_lid':
        if (
            not 2 <= len(value) <= 8
            or not value.isascii()
            or value != value.lower()
            or not value.replace('-', '').isalpha()
            or any(not part for part in value.split('-'))
            or not _finite_number(duration_seconds)
            or not _valid_self_lid_context(
                context,
                duration_seconds=duration_seconds,
                expected_owner_id=expected_owner_id,
                expected_segment_id=expected_segment_id,
            )
            or not _finite_number(confidence)
            or not 0 <= confidence <= 1
        ):
            return None
        if classification == 'supported':
            minimum = self_lid_confidence_floor(min(float(duration_seconds), MAX_SELF_LID_PROBE_SECONDS))
            if minimum is None or confidence < minimum:
                return None
        # An authenticated unsupported top language remains unavailable to the
        # fixed Parakeet worker and is retained for its multilingual recovery.
        return value

    if classification == 'supported':
        # Older intake copied the app's primary language even in multilingual
        # mode. Such a hint is not proof that this audio is supported.
        minimum = audio_lid_confidence_floor(duration_seconds) if evidence == 'audio_lid' else MIN_AUDIO_LID_CONFIDENCE
        if (
            evidence not in ('declared', 'audio_lid')
            or not _finite_number(confidence)
            or not minimum <= confidence <= 1
        ):
            return None
    return value


def decode_pcm16_wav(body):
    """Bounded canonical staging format; callers decrypt/fetch before this step."""
    with wave.open(io.BytesIO(body), 'rb') as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, 16000):
            raise ValueError('staging requires 16kHz mono PCM16 WAV')
        if not 0 < handle.getnframes() <= 7200 * 16000:
            raise ValueError('invalid staged audio length')
        raw = handle.readframes(handle.getnframes())
        if len(raw) != handle.getnframes() * 2:
            raise ValueError('truncated staged WAV')
    return np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768


def create_local_worker(
    *,
    fetch_audio,
    persist_result,
    vad_model,
    parakeet_model,
    pyannote_model,
    live_words=None,
    single_speaker=None,
    on_failure=None,
):
    """Compose once per GPU process after explicit model startup.

    fetch_audio/persist_result own decryption/encryption and durable references.
    Scheduler owns leases/heartbeats; invoke process_batch on its blocking worker
    lane. No API or vendor calls are introduced. Alternative providers must be
    explicitly registered in PipelineWorker, never silently mapped to Parakeet.
    """
    config = provider_config()
    if config.pool_kind != 'dedicated_batch':
        raise ValueError(
            'local model chain requires dedicated batch GPU; shared-live requires its existing GPU arbiter'
        )
    pin_parakeet_decoding(parakeet_model)
    words = ParakeetWords(parakeet_model, enforce_eager=True)
    flight = (
        FlightPyannote.create(pyannote_model, vad_model, budget_seconds=config.flight_batch_seconds)
        if config.flight_batching
        else None
    )
    # Resolve dynamically: run_process binds its private registry after loading.
    staged = StagedAudio(fetch_audio, timings_of=lambda: worker.timings)

    def persist(item, payload):
        with leaf_timings.active(worker.timings):
            return persist_result(item, payload)

    worker = PipelineWorker(
        decode=staged.decode,
        vad=PyannoteVAD(vad_model),
        words_providers={'parakeet': words},
        recover_words=words.recover_empty,
        diarizers={'pyannote': PyannoteDiarizer(pyannote_model, timings_of=lambda: worker.timings)},
        persist=persist,
        config=config,
        live_words=live_words,
        single_speaker=single_speaker,
        on_failure=on_failure,
        flight_models=flight,
        stream_of=staged.stream,
        language_of=staged.language,
    )
    return worker
