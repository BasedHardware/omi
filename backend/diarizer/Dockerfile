# Default keeps the upstream private base (unchanged builds); on-prem overrides it with a
# public image, e.g. --build-arg PYTHON_BASE_IMAGE=python:3.11-slim (see SELFHOST_NOTES).
ARG PYTHON_BASE_IMAGE=gcr.io/based-hardware-dev/python:3.11-slim-forky

FROM ${PYTHON_BASE_IMAGE} AS builder

ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv

COPY backend/diarizer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM ${PYTHON_BASE_IMAGE}
# Python 3.11 on Debian 14 (Forky)

WORKDIR /app
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu"

# System CUDA runtime install. Default (INSTALL_SYSTEM_CUDA=1) keeps upstream's GPU-pod image
# byte-for-byte: CUDA Runtime 13.2 Update 1 only (the pod runs inference, no build tools like nvcc).
#
# On-prem overrides with --build-arg INSTALL_SYSTEM_CUDA=0: the ~3GB CUDA local-installer .deb is
# skipped entirely because torch 2.8.0's wheels already bundle the CUDA 12.8 runtime libraries
# (nvidia-*-cu12 in requirements.txt) — the only host-side dependency is the NVIDIA driver, injected
# at runtime by the container toolkit (CDI). This cuts the image from ~24.8GB to a few GB. cu12.8 is
# the version torch needs for Blackwell (sm_120) GPUs, so no system CUDA 13.2 is involved either way.
# Proven end-to-end by the speaker-embedding live contract test (ADR-0035). See SELFHOST_NOTES.
ARG INSTALL_SYSTEM_CUDA=1
RUN apt-get update && \
if [ "$INSTALL_SYSTEM_CUDA" = "1" ]; then \
apt-get -y install build-essential ffmpeg curl unzip wget && \
wget https://developer.download.nvidia.com/compute/cuda/13.2.1/local_installers/cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb && \
dpkg -i cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb && \
cp /var/cuda-repo-debian13-13-2-local/cuda-*-keyring.gpg /usr/share/keyrings/ && \
apt-get update && \
apt-get -y install cuda-runtime-13-2 && \
rm -f cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb; \
else \
apt-get -y install --no-install-recommends ffmpeg; \
fi && \
rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY backend/diarizer/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
