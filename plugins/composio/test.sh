#!/usr/bin/env bash
# Run the plugin's hermetic regression suite using its own dependency versions.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
exec uv run --isolated --no-project --python 3.11 \
  --with-requirements requirements.txt \
  python -m unittest discover -s tests -v
