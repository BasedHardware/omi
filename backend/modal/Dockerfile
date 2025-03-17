FROM python:3.11 AS builder

ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.11-slim
# Python 3.11 on Debian 12 (Bookworm)

WORKDIR /app
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/opt/venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64"

# Install CUDA Toolkit 12.6 Update 3
RUN apt-get update && apt-get -y install build-essential ffmpeg curl unzip wget software-properties-common && \ 
wget https://developer.download.nvidia.com/compute/cuda/12.6.3/local_installers/cuda-repo-debian12-12-6-local_12.6.3-560.35.05-1_amd64.deb && \
dpkg -i cuda-repo-debian12-12-6-local_12.6.3-560.35.05-1_amd64.deb && \
cp /var/cuda-repo-debian12-12-6-local/cuda-*-keyring.gpg /usr/share/keyrings/ && \
add-apt-repository contrib && \
apt-get update && \
apt-get -y install cuda-toolkit-12-6 && \
rm -rf /var/lib/apt/lists/* cuda-repo-debian11-12-6-local_12.6.3-560.35.05-1_amd64.deb

COPY --from=builder /opt/venv /opt/venv
COPY backend/database /app/database
COPY backend/utils /app/utils
COPY backend/modal/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
