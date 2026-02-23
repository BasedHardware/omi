FROM dhi.io/python:3.11-sfw-dev AS builder

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
    ffmpeg \
    curl \
    unzip \
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

# Install Python requirements + liblc3 wheel
WORKDIR /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt && \
    pip install --no-cache-dir /tmp/wheels/*.whl

# Run ldconfig so liblc3.so is indexed
RUN ldconfig

FROM dhi.io/python:3.11

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Copy binaries from builder (no shell available in runtime image)
COPY --from=builder /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=builder /usr/bin/ffprobe /usr/bin/ffprobe
COPY --from=builder /usr/bin/curl /usr/bin/curl
COPY --from=builder /usr/bin/unzip /usr/bin/unzip
COPY --from=builder /usr/lib/ /usr/lib/
COPY --from=builder /etc/ssl/ /etc/ssl/

# Copy compiled liblc3 library and ldconfig cache from builder
COPY --from=builder /usr/local/lib/liblc3.so* /usr/local/lib/
COPY --from=builder /etc/ld.so.cache /etc/ld.so.cache

COPY --from=builder /opt/venv /opt/venv
COPY backend/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
