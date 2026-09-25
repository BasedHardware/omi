ARG PYTHON_BASE_IMAGE=gcr.io/based-hardware-dev/python:3.11-slim-forky
ARG UV_VERSION=0.11.13

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG UV_VERSION

RUN python -m venv /opt/venv
RUN python3 -m pip install --no-cache-dir "uv==${UV_VERSION}"
ENV PATH="/opt/venv/bin:$PATH"

# Build locked source distributions such as webrtcvad.
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements from the pusher-specific checked-in lock.
WORKDIR /opt/venv
COPY backend/pusher/pylock.toml /tmp/pylock.toml
RUN uv pip sync /tmp/pylock.toml --python /opt/venv/bin/python --compile-bytecode

FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"

# Patch OS packages in this layer before installing runtime deps (#7136).
RUN apt-get update && apt-get -y dist-upgrade \
    && apt-get -y install --no-install-recommends ffmpeg curl libjemalloc2 && \
    groupadd --system --gid 10001 pusher && \
    useradd --system --uid 10001 --gid 10001 --home-dir /app pusher && \
    mkdir -p _temp _samples _segments _speech_profiles && \
    chown -R 10001:10001 _temp _samples _segments _speech_profiles && \
    rm -rf /var/lib/apt/lists/*

# jemalloc eliminates glibc malloc fragmentation that causes RSS to grow linearly
# under high-churn bytearray allocations from WebSocket audio streams (#6938)
# Use soname-only form so ld.so resolves via standard search paths (arch-portable)
ENV LD_PRELOAD=libjemalloc.so.2

COPY --from=builder /opt/venv /opt/venv

# Whitelist-copy only the modules pusher reaches
COPY backend/config/ ./config/
COPY backend/database/ ./database/
COPY backend/models/ ./models/
COPY backend/routers/ ./routers/
COPY backend/services/ ./services/
COPY backend/testing/parity_pack_v0/ ./testing/parity_pack_v0/
COPY backend/utils/ ./utils/
COPY backend/pusher/ ./pusher/

EXPOSE 8080
USER 10001:10001
CMD ["uvicorn", "pusher.main:app", "--host", "0.0.0.0", "--port", "8080", "--ws-ping-interval", "20", "--ws-ping-timeout", "20", "--loop", "uvloop"]
