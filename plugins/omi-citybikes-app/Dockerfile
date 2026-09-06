FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + (os.environ.get('PORT', '8000')) + '/health')" || exit 1

# Start FastAPI application
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
