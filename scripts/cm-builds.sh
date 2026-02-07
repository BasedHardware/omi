#!/bin/bash
#
# Codemagic Build Status Checker
# Usage: ./cm-builds.sh [limit]
#

LIMIT=${1:-10}
APP_ID="66c95e6ec76853c447b8bcbb"

# Check for API token
if [ -z "$CODEMAGIC_API_TOKEN" ]; then
    echo "Error: CODEMAGIC_API_TOKEN not set"
    echo "Add to ~/.zshrc: export CODEMAGIC_API_TOKEN=\"your-token\""
    exit 1
fi

echo "Recent Codemagic builds (limit: $LIMIT):"
echo "----------------------------------------"

curl -s -H "Authorization: Bearer $CODEMAGIC_API_TOKEN" \
    "https://api.codemagic.io/builds?appId=$APP_ID&limit=$LIMIT" | \
    jq -r '.builds[] |
        (if .status == "building" then "🔨"
         elif .status == "finished" then "✅"
         elif .status == "failed" then "❌"
         elif .status == "skipped" then "⏭️"
         elif .status == "queued" then "⏳"
         else "❓" end) + " " +
        (.index | tostring) + " | " +
        .status + " | " +
        (.config.name // "unknown") + " | " +
        (.createdAt | split("T")[0])'
