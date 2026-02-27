FROM python:3.11 AS builder

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
    cd /tmp/liblc3 && \
    python3 -m pip wheel --no-cache-dir --wheel-dir /tmp/wheels .

# Install Python requirements
WORKDIR /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt

FROM python:3.11-slim

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

RUN apt-get update && apt-get -y install ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*

# Copy compiled liblc3 library and wheel from builder
COPY --from=builder /usr/local/lib/liblc3.so* /usr/local/lib/
COPY --from=builder /tmp/wheels /tmp/wheels

# Install liblc3 Python package and set library path
RUN ldconfig && \
    pip install --no-cache-dir /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

COPY --from=builder /opt/venv /opt/venv
COPY backend/ .

EXPOSE 8080
CMD ["uvicorn", "pusher.main:app", "--host", "0.0.0.0", "--port", "8080"]
