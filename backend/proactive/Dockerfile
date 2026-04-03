FROM python:3.11-slim

WORKDIR /app

COPY proactive/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY proactive/ /app/proactive/

ENV PYTHONPATH=/app
EXPOSE 50051

CMD ["python", "-m", "proactive.main"]
