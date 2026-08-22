FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ARG UV_VERSION=0.12.5

# Patch OS packages before installing runtime deps (#7136).
# NLLB stays on the CUDA Ubuntu base's system Python; install uv for deps.
RUN apt-get update && \
    apt-get -y dist-upgrade && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --python python3 --system --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
