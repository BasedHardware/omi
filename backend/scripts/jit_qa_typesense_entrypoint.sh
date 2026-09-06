#!/bin/sh
set -eu

: "${TYPESENSE_API_KEY:?TYPESENSE_API_KEY must be provided by the dedicated QA secret}"

if command -v typesense-server >/dev/null 2>&1; then
    typesense_binary="$(command -v typesense-server)"
elif [ -x /opt/typesense-server/typesense-server ]; then
    typesense_binary="/opt/typesense-server/typesense-server"
else
    echo "Typesense server binary is unavailable in the pinned image" >&2
    exit 78
fi

exec "$typesense_binary" \
    --data-dir "${TYPESENSE_DATA_DIR:-/tmp/typesense}" \
    --api-address 0.0.0.0 \
    --api-port "${PORT:-8080}" \
    --api-key "$TYPESENSE_API_KEY"
