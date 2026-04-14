#!/bin/bash
# Thin wrapper — all logic lives in run.sh
exec "$(dirname "$0")/run.sh" --release "$@"
