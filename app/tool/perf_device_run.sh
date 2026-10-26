#!/usr/bin/env bash
# Physical DEV-device benchmark. See tool/perf/README.md.
set -euo pipefail
exec python3 -I "$(dirname "$0")/perf/device_run.py" "$@"
