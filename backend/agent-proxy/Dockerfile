FROM python:3.11-slim

WORKDIR /app

COPY backend/agent-proxy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/agent-proxy/main.py .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
