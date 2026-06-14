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

# NGC ships torch+torchvision with CUDA 12.8 but no torchaudio.
# Standard PyPI torchaudio is ABI-incompatible with NGC's custom torch.
# Install from PyTorch's CUDA 12.8 wheel index for ABI-compatible builds.
# --no-deps prevents pulling in standard PyPI torch over NGC's build.
RUN TORCH_MM=$(python -c "import torch; print('.'.join(torch.__version__.split('.')[:2]))") && \
    pip install --no-cache-dir --no-deps \
    "torchaudio==${TORCH_MM}.*" \
    --index-url https://download.pytorch.org/whl/cu128

# Extra deps not in the NGC image.
# pyannote.audio installed --no-deps to prevent it and its transitive
# deps (speechbrain, torchmetrics) from upgrading torch/torchvision.
# Its non-torch deps are installed separately below.
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "python-multipart>=0.0.6" \
    "httpx>=0.28.0" \
    "langdetect>=1.0.9" \
    "prometheus-client>=0.21.0" \
    "soundfile>=0.13.0"

RUN pip install --no-cache-dir --no-deps "pyannote.audio>=3.1.0" && \
    pip install --no-cache-dir --no-deps \
    "pyannote.core" "pyannote.database" "pyannote.pipeline" \
    "speechbrain" "asteroid-filterbanks" "einops" "semver" \
    "hf_transfer" "tensorboardX"

COPY backend/parakeet/ .

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV HF_HOME=/root/.cache/huggingface
ENV NUMBA_CACHE_DIR=/tmp/numba_cache

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
