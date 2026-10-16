"""Local model adapters. Models are explicitly constructed once at worker startup.

Do not import the existing Parakeet GPUWorker here: it owns a second GPU thread
and loads unrelated embedding models. This chain is the sole model owner.
"""

import io
from copy import deepcopy
from contextlib import nullcontext
import wave
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
from diarizer.batch_pipeline import PipelineWorker, SAMPLE_RATE, crop_model_vad_spans, validate_words
from utils.stt.diarization_turns import exclusive_from_activity, overlap_regions


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
            if hypothesis.text.strip() and not words:
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
        padded_seconds = (len(samples) + left + right) / SAMPLE_RATE
        if padded_seconds > min(120, max_padded_seconds):
            # The callback identifies enforced dispatch. Main's unflagged
            # adapter still returns an empty hypothesis; policy holds must not
            # spend a provider-failure attempt for audio never submitted.
            return None if before_dispatch is not None else []
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
    def __init__(self, model):
        self.model = model

    def __call__(self, samples):
        if torch is None:
            raise RuntimeError('pyannote adapter requires the GPU runtime with torch')
        with torch.inference_mode():
            output = self.model({'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': 16000})
        activity = [
            {'start': float(t.start), 'end': float(t.end), 'speaker': str(s)} for t, s in output.speaker_diarization
        ]
        exclusive = getattr(output, 'exclusive_speaker_diarization', None)
        turns = (
            [{'start': float(t.start), 'end': float(t.end), 'speaker': str(s)} for t, s in exclusive]
            if exclusive is not None
            else exclusive_from_activity(activity)
        )
        return {'turns': turns, 'overlaps': overlap_regions(activity), 'backend': 'pyannote'}


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
    on_failure=None
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
    return PipelineWorker(
        decode=lambda item: decode_pcm16_wav(fetch_audio(item)),
        vad=PyannoteVAD(vad_model),
        words_providers={'parakeet': words},
        recover_words=words.recover_empty,
        diarizers={'pyannote': PyannoteDiarizer(pyannote_model)},
        persist=persist_result,
        config=config,
        live_words=live_words,
        single_speaker=single_speaker,
        on_failure=on_failure,
    )
