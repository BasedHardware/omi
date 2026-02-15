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
COPY requirements.txt /tmp/requirements.txt

# Install heavy NVIDIA/torch packages first (allows Docker layer caching if one fails)
RUN pip install --no-cache-dir --timeout=600 torch==2.4.0 || \
    pip install --no-cache-dir --timeout=600 torch==2.4.0 || \
    pip install --no-cache-dir --timeout=600 torch==2.4.0

RUN pip install --no-cache-dir --timeout=600 torchaudio==2.4.0 torchvision==0.19.0 || \
    pip install --no-cache-dir --timeout=600 torchaudio==2.4.0 torchvision==0.19.0

# Install remaining requirements (exclude lc3py - it's built from source above)
RUN grep -v lc3py /tmp/requirements.txt > /tmp/requirements_filtered.txt && \
    pip install --no-cache-dir --upgrade --timeout=600 --retries 5 -r /tmp/requirements_filtered.txt

FROM python:3.11-slim

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

RUN apt-get update && apt-get -y install ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*

# Copy venv first so lc3py installs into it
COPY --from=builder /opt/venv /opt/venv

# Copy compiled liblc3 library and wheel from builder
COPY --from=builder /usr/local/lib/liblc3.so* /usr/local/lib/
COPY --from=builder /tmp/wheels /tmp/wheels

# Install liblc3 Python package into the venv
RUN ldconfig && \
    pip install --no-cache-dir /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels
COPY . .

# Copy and set permissions for entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080

# Health check for Coolify/Docker orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "pusher.main:app", "--host", "0.0.0.0", "--port", "8080"]
