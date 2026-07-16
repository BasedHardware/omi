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
# P2 (cubic, PR #8682): pin the Dockerfile to the exact patch version
# declared in plugins/omi-whatsapp-app/runtime.txt so the Heroku /
# Docker interpreters don't drift apart. Without this, runtime.txt
# could pin 3.11.11 while the Docker image silently upgrades to the
# latest 3.11.x slim point release — which on Heroku means the user's
# local Docker testing sees a different interpreter than the deployed
# workers. Keep the two values in lockstep when bumping.
FROM python:3.11.11-slim

# Create non-root user early so owned dirs/files get correct uid/gid
RUN groupadd --system --gid 1001 omi \
    && useradd --system --uid 1001 --gid omi --no-create-home omi

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Belt-and-suspenders against accidental secret inclusion regardless of
# the build context. P1 from cubic AI review (PR #8682): the previous
# design relied entirely on the caller passing this plugin's directory
# as the build context (`docker build plugins/omi-whatsapp-app/`) so
# that .dockerignore at plugins/omi-whatsapp-app/.dockerignore would
# exclude .env / users_data.json / pending_setups.json. Invoking
# `docker build -f plugins/omi-whatsapp-app/Dockerfile .` from the repo
# root would silently use the repo-root .dockerignore (which doesn't
# exclude our secrets) and bake them into the image. To make secret
# exclusion robust regardless of context, refuse to build if any of
# the secret-bearing files are present after COPY — this catches the
# "wrong context" mistake at build time, not at image-push time.
RUN set -eu; \
    secrets_found=0; \
    # Check both WORKDIR-relative paths (correct-context build where
    # the plugin dir is the build root) AND plugin-local paths (repo-
    # root context where `COPY . .` lands the plugin at
    # /app/plugins/omi-whatsapp-app/). The latter is a P1 from cubic
    # AI review (PR #8682 follow-up 4601469127): the previous guard
    # only checked WORKDIR-rooted paths and silently allowed secrets
    # through when the build context was the repo root, since the
    # files landed at /app/plugins/omi-whatsapp-app/users_data.json
    # etc. — invisible to the WORKDIR-rooted checks.
    for path in \
        .env .env.local users_data.json pending_setups.json \
        plugins/omi-whatsapp-app/.env plugins/omi-whatsapp-app/.env.local \
        plugins/omi-whatsapp-app/users_data.json plugins/omi-whatsapp-app/pending_setups.json \
    ; do \
        if [ -e "$path" ]; then \
            echo "ERROR: secret-bearing file '$path' found in build context. \
Build context must be the plugin directory, not the repo root. \
Run 'docker build plugins/omi-whatsapp-app/' or 'cd plugins/omi-whatsapp-app && docker build .'." >&2; \
            secrets_found=1; \
        fi; \
    done; \
    [ "$secrets_found" = "0" ] || exit 1

ENV STORAGE_DIR=/app/data
RUN mkdir -p /app/data && chown -R omi:omi /app

USER omi

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]