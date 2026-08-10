#!/bin/bash
# Compatibility wrapper — prefer scripts/cm-builds
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cm-builds" "$@"
