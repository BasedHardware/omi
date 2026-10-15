"""Lazy startup for the dedicated one-process/one-GPU chain."""

import os
from pathlib import Path
import resource
import sys

try:
    import torch  # type: ignore[reportMissingImports]  # Optional GPU image dependency
    import nemo.collections.asr as nemo_asr  # type: ignore[reportMissingImports]  # Optional GPU image dependency
    from pyannote.audio import Pipeline  # type: ignore[reportMissingImports]  # Optional GPU image dependency
    from pyannote.audio.pipelines import VoiceActivityDetection  # type: ignore[reportMissingImports]
    from huggingface_hub import hf_hub_download
except ImportError:
    torch = None
    nemo_asr = None
    Pipeline = None
    VoiceActivityDetection = None
    hf_hub_download = None

from diarizer.batch_pipeline_models import create_local_worker

ASR_REVISION = '541d1f99c6b0c3cd0b11a95167540bb8edefd82b'
DIARIZER_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'


def load_worker(artifacts):
    if torch is None or nemo_asr is None or Pipeline is None or VoiceActivityDetection is None:
        raise RuntimeError('batch worker requires the joint GPU image')
    if hf_hub_download is None or not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError('batch worker requires exactly one visible dedicated CUDA GPU')
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError('batch worker requires BF16 ASR support')
    checkpoint = hf_hub_download('nvidia/parakeet-tdt-0.6b-v3', 'parakeet-tdt-0.6b-v3.nemo', revision=ASR_REVISION)
    asr = nemo_asr.models.ASRModel.restore_from(checkpoint, map_location='cuda:0').to(torch.bfloat16).eval()
    diarizer = Pipeline.from_pretrained(
        'pyannote/speaker-diarization-community-1',
        revision=DIARIZER_REVISION,
        token=os.getenv('HUGGINGFACE_TOKEN'),
    ).to(torch.device('cuda:0'))
    # Never apply BF16 autocast to segmentation: the quality lane rejected it.
    segmentation = diarizer._segmentation.model.float().eval()
    vad = VoiceActivityDetection(segmentation=segmentation)
    # Community-1 powerset segmentation fixes onset/offset at 0.5; they are
    # constants, not tunable pipeline parameters.
    vad.instantiate({'min_duration_on': 0.0, 'min_duration_off': 0.0})
    vad.to(torch.device('cuda:0'))
    return create_local_worker(
        fetch_audio=artifacts.fetch_audio,
        persist_result=artifacts.persist_result,
        vad_model=vad,
        parakeet_model=asr,
        pyannote_model=diarizer,
    )


def synchronize_gpu():
    if torch is None:
        raise RuntimeError('CUDA runtime unavailable')
    torch.cuda.synchronize()


class ChainMemoryProbe:
    """Full-flight CUDA peak plus process/container lifetime host peaks in bytes.

    Reset CUDA counters only after models are resident, before the locked chain.
    Host peaks intentionally include startup; the chart limit governs host RAM.
    """

    def __init__(self, cuda=None):
        self.cuda = cuda if cuda is not None else (torch.cuda if torch is not None else None)

    def begin(self):
        if self.cuda is None:
            raise RuntimeError('CUDA runtime unavailable for memory qualification')
        self.cuda.synchronize()
        self.cuda.reset_peak_memory_stats()
        return {
            'gpu_allocated_baseline_bytes': self.cuda.memory_allocated(),
            'gpu_reserved_baseline_bytes': self.cuda.memory_reserved(),
        }

    def finish(self, baseline):
        if self.cuda is None:
            raise RuntimeError('CUDA runtime unavailable for memory qualification')
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result = {
            **baseline,
            'gpu_allocated_peak_bytes': self.cuda.max_memory_allocated(),
            'gpu_reserved_peak_bytes': self.cuda.max_memory_reserved(),
            'host_process_peak_bytes': int(peak if sys.platform == 'darwin' else peak * 1024),
        }
        for path in ('/sys/fs/cgroup/memory.peak', '/sys/fs/cgroup/memory/memory.max_usage_in_bytes'):
            try:
                result['host_container_peak_bytes'] = int(Path(path).read_text().strip())
                break
            except (OSError, ValueError):
                continue
        return result
