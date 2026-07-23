ARG PYTHON_BASE_IMAGE=gcr.io/based-hardware-dev/python:3.11-slim-forky
ARG UV_VERSION=0.11.13

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG UV_VERSION

RUN python -m venv /opt/venv
RUN python3 -m pip install --no-cache-dir "uv==${UV_VERSION}"
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/agent-proxy/pylock.toml /tmp/pylock.toml
RUN uv pip sync /tmp/pylock.toml --python /opt/venv/bin/python --compile-bytecode

FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv
COPY backend/utils/__init__.py ./utils/__init__.py
COPY backend/utils/executors.py ./utils/executors.py
COPY backend/agent-proxy/resilience.py .
COPY backend/agent-proxy/main.py .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop"]
