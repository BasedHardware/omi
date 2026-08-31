# Base image is overridable so on-prem can build on a PUBLIC image (the default is the private
# based-hardware base). compose.selfhost.yaml passes PYTHON_BASE_IMAGE=python:3.11-slim. Declared
# before the first FROM so both stages honor it (cubic review PR 10887, review 4939247683).
ARG PYTHON_BASE_IMAGE=gcr.io/based-hardware-dev/python:3.11-slim-forky

FROM ${PYTHON_BASE_IMAGE} AS builder

ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv

COPY backend/diarizer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM ${PYTHON_BASE_IMAGE}
# Python 3.11 on Debian 14 (Forky)

# Skip the ~3GB system CUDA install when 0: torch bundles its own cu12.8 runtime, so on-prem via CDI
# needs only the host driver (compose.selfhost.yaml passes INSTALL_SYSTEM_CUDA=0). Default 1 keeps the
# datacenter build unchanged. Stage-scoped ARG (declared after FROM).
ARG INSTALL_SYSTEM_CUDA=1

WORKDIR /app
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu"

# Common runtime deps always; system CUDA Runtime 13.2 only when INSTALL_SYSTEM_CUDA=1 (the pod runs
# inference and does not need nvcc). Patch OS packages before installing runtime deps (#7136).
RUN apt-get update && apt-get -y dist-upgrade && \
apt-get -y install --no-install-recommends build-essential ffmpeg curl unzip wget && \
if [ "$INSTALL_SYSTEM_CUDA" = "1" ]; then \
  wget https://developer.download.nvidia.com/compute/cuda/13.2.1/local_installers/cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb && \
  dpkg -i cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb && \
  cp /var/cuda-repo-debian13-13-2-local/cuda-*-keyring.gpg /usr/share/keyrings/ && \
  apt-get update && \
  apt-get -y install cuda-runtime-13-2 && \
  rm -f cuda-repo-debian13-13-2-local_13.2.1-595.58.03-1_amd64.deb ; \
fi && \
rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY backend/diarizer/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
