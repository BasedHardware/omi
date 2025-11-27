#!/bin/bash
set -e

echo "Starting Omi Backend..."

# Create credentials file from environment variable if provided
if [ -n "$SERVICE_ACCOUNT_JSON" ]; then
    echo "Creating google-credentials.json from SERVICE_ACCOUNT_JSON environment variable..."
    echo "$SERVICE_ACCOUNT_JSON" > /app/google-credentials.json

    # Validate it's proper JSON
    if ! python3 -c "import json; json.load(open('/app/google-credentials.json'))" 2>/dev/null; then
        echo "ERROR: SERVICE_ACCOUNT_JSON is not valid JSON"
        echo "Content (first 100 chars): ${SERVICE_ACCOUNT_JSON:0:100}"
        exit 1
    fi

    echo "✓ Successfully created /app/google-credentials.json"
    export GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json
elif [ -f "/app/google-credentials.json" ]; then
    echo "✓ Found existing google-credentials.json"
    export GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json
else
    echo "WARNING: No Google credentials found!"
    echo "Please set SERVICE_ACCOUNT_JSON environment variable or mount google-credentials.json file"
fi

# Execute the main command
exec "$@"
