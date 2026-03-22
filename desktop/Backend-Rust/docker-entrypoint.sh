#!/bin/bash
set -e

echo "Starting Nooto Desktop Backend..."

# Create credentials file from environment variable if provided
# Matches the Python backend pattern: SERVICE_ACCOUNT_JSON is minified JSON
if [ -n "$SERVICE_ACCOUNT_JSON" ]; then
    echo "Creating google-credentials.json from SERVICE_ACCOUNT_JSON..."
    printf '%s\n' "$SERVICE_ACCOUNT_JSON" > /app/google-credentials.json
    echo "✓ Created /app/google-credentials.json"
    export GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json

elif [ -n "$SERVICE_ACCOUNT_JSON_BASE64" ]; then
    echo "Creating google-credentials.json from SERVICE_ACCOUNT_JSON_BASE64..."
    echo "$SERVICE_ACCOUNT_JSON_BASE64" | base64 -d > /app/google-credentials.json
    echo "✓ Created /app/google-credentials.json from base64"
    export GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json

elif [ -f "/app/google-credentials.json" ]; then
    echo "✓ Found existing google-credentials.json"
    export GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json
else
    echo "WARNING: No Google credentials found!"
    echo "Set SERVICE_ACCOUNT_JSON env var (minified JSON: cat creds.json | jq -c)"
fi

# Execute the main command
exec "$@"
