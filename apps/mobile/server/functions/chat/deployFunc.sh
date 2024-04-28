#!/bin/bash

CHAT_SERVICE_FILE="../../services/chat_services.py"

cp "$CHAT_SERVICE_FILE" .

gcloud functions deploy chat \
  --gen2 \
  --runtime=python311 \
  --trigger-http \
  --entry-point=chat \
  --region=us-west1 \
  --source=. \
  --allow-unauthenticated \
  --timeout=540s \