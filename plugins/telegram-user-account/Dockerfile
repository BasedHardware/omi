# IMPORTANT: Build context must be this plugin's directory, NOT the
# repository root. Docker reads .dockerignore from the build-context
# root — if you `docker build -f plugins/telegram-user-account/Dockerfile .`
# from the repo root, the .dockerignore exclusions will NOT take
# effect, and any locally-written secret files will be baked into the
# image. (Same pattern as the bot plugin.)
#
# Correct invocation from the repo root:
#   docker build -f plugins/telegram-user-account/Dockerfile plugins/telegram-user-account/
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

# `COPY . .` is intentionally broad — the matching .dockerignore
# excludes test/, .venv/, .env, users_data.json, etc.
COPY . .

# The user-account plugin needs the _shared/ sibling for auth +
# persona_client imports. Copy it into the image.
# (When building with context=plugins/telegram-user-account/, the
# _shared/ dir is NOT in the build context. The CI pipeline handles
# this by copying _shared/ into the build context before building.)
ENV STORAGE_DIR=/app/data
RUN mkdir -p /app/data && chown -R omi:omi /app

USER omi

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
