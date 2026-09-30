# NOTE: build with the repo's plugins/ directory as the build context so the
# sibling omi-plugin-sdk checkout is available for the ../omi-plugin-sdk
# requirement, e.g. from the repo root:
#   docker build -f plugins/omi-tasting-notes-app/Dockerfile plugins/
FROM python:3.11-slim

WORKDIR /app

# ../omi-plugin-sdk resolves to /omi-plugin-sdk from /app.
COPY omi-plugin-sdk /omi-plugin-sdk
COPY omi-tasting-notes-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY omi-tasting-notes-app/main.py .

ENV PORT=8080
ENV TASTING_DATA_DIR=/data
VOLUME /data

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
