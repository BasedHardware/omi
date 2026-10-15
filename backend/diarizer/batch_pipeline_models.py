"""Local model adapters. Models are explicitly constructed once at worker startup.

Do not import the existing Parakeet GPUWorker here: it owns a second GPU thread
and loads unrelated embedding models. This chain is the sole model owner.
"""

import io
import wave
import numpy as np

try:
    import torch  # GPU runtime dependency, absent in the backend unit environment
except ImportError:
    torch = None

from config.batch_pipeline_providers import provider_config
from diarizer.batch_pipeline import PipelineWorker
from utils.stt.diarization_turns import exclusive_from_activity, overlap_regions


class ParakeetWords:
    def __init__(self, model):
        self.model = model

    def transcribe_batch(self, samples):
        # NeMo accepts float32 16kHz arrays: no file write, read or second decode.
        hypotheses = self.model.transcribe(
            samples,
            batch_size=len(samples),
            timestamps=True,
            return_hypotheses=True,
            num_workers=0,
            verbose=False,
        )
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
        with torch.inference_mode():
            output = self.model({'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': 16000})
        return [(float(t.start), float(t.end)) for t in output.get_timeline().support()]


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
    return PipelineWorker(
        decode=lambda item: decode_pcm16_wav(fetch_audio(item)),
        vad=PyannoteVAD(vad_model),
        words_providers={'parakeet': ParakeetWords(parakeet_model)},
        diarizers={'pyannote': PyannoteDiarizer(pyannote_model)},
        persist=persist_result,
        config=config,
        live_words=live_words,
        single_speaker=single_speaker,
        on_failure=on_failure,
    )
