#!/bin/bash
set -e

echo "Starting Omi Backend..."

# Create credentials file from environment variable if provided
# Support base64 encoded JSON (recommended for avoiding escape issues)
if [ -n "$SERVICE_ACCOUNT_JSON_BASE64" ]; then
    echo "Creating google-credentials.json from SERVICE_ACCOUNT_JSON_BASE64 environment variable..."

    # Use Python for reliable base64 decoding (works across all platforms)
    python3 -c "
import base64
import json
import os
import sys

b64_value = os.environ.get('SERVICE_ACCOUNT_JSON_BASE64', '')
try:
    decoded = base64.b64decode(b64_value).decode('utf-8')
    # Validate it's proper JSON
    data = json.loads(decoded)
    with open('/app/google-credentials.json', 'w') as f:
        json.dump(data, f)
    print('✓ Successfully created /app/google-credentials.json from base64')
except Exception as e:
    print(f'ERROR: Failed to decode SERVICE_ACCOUNT_JSON_BASE64: {e}')
    sys.exit(1)
"
    if [ $? -ne 0 ]; then
        exit 1
    fi

    export GOOGLE_APPLICATION_CREDENTIALS=/app/google-credentials.json
elif [ -n "$SERVICE_ACCOUNT_JSON" ]; then
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
