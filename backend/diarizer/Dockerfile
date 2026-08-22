ARG PYTHON_BASE_IMAGE=python:3.13-slim-bookworm
ARG UV_VERSION=0.12.5

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG UV_VERSION
ENV PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv && \
    python3 -m pip install --no-cache-dir "uv==${UV_VERSION}"

COPY backend/diarizer/requirements.txt /tmp/requirements.txt
RUN uv pip install --python /opt/venv/bin/python --no-cache-dir -r /tmp/requirements.txt

FROM ${PYTHON_BASE_IMAGE}
# Python 3.13 — speaker embedding GPU service

WORKDIR /app
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu"

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
COPY backend/diarizer/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
