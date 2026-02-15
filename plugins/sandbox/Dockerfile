FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get -y install curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY soul/ ./soul/
COPY prompts/ ./prompts/
COPY app/ ./app/

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
