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
from diarizer.batch_pipeline import PipelineWorker, crop_model_vad_spans
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
    return PipelineWorker(
        decode=lambda item: decode_pcm16_wav(fetch_audio(item)),
        vad=PyannoteVAD(vad_model),
        words_providers={'parakeet': ParakeetWords(parakeet_model, enforce_eager=True)},
        diarizers={'pyannote': PyannoteDiarizer(pyannote_model)},
        persist=persist_result,
        config=config,
        live_words=live_words,
        single_speaker=single_speaker,
        on_failure=on_failure,
    )
