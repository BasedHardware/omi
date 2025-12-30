# Builder stage - compile liblc3
FROM tiangolo/uvicorn-gunicorn:python3.11 as builder

# Install build dependencies
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
    cd /tmp/liblc3 && \
    python3 -m pip wheel --no-cache-dir --wheel-dir /tmp/wheels .

# Runtime stage - minimal image
FROM tiangolo/uvicorn-gunicorn:python3.11

# Only install runtime dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled library and wheel from builder
COPY --from=builder /usr/local/lib/liblc3.so* /usr/local/lib/
COPY --from=builder /tmp/wheels /tmp/wheels

# Install liblc3 Python package and set library path
RUN ldconfig && \
    pip install --no-cache-dir /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Install Python requirements (now including lc3py if present)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app

#COPY . .
COPY ./routers ./routers
COPY ./pretrained_models ./pretrained_models
COPY ./database ./database
COPY ./migrations ./migrations
COPY ./memories-tuner ./tuner
COPY ./pusher ./pusher
COPY ./typesense ./typesense
COPY ./charts ./charts
COPY ./utils ./utils
COPY ./models ./models
COPY ./testing ./testing
COPY ./scripts ./scripts
COPY ./templates ./templates
COPY ./modal ./modal
COPY ./migration ./migration
COPY google-credentials.json ./


EXPOSE 8080

CMD uvicorn pusher.main:app --host 0.0.0.0 --port 8080 --limit-concurrency 16 --backlog 32
