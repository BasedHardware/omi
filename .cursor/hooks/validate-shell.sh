#!/bin/bash
# Shell command validation hook for Cursor
# Blocks dangerous operations and checks for exposed secrets

set -e

# Get command from stdin
COMMAND="${1:-}"

if [ -z "$COMMAND" ]; then
    exit 0
fi

# Dangerous commands to block
DANGEROUS_PATTERNS=(
    "rm -rf /"
    "rm -rf ~"
    "rm -rf \$HOME"
    "git push --force"
    "git push -f"
    "git push origin --force"
    "dd if="
    "mkfs"
    "fdisk"
    "format c:"
    ":(){ :|:& };:"
)

# Check for dangerous patterns
for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if echo "$COMMAND" | grep -qi "$pattern"; then
        echo "❌ BLOCKED: Dangerous command detected: $pattern"
        exit 1
    fi
done

# Check for potential secret exposure
SECRET_PATTERNS=(
    "OPENAI_API_KEY="
    "DEEPGRAM_API_KEY="
    "PINECONE_API_KEY="
    "REDIS_DB_PASSWORD="
    "GOOGLE_APPLICATION_CREDENTIALS="
    "api_key"
    "secret"
    "password"
    "token"
)

# Warn about potential secret exposure (non-blocking)
for pattern in "${SECRET_PATTERNS[@]}"; do
    if echo "$COMMAND" | grep -qi "$pattern"; then
        echo "⚠️  WARNING: Potential secret exposure detected in command"
        echo "   Review command before executing: $COMMAND"
    fi
done

# Allow command to proceed
exit 0
