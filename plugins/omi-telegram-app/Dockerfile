# IMPORTANT: Build context must be this plugin's directory, NOT the
# repository root. Docker reads .dockerignore from the build-context
# root — if you `docker build -f plugins/omi-telegram-app/Dockerfile .`
# from the repo root, the .env / users_data.json / pending_setups.json
# exclusions in plugins/omi-telegram-app/.dockerignore will NOT take
# effect, and any locally-written secret files will be baked into the
# image. (Identified by cubic P2.)
#
# Correct invocation from the repo root:
#   docker build -f plugins/omi-telegram-app/Dockerfile plugins/omi-telegram-app/
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

# `COPY . .` is intentionally broad here — the matching .dockerignore
# (in this same directory) excludes test/, .venv/, .env, users_data.json,
# pending_setups.json, .aidlc/, requirements-dev.txt, etc. The build-context
# requirement (header comment above) is the second line of defence.
# Identified by cubic (P2) on PR #8531.
COPY . .

ENV STORAGE_DIR=/app/data
RUN mkdir -p /app/data && chown -R omi:omi /app

USER omi

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]