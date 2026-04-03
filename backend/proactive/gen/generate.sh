#!/usr/bin/env bash
# Regenerate Python gRPC stubs from the proto definition.
# Run from the repository root: bash backend/proactive/gen/generate.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PROTO_DIR="$REPO_ROOT/proto"
OUT_DIR="$REPO_ROOT/backend"

python3 -m grpc_tools.protoc \
    -I "$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    "$PROTO_DIR/proactive/v1/proactive.proto"

echo "Generated stubs in $OUT_DIR/proactive/v1/"
