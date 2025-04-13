FROM python:3.12-slim-bookworm as builder

# Install system dependencies for building
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /uvx /bin/

# Set up the working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .

# Create a virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies using uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -e .

# Final stage
FROM python:3.12-slim-bookworm

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Set up the working directory
WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Set the PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
