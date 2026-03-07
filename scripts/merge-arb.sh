#!/usr/bin/env bash
# Custom merge driver for ARB (JSON) files.
# Keeps all our existing keys/values, but adds NEW keys from upstream.
# Usage in .gitattributes: *.arb merge=arb
#
# Git calls this as: merge-arb.sh %A %O %B
#   %A = current (ours), %O = ancestor, %B = other (upstream)
# We must write the result into %A and exit 0 for success.

OURS="$1"
BASE="$2"
THEIRS="$3"

if ! command -v jq &>/dev/null; then
  echo "merge-arb: jq is required but not found" >&2
  exit 1
fi

# Start with our version, then add any keys from upstream that we don't have.
# jq `*` does recursive merge — THEIRS * OURS means OURS values win on conflict,
# but new keys from THEIRS are added.
MERGED=$(jq -s '.[0] * .[1]' "$THEIRS" "$OURS" 2>/dev/null)

if [ $? -ne 0 ]; then
  # If jq fails (e.g. invalid JSON), fall back to keeping ours
  exit 0
fi

echo "$MERGED" > "$OURS"
exit 0
