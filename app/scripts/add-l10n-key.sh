#!/usr/bin/env bash
# add-l10n-key.sh — Add a localization key to the English ARB file.
# Usage: ./scripts/add-l10n-key.sh <keyName> <"English text"> [<"Description for translators">]
#
# Example:
#   ./scripts/add-l10n-key.sh settingsTitle "Settings" "Title for settings page"
#
# This adds the key to app_en.arb only. For all 33 non-English translations,
# use the 'omi-add-missing-language-keys-l10n' skill or add them manually
# with Python (jq breaks on apostrophes in French/Catalan/Italian).
#
# After adding keys, run: cd app && flutter gen-l10n
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARB_FILE="$APP_DIR/lib/l10n/app_en.arb"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <keyName> <\"English text\"> [<\"Description\">]"
  echo "Example: $0 settingsTitle \"Settings\" \"Title for settings page\""
  exit 1
fi

KEY="$1"
VALUE="$2"
DESC="${3:-}"

if ! command -v jq &>/dev/null; then
  echo "Error: jq is required. Install: apt install jq / brew install jq"
  exit 1
fi

if [[ ! -f "$ARB_FILE" ]]; then
  echo "Error: $ARB_FILE not found"
  exit 1
fi

# Check if key already exists
if jq -e "has(\"$KEY\")" "$ARB_FILE" >/dev/null 2>&1; then
  echo "Key '$KEY' already exists in app_en.arb"
  jq -r ".[\"$KEY\"]" "$ARB_FILE"
  exit 1
fi

# Add key + optional description (--indent 4 preserves ARB formatting)
if [[ -n "$DESC" ]]; then
  jq --indent 4 --arg k "$KEY" --arg v "$VALUE" --arg d "$DESC" \
    '. + {($k): $v, ("@" + $k): {"description": $d}}' \
    "$ARB_FILE" > "$ARB_FILE.tmp" && mv "$ARB_FILE.tmp" "$ARB_FILE"
else
  jq --indent 4 --arg k "$KEY" --arg v "$VALUE" \
    '. + {($k): $v}' \
    "$ARB_FILE" > "$ARB_FILE.tmp" && mv "$ARB_FILE.tmp" "$ARB_FILE"
fi

echo "Added '$KEY' = \"$VALUE\" to app_en.arb"

# Count non-English locales that need translation
non_en=$(ls "$APP_DIR/lib/l10n/app_"*.arb 2>/dev/null | grep -v app_en.arb | wc -l)
echo ""
echo "Next steps:"
echo "  1. Add translations to $non_en non-English locales"
echo "     (use 'omi-add-missing-language-keys-l10n' skill or Python script)"
echo "  2. Run: cd app && flutter gen-l10n"
echo "  3. Use context.l10n.$KEY in Dart code"
