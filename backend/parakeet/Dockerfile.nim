# NVIDIA NIM-based Parakeet deployment — auth gateway.
#
# This Dockerfile builds a lightweight FastAPI gateway that proxies
# transcription requests to an NVIDIA NIM ASR sidecar container.
#
# The NIM container (nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual)
# provides /v1/audio/transcriptions with TensorRT-optimized inference
# (~238x real-time on L4 GPU). This gateway adds the /health endpoint
# for load balancer checks. No auth needed — runs behind internal LB.
#
# Build:
#   docker build -f backend/parakeet/Dockerfile.nim -t parakeet-nim-gateway .
#
# Deployment (sidecar pattern in Kubernetes):
#   Pod has 2 containers:
#   1. This gateway (port 8080, no GPU) — proxies to NIM
#   2. NIM container (port 9000, GPU) — actual ASR inference
#
#   Helm changes needed for NIM mode:
#   - Add NIM sidecar container with GPU resources
#   - Add NGC image pull secret (nvcr.io registry)
#   - Add model cache volume (NIM downloads ~2GB model on first start)
#   - Set PARAKEET_INFERENCE_MODE=nim, NIM_INFERENCE_URL=http://localhost:9000
#
# Local dev (docker-compose):
#   docker run -d --gpus all -p 9000:9000 nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual:latest
#   docker run -p 8080:8080 -e NIM_INFERENCE_URL=http://host.docker.internal:9000 parakeet-nim-gateway

FROM gcr.io/based-hardware-dev/python:3.11-slim-forky

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv && \
    pip install --no-cache-dir \
    fastapi==0.121.0 \
    uvicorn[standard]==0.34.0 \
    python-multipart==0.0.18 \
    httpx==0.28.1 \
    numpy==2.4.0 \
    scipy>=1.11.0 \
    langdetect>=1.0.9

COPY backend/parakeet/main.py .
COPY backend/parakeet/transcribe.py .
COPY backend/parakeet/stream_handler.py .

ENV PARAKEET_INFERENCE_MODE=nim
ENV NIM_INFERENCE_URL=http://localhost:9000

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
