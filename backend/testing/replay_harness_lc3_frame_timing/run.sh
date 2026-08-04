#!/usr/bin/env bash
# Run the LC3 frame-cadence oracle only where the locked lc3py wheel is supported.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "Replay LC3 frame-timing oracle requires Linux x86_64 with the locked lc3py==1.1.3 backend environment; this host is unsupported." >&2
  exit 2
fi

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Missing backend/.venv. Sync the locked Linux backend dependencies before running this oracle." >&2
  exit 2
fi

# Imports of the production runtime require this test-only local value. It is
# never emitted by the oracle, passed to a provider, or persisted.
export ENCRYPTION_SECRET="${ENCRYPTION_SECRET:-replay_lc3_frame_timing_test_secret}"

PYTHONPATH=backend backend/.venv/bin/python -m testing.replay_harness_lc3_frame_timing.oracle
