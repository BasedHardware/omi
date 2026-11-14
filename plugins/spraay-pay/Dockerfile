FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py main.py models.py ./
COPY payment ./payment

RUN useradd --create-home spraay && mkdir /data && chown spraay /data
USER spraay
ENV DATABASE_PATH=/data/spraay.db
VOLUME /data
EXPOSE 8000

# Access logs stay off because Omi URLs carry the shared secret in the query string.
# One worker: the transcript buffer is held in process memory.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
