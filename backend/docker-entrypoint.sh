#!/bin/bash
set -e

echo "Starting Omi Backend..."

# Create credentials file from environment variable if provided
if [ -n "$SERVICE_ACCOUNT_JSON" ]; then
    echo "Creating google-credentials.json from SERVICE_ACCOUNT_JSON environment variable..."

    # Use printf to handle escaped characters properly
    printf '%s\n' "$SERVICE_ACCOUNT_JSON" > /app/google-credentials.json

    # Validate it's proper JSON
    if ! python3 -c "import json; json.load(open('/app/google-credentials.json'))" 2>/dev/null; then
        echo "ERROR: SERVICE_ACCOUNT_JSON is not valid JSON"
        echo "Content (first 100 chars): ${SERVICE_ACCOUNT_JSON:0:100}"
        echo "Trying to unescape the JSON..."

        # Try to unescape using Python
        python3 -c "
import json
import os
import sys

raw = os.environ.get('SERVICE_ACCOUNT_JSON', '')
# Try to parse as-is first
try:
    data = json.loads(raw)
    with open('/app/google-credentials.json', 'w') as f:
        json.dump(data, f)
    print('✓ Successfully unescaped and created credentials file')
    sys.exit(0)
except:
    # If that fails, try treating it as escaped string
    try:
        # Remove extra escaping
        unescaped = raw.encode().decode('unicode_escape')
        data = json.loads(unescaped)
        with open('/app/google-credentials.json', 'w') as f:
            json.dump(data, f)
        print('✓ Successfully unescaped and created credentials file')
        sys.exit(0)
    except Exception as e:
        print(f'ERROR: Could not process SERVICE_ACCOUNT_JSON: {e}')
        sys.exit(1)
"
        if [ $? -ne 0 ]; then
            exit 1
        fi
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
