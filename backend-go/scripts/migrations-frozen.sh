#!/bin/bash
# migrations-frozen.sh BASE: fail if a migration that exists at BASE was changed or removed.
#
# An applied migration is never edited: databases that already ran it would silently differ
# from new ones. A schema change is a new numbered file. BASE is the commit or ref the change
# will merge into; files that are new since BASE may be anything.
set -euo pipefail

base=${1:?usage: migrations-frozen.sh BASE_REF}
root=$(git rev-parse --show-toplevel)
cd "$root"
changed=$(git diff --name-status --no-renames "$base"...HEAD -- '*/migrations/*.sql' | awk '$1 != "A" {print $1 "\t" $2}')
if [[ -n $changed ]]; then
    printf 'These migrations exist at %s and were changed or removed:\n%s\n' "$base" "$changed" >&2
    echo 'Add a new numbered file instead of editing one that may already be applied.' >&2
    exit 1
fi
