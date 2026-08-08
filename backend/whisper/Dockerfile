# On-prem multilingual STT (faster-whisper / CTranslate2) as an OpenAI-compatible ASR server behind
# the parakeet gateway (ADR-0037 default engine). CTranslate2 on Blackwell (sm_120) needs CUDA 12.8 +
# cuDNN 9; the cudnn-runtime base ships both. Public base, builds directly (no NGC/Riva/TensorRT).
#
# Intentionally NOT registered in backend/runtime_images.json: that registry is for cloud-deployed
# images and requires every entry to reference an existing GCP deploy workflow
# (backend/scripts/runtime_image_contracts.py enforces `deployment_workflows` non-empty + on-disk).
# This service is on-prem/compose-only and has no such workflow. Its offline build + dependency
# import is covered instead by deploy/onprem/run-inference-live-tests.sh (compose build + live STT)
# and the hermetic tests in backend/tests/unit/test_whisper_service.py.
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# Ubuntu 22.04's apt python3 is 3.10; the repo mandates Python 3.11 (AGENTS.md). Install 3.11 from
# deadsnakes so this service matches the rest of the backend's runtime contract.
# Build-scoped (does not persist to the runtime image): software-properties-common pulls tzdata,
# whose postinst prompts for a timezone interactively and would hang the build without this.
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends software-properties-common gnupg && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-dev && \
    python3.11 -m ensurepip --upgrade && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Run as non-root: this endpoint consumes untrusted multipart uploads, so drop root to shrink the
# blast radius of a decode/parse exploit. Models are pre-provisioned read-only into the mounted
# volume (HF_HOME); multipart spooling uses world-writable /tmp, so no app-owned writable dir is
# needed. --gid stays default; uid is fixed for reproducible ownership.
RUN useradd --create-home --uid 10001 whisper
USER whisper

EXPOSE 8000

CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
