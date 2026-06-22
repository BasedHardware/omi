# Parakeet ASR batch server on NeMo NGC 26.02.
#
# This base image ships PyTorch 2.6 + CUDA 12.8 + NeMo 2.3 —
# the exact stack benchmarked at 43 RPS sustained on L4 with
# zero CachingHostAllocator crashes.
#
# Build (from omi repo root):
#   docker build -f backend/parakeet/Dockerfile -t parakeet-batch .

FROM nvcr.io/nvidia/nemo:26.02

WORKDIR /app

# Install the beastoin/NeMo fork on top of the container's NeMo.
# --no-deps: don't reinstall PyTorch (breaks CUDA alignment)
# --force-reinstall: overwrite the container's nemo_toolkit
RUN pip install --no-cache-dir --no-deps --force-reinstall \
    "nemo_toolkit[asr] @ git+https://github.com/beastoin/NeMo.git@68d99a17944181452205dc60da21e82bf3647054"

# NGC torch ABI is incompatible with standard torchaudio C extensions.
# Install torchaudio --no-deps for the pure-Python compliance.kaldi module
# (wespeaker needs kaldi.fbank for mel filterbank features), then patch
# __init__.py to skip the C extension loader and only expose compliance.
RUN pip install --no-cache-dir --no-deps torchaudio && \
    printf '__version__ = "2.11.0-ngc-compat"\nfrom . import compliance\nfrom . import functional\n' > \
    /usr/local/lib/python3.12/dist-packages/torchaudio/__init__.py && \
    printf '_IS_TORCHAUDIO_EXT_AVAILABLE = False\ndef fail_if_no_align(*a, **kw): pass\ndef fail_if_no_sox(*a, **kw): pass\ndef fail_if_no_ffmpeg(*a, **kw): pass\ndef fail_if_no_soundfile(*a, **kw): pass\ndef fail_if_no_kaldi(*a, **kw): pass\n' > \
    /usr/local/lib/python3.12/dist-packages/torchaudio/_extension/__init__.py

# pyannote.audio.core.task imports torch_audiomentations for training-time
# data augmentation. We only use Model + Inference (embedding extraction),
# never the training pipeline. Stub the package with all symbols pyannote needs.
RUN mkdir -p /usr/local/lib/python3.12/dist-packages/torch_audiomentations/core \
             /usr/local/lib/python3.12/dist-packages/torch_audiomentations/augmentations \
             /usr/local/lib/python3.12/dist-packages/torch_audiomentations/utils && \
    printf '__version__ = "stub"\nclass Identity:\n    pass\n' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/__init__.py && \
    printf '' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/core/__init__.py && \
    printf 'class BaseWaveformTransform:\n    pass\n' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/core/transforms_interface.py && \
    printf '' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/augmentations/__init__.py && \
    printf 'class Mix:\n    pass\n' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/augmentations/mix.py && \
    printf '' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/utils/__init__.py && \
    printf 'def from_dict(*a, **kw):\n    pass\n' > \
    /usr/local/lib/python3.12/dist-packages/torch_audiomentations/utils/config.py

# Extra deps not in the NGC image.
# pyannote.audio and torch-dependent deps installed --no-deps to prevent
# upgrading torch/torchvision/torchaudio in the NGC stack.
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "python-multipart>=0.0.6" \
    "httpx>=0.28.0" \
    "langdetect>=1.0.9" \
    "prometheus-client>=0.21.0" \
    "soundfile>=0.13.0"

# pyannote.audio + deps. Post-install: stub telemetry (needs opentelemetry
# OTLP exporter which we don't need for inference-only usage).
RUN pip install --no-cache-dir --no-deps "pyannote.audio>=3.1.0,<4.0" && \
    pip install --no-cache-dir --no-deps \
    "pyannote.core" "pyannote.database" "pyannote.pipeline" \
    "speechbrain" "asteroid-filterbanks" "einops" "semver" \
    "hf_transfer" "tensorboardX" && \
    mkdir -p /usr/local/lib/python3.12/dist-packages/pyannote/audio/telemetry && \
    printf 'def set_opentelemetry_log_level(*a, **kw): pass\ndef set_telemetry_metrics(*a, **kw): pass\ndef track_model_init(*a, **kw): pass\ndef track_pipeline_init(*a, **kw): pass\ndef track_pipeline_apply(*a, **kw): pass\n' > \
    /usr/local/lib/python3.12/dist-packages/pyannote/audio/telemetry/__init__.py

COPY backend/parakeet/ .

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV HF_HOME=/root/.cache/huggingface
ENV NUMBA_CACHE_DIR=/tmp/numba_cache

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
