#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "$0")/../listen_pusher_stack/run.sh" --lifecycle-only "$@"
