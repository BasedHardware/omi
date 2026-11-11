#!/usr/bin/env bash
# add-l10n-key.sh — retired.
# English-only jq inserts left the other locales untranslated. Use the
# keyless l10n tool, which writes every locale, regenerates, and formats:
#
#   python3 scripts/l10n.py template <key> > /tmp/tr.json
#   # fill every locale, then:
#   python3 scripts/l10n.py add <key> --en "<English>" --description "..." --translations /tmp/tr.json
set -euo pipefail
echo "error: add-l10n-key.sh is retired (English-only). Use: python3 scripts/l10n.py add --help" >&2
exit 2
