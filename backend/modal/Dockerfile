FROM nvidia/cuda:12.6.2-cudnn-runtime-ubuntu22.04

WORKDIR /app

# Install Python and system dependencies
RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv ffmpeg curl unzip wget git && \
    rm -rf /var/lib/apt/lists/*
# Copy requirements and install
COPY backend/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ENV PATH="/opt/venv/bin:$PATH"

# Copy your app code
COPY backend/database /app/database
COPY backend/utils /app/utils
COPY backend/modal/ .
RUN if [ -f service-account.json ]; then cp service-account.json /app/service-account.json; fi

EXPOSE 8091
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8091"]