#!/usr/bin/env bash
set -euo pipefail
# One entrypoint for mobile verification lanes (SCA-490 / C4):
# select | doctor | fast | smoke | physical. See MOBILE_VERIFY.md.
# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
# shellcheck source=_resolve_python.sh
source "$(dirname "$0")/_resolve_python.sh"
cd "$(dirname "$0")/../.."
PYTHON_BIN="$(dev_harness_python)"
HARNESS_PYTHONPATH="$(dev_harness_pythonpath "$PYTHON_BIN" scripts/dev-harness)"
dev_harness_require_cli "$PYTHON_BIN" "$HARNESS_PYTHONPATH"
PYTHONPATH="$HARNESS_PYTHONPATH" "$PYTHON_BIN" -m dev_harness.mobile_verify "$@"
