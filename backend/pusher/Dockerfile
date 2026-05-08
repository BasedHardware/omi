FROM gcr.io/based-hardware-dev/python:3.11-slim-forky AS builder

ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv

# Install build dependencies for liblc3
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    meson \
    ninja-build \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Build liblc3 and create wheel
WORKDIR /tmp
RUN git clone https://github.com/google/liblc3.git && \
    cd liblc3 && \
    meson setup build && \
    cd build && \
    meson install && \
    ldconfig && \
    # Stage shared libs to a fixed path (meson install path varies by arch)
    mkdir -p /opt/liblc3 && \
    cp /usr/local/lib/*/liblc3.so* /opt/liblc3/ 2>/dev/null || \
    cp /usr/local/lib/liblc3.so* /opt/liblc3/ && \
    cd /tmp/liblc3 && \
    python3 -m pip wheel --no-cache-dir --wheel-dir /tmp/wheels .

# Install Python requirements — pusher-specific (no torch/onnxruntime/pyannote)
WORKDIR /opt/venv
COPY backend/pusher/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt

FROM gcr.io/based-hardware-dev/python:3.11-slim-forky

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

RUN apt-get update && apt-get -y install ffmpeg curl libjemalloc2 && rm -rf /var/lib/apt/lists/*

# jemalloc eliminates glibc malloc fragmentation that causes RSS to grow linearly
# under high-churn bytearray allocations from WebSocket audio streams (#6938)
# Use soname-only form so ld.so resolves via standard search paths (arch-portable)
ENV LD_PRELOAD=libjemalloc.so.2

# Copy compiled liblc3 library from builder staging dir
COPY --from=builder /opt/liblc3/ /usr/local/lib/
COPY --from=builder /tmp/wheels /tmp/wheels

# Install liblc3 Python package and set library path
RUN ldconfig && \
    pip install --no-cache-dir /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

COPY --from=builder /opt/venv /opt/venv

# Whitelist-copy only the modules pusher reaches
COPY backend/database/ ./database/
COPY backend/models/ ./models/
COPY backend/routers/ ./routers/
COPY backend/utils/ ./utils/
COPY backend/pusher/ ./pusher/
# CI writes google-credentials.json to backend/ before build (gcp_backend_pusher.yml)
COPY backend/google-credentials.json ./google-credentials.json

EXPOSE 8080
CMD ["uvicorn", "pusher.main:app", "--host", "0.0.0.0", "--port", "8080", "--ws-ping-interval", "20", "--ws-ping-timeout", "20", "--loop", "uvloop"]
