#!/usr/bin/env bash
# Run the advisory STT wire-fidelity oracle against its loopback fake upstream.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Missing backend/.venv. Run make setup first." >&2
  exit 1
fi

PYTHONPATH=backend backend/.venv/bin/python -m testing.replay_harness_stt_wire_fidelity.oracle
