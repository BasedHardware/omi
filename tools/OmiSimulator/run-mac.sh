#!/usr/bin/env bash
# Launch the Crepuscularity GPUI Omi BLE simulator (does not touch /Applications/Omi.app).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -x /Users/undivisible/projects/crepuscularity/scripts/metal-env.sh ]]; then
  # shellcheck disable=SC1090
  eval "$(/Users/undivisible/projects/crepuscularity/scripts/metal-env.sh)"
else
  export SDKROOT="${SDKROOT:-$(xcrun --show-sdk-path)}"
  export DEVELOPER_DIR="${DEVELOPER_DIR:-$(xcode-select -p)}"
  export TOOLCHAINS="${TOOLCHAINS:-Metal}"
fi
cd "$ROOT"
cargo build
exec cargo run
