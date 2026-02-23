FROM dhi.io/python:3.11-sfw-dev AS builder

ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv

COPY backend/diarizer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM dhi.io/python:3.11
# Python 3.11 on Debian 13 (Trixie)

WORKDIR /app
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64"

# Install CUDA Toolkit 13.1 Update 1
RUN apt-get update && apt-get -y install build-essential ffmpeg curl unzip wget && \ 
wget https://developer.download.nvidia.com/compute/cuda/13.1.1/local_installers/cuda-repo-debian13-13-1-local_13.1.1-590.48.01-1_amd64.deb && \
dpkg -i cuda-repo-debian13-13-1-local_13.1.1-590.48.01-1_amd64.deb && \
cp /var/cuda-repo-debian13-13-1-local/cuda-*-keyring.gpg /usr/share/keyrings/ && \
apt-get update && \
apt-get -y install cuda-toolkit-13-1 && \
rm -rf /var/lib/apt/lists/* cuda-repo-debian13-13-1-local_13.1.1-590.48.01-1_amd64.deb

COPY --from=builder /opt/venv /opt/venv
COPY backend/diarizer/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
