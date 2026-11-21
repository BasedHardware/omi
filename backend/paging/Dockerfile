FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY backend/paging/requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY backend/omi_logging.py .
COPY backend/paging/app.py backend/paging/bark.py backend/paging/oidc.py backend/paging/publisher.py backend/paging/run.py backend/paging/store.py ./paging/
USER 65532:65532
CMD ["python", "-m", "paging.run"]
