# NVIDIA NIM-based Parakeet deployment.
#
# Uses the official NIM container for TensorRT-optimized inference (~238x real-time on L4).
# The NIM container provides its own /v1/transcribe gRPC/REST endpoint, so this Dockerfile
# wraps it with our FastAPI auth layer and health check.
#
# Build:
#   docker build -f backend/parakeet/Dockerfile.nim -t parakeet-nim .
#
# Requires:
#   - NVIDIA GPU (L4 24GB recommended)
#   - NGC API key for pulling NIM image (NGC_CLI_API_KEY)
#   - PARAKEET_INFERENCE_MODE=nim
#   - NIM_INFERENCE_URL=http://localhost:9000 (sidecar pattern)
#
# Deployment pattern: run NIM container as a sidecar or separate pod,
# with this FastAPI service as the auth gateway.

FROM gcr.io/based-hardware-dev/python:3.11-slim-forky

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv && \
    pip install --no-cache-dir \
    fastapi==0.121.0 \
    uvicorn[standard]==0.34.0 \
    python-multipart==0.0.18 \
    httpx==0.28.1

COPY backend/parakeet/main.py .
COPY backend/parakeet/transcribe.py .

ENV PARAKEET_INFERENCE_MODE=nim
ENV NIM_INFERENCE_URL=http://localhost:9000

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
