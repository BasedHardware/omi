ARG PYTHON_BASE_IMAGE=python:3.13-slim-bookworm
ARG UV_VERSION=0.12.5

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG UV_VERSION
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_LINK_MODE=copy

RUN python -m venv /opt/venv && \
    python3 -m pip install --no-cache-dir "uv==${UV_VERSION}"

RUN apt-get update && apt-get install -y \
    git \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/omi-backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode
COPY backend/modal/requirements.txt /tmp/modal-requirements.txt
RUN uv pip install --python /opt/venv/bin/python --no-cache-dir -r /tmp/modal-requirements.txt

FROM ${PYTHON_BASE_IMAGE}
# Python 3.13 — GPU VAD / speaker identification

WORKDIR /app
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64"

# Install CUDA Runtime 13.2 Update 1 only; the pod runs inference and does not need build tools like nvcc.
# Patch OS packages before installing runtime deps (#7136).
RUN apt-get update && apt-get -y dist-upgrade && \
apt-get -y install --no-install-recommends build-essential ffmpeg curl unzip wget && \
wget https://developer.download.nvidia.com/compute/cuda/13.2.1/local_installers/cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb && \
dpkg -i cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb && \
cp /var/cuda-repo-debian13-13-2-local/cuda-*-keyring.gpg /usr/share/keyrings/ && \
apt-get update && \
apt-get -y install cuda-runtime-13-2 && \
rm -rf /var/lib/apt/lists/* cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb

COPY --from=builder /opt/venv /opt/venv
COPY backend/config/__init__.py backend/config/plan_catalog.py backend/config/plan_catalog_generated.py /app/config/
COPY backend/database /app/database
COPY backend/utils /app/utils
COPY backend/models /app/models
COPY backend/modal/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
