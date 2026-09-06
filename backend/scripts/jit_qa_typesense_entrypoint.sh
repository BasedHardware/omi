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

data_dir="${TYPESENSE_DATA_DIR:-/tmp/typesense}"
mkdir -p "$data_dir"

# Typesense 27.1 maps TYPESENSE_API_KEY to its api-key server setting. Keep
# the secret in the environment supplied by Cloud Run Secret Manager instead
# of exposing it in the process argument list.
exec "$typesense_binary" \
    --data-dir "$data_dir" \
    --api-address 0.0.0.0 \
    --api-port "${PORT:-8080}"
