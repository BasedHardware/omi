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