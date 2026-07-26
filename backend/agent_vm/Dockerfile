ARG PYTHON_BASE_IMAGE=gcr.io/based-hardware-dev/python:3.11-slim-forky
ARG UV_VERSION=0.11.13

FROM oven/bun:1.2.4 AS bun

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG UV_VERSION

RUN python -m venv /opt/venv
RUN python3 -m pip install --no-cache-dir "uv==${UV_VERSION}"
COPY backend/agent_vm/pylock.toml /tmp/pylock.toml
RUN uv pip sync /tmp/pylock.toml --python /opt/venv/bin/python --compile-bytecode

FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app
ENV BUN_INSTALL=/opt/bun
ENV PATH="/opt/bun/bin:/opt/venv/bin:$PATH"

COPY --from=bun /usr/local/bin/bun /opt/bun/bin/bun
RUN bunx playwright@1.59.0-alpha-1770338664000 install --with-deps chromium
RUN bun add --global @playwright/mcp@0.0.64
COPY --from=builder /opt/venv /opt/venv
COPY backend/agent_vm/main.py .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
