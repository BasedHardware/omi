FROM python:3.12-slim-bookworm AS builder

# Install system dependencies for building
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /uvx /bin/

# Set up the working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .

# Install dependencies using uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync


# Set up the working directory
WORKDIR /app

# Copy application code
COPY . .


# Run the application
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
