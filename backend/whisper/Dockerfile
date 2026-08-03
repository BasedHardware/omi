# On-prem multilingual STT (faster-whisper / CTranslate2) as an OpenAI-compatible ASR server behind
# the parakeet gateway (ADR-0037 default engine). CTranslate2 on Blackwell (sm_120) needs CUDA 12.8 +
# cuDNN 9; the cudnn-runtime base ships both. Public base, builds directly (no NGC/Riva/TensorRT).
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
