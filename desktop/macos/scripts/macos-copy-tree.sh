#!/bin/bash
# Copy a file or directory into the app bundle.
# On Darwin, clone file contents when the destination volume supports it.
# --norsrc / cp -X keep resource forks out of the bundle, matching the
# historical ditto --norsrc copy.

macos_ditto_supports_clone() {
  if [ -z "${MACOS_DITTO_SUPPORTS_CLONE+x}" ]; then
    # ditto --help exits non-zero. Capture it so pipefail does not hide --clone.
    local help_text
    help_text="$(ditto --help 2>&1 || true)"
    if printf '%s\n' "$help_text" | grep -q -- '--clone'; then
      MACOS_DITTO_SUPPORTS_CLONE=1
    else
      MACOS_DITTO_SUPPORTS_CLONE=0
    fi
  fi
  [ "$MACOS_DITTO_SUPPORTS_CLONE" = "1" ]
}

macos_copy_tree() {
  local src="$1"
  local dest="$2"
  if [ "$(uname -s)" = "Darwin" ] && command -v ditto >/dev/null 2>&1; then
    if macos_ditto_supports_clone; then
      # --clone shares the source resource fork and ignores --norsrc. Clear
      # xattrs afterwards; that is metadata-only and keeps the data clone.
      ditto --norsrc --clone "$src" "$dest"
      xattr -cr "$dest" 2>/dev/null || true
      return
    fi
    ditto --norsrc "$src" "$dest"
    return
  fi
  if [ "$(uname -s)" = "Darwin" ]; then
    # cp rejects -c together with -X, so clone first and drop xattrs after.
    if cp -c -R "$src" "$dest" 2>/dev/null; then
      xattr -cr "$dest" 2>/dev/null || true
      return
    fi
    cp -R -X "$src" "$dest"
    return
  fi
  cp -R "$src" "$dest"
}
