# IMPORTANT: Build context must be this plugin's directory, NOT the
# repository root. Docker reads .dockerignore from the build-context
# root — if you `docker build -f plugins/omi-whatsapp-app/Dockerfile .`
# from the repo root, the .env / users_data.json / pending_setups.json
# exclusions in plugins/omi-whatsapp-app/.dockerignore will NOT take
# effect, and any locally-written secret files will be baked into the
# image.
#
# Correct invocation from the repo root:
#   docker build -f plugins/omi-whatsapp-app/Dockerfile plugins/omi-whatsapp-app/
#
# Correct invocation from this directory:
#   docker build .
FROM python:3.11-slim

# Create non-root user early so owned dirs/files get correct uid/gid
RUN groupadd --system --gid 1001 omi \
    && useradd --system --uid 1001 --gid omi --no-create-home omi

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV STORAGE_DIR=/app/data
RUN mkdir -p /app/data && chown -R omi:omi /app

USER omi

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]