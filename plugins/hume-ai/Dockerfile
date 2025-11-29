FROM python:3.11-slim AS builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim AS runner

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY main.py .
COPY app.py .
COPY emotion_config.json .
COPY templates/ templates/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
