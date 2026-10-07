#!/bin/bash
# Capture one macOS screenshot into the shared UI evidence silo.
#
#   bash desktop/macos/scripts/capture-ui-evidence.sh \
#     --out .agent-artifacts/ui-evidence/<pr-or-branch-slug> \
#     --slug <screen-slug> \
#     [--ordinal N] [--describe <text>] [--window-title <substring>]
#
# Filename: <NNN>-desktop-macos-<slug>.png
# Manifest: <out>/evidence.json (JSON, 2-space indent, trailing newline).
# Source this file to test validate_filename / update_evidence_json without capturing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"

usage() {
  cat <<'EOF'
Usage: capture-ui-evidence.sh --out <repo-relative .agent-artifacts/ui-evidence/<dir>> --slug <screen-slug> [--ordinal N] [--describe <text>] [--window-title <substring>]

Write a desktop-macos screenshot and update evidence.json in that directory.

  --out DIR            Repo-relative .agent-artifacts/ui-evidence/<lowercase-kebab-or-pr>
  --slug SLUG          Lowercase kebab-case screen slug, 1-40 characters
  --ordinal N          Integer 1-999 (default: one past the highest existing ordinal)
  --describe TEXT      evidence.json description (default: the slug)
  --window-title TEXT  Capture the on-screen window whose title (or owner, if the
                       title is blank) contains TEXT. Default: full screen.
  -h, --help           Show this help

Filenames are <NNN>-desktop-macos-<slug>.png. NNN is zero-padded from 001.
evidence.json records captured_by=agent and source=screencapture.
EOF
}

print_screen_recording_remediation() {
  cat >&2 <<'EOF'
Screen Recording permission is required.
Open System Settings → Privacy & Security → Screen Recording,
enable the terminal or app running this script, then retry.
EOF
}

format_ordinal() {
  local raw="$1"
  local value
  if [[ ! "$raw" =~ ^[0-9]+$ ]]; then
    echo "capture-ui-evidence: ordinal must be an integer from 1 to 999" >&2
    return 1
  fi
  value=$((10#$raw))
  if (( value < 1 || value > 999 )); then
    echo "capture-ui-evidence: ordinal must be an integer from 1 to 999" >&2
    return 1
  fi
  printf '%03d\n' "$value"
}

validate_slug() {
  local slug="$1"
  if (( ${#slug} < 1 || ${#slug} > 40 )); then
    echo "capture-ui-evidence: slug must be 1-40 lowercase-kebab characters" >&2
    return 1
  fi
  if [[ ! "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "capture-ui-evidence: slug must be lowercase-kebab (a-z, 0-9, single hyphens): $slug" >&2
    return 1
  fi
}

validate_filename() {
  local name="$1"
  local stem ordinal rest slug
  if [[ "$name" == */* || "$name" != *.png ]]; then
    echo "capture-ui-evidence: filename must be NNN-desktop-macos-<slug>.png: $name" >&2
    return 1
  fi
  stem="${name%.png}"
  ordinal="${stem%%-*}"
  rest="${stem#*-}"
  if [[ ! "$ordinal" =~ ^[0-9]{3}$ || "$ordinal" == "000" ]]; then
    echo "capture-ui-evidence: ordinal must be a zero-padded value from 001: $name" >&2
    return 1
  fi
  if [[ ! "$rest" =~ ^desktop-macos-.+ ]]; then
    echo "capture-ui-evidence: platform token must be desktop-macos: $name" >&2
    return 1
  fi
  slug="${rest#desktop-macos-}"
  validate_slug "$slug"
}

evidence_filename() {
  local ordinal_raw="$1"
  local slug="$2"
  local nnn name
  validate_slug "$slug"
  nnn="$(format_ordinal "$ordinal_raw")"
  name="${nnn}-desktop-macos-${slug}.png"
  validate_filename "$name"
  printf '%s\n' "$name"
}

resolve_out_dir() {
  local out="${1%/}"
  local rel
  if [[ "$out" == /* ]]; then
    case "$out" in
      "$REPO_ROOT"/*) rel="${out#"$REPO_ROOT"/}" ;;
      *)
        echo "capture-ui-evidence: --out must be inside the repository" >&2
        return 1
        ;;
    esac
  else
    rel="$out"
  fi
  rel="$(python3 -c 'import os, sys; print(os.path.normpath(sys.argv[1]))' "$rel")"
  if [[ ! "$rel" =~ ^\.agent-artifacts/ui-evidence/[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "capture-ui-evidence: --out must be repo-relative .agent-artifacts/ui-evidence/<lowercase-kebab-or-pr-number>" >&2
    return 1
  fi
  printf '%s\n' "$REPO_ROOT/$rel"
}

next_ordinal() {
  local dir="$1"
  local max=0
  local path name value
  if [[ -d "$dir" ]]; then
    for path in "$dir"/*.png; do
      [[ -e "$path" ]] || continue
      name="$(basename "$path")"
      if validate_filename "$name" >/dev/null 2>&1; then
        value=$((10#${name%%-*}))
        if (( value > max )); then
          max=$value
        fi
      fi
    done
  fi
  if (( max >= 999 )); then
    echo "capture-ui-evidence: no ordinals left (001-999)" >&2
    return 1
  fi
  format_ordinal $((max + 1))
}

update_evidence_json() {
  local evidence_path="$1"
  local filename="$2"
  local description="$3"
  python3 - "$evidence_path" "$filename" "$description" <<'PY'
import json
import os
import sys
from pathlib import Path

path, filename, description = sys.argv[1:]
description = description.strip()
if not description:
    print("capture-ui-evidence: description must not be empty", file=sys.stderr)
    raise SystemExit(1)
if not filename.endswith(".png") or "/" in filename:
    print(f"capture-ui-evidence: refusing evidence entry for {filename}", file=sys.stderr)
    raise SystemExit(1)

entry = {
    "file": filename,
    "platform": "desktop-macos",
    "description": description,
    "captured_by": "agent",
    "source": "screencapture",
}

evidence = Path(path)
if evidence.exists():
    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"capture-ui-evidence: cannot read {evidence}: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    if not isinstance(data, dict):
        print("capture-ui-evidence: evidence.json must be a JSON object", file=sys.stderr)
        raise SystemExit(1)
else:
    data = {}

images = data.get("images", [])
if not isinstance(images, list):
    print("capture-ui-evidence: evidence.json images must be an array", file=sys.stderr)
    raise SystemExit(1)

replaced = False
merged = []
for item in images:
    if isinstance(item, dict) and item.get("file") == filename:
        if not replaced:
            merged.append(entry)
            replaced = True
        continue
    merged.append(item)
if not replaced:
    merged.append(entry)

extras = {key: value for key, value in data.items() if key not in ("version", "images")}
payload = {"version": 1, "images": merged}
payload.update(extras)
text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
evidence.parent.mkdir(parents=True, exist_ok=True)
temporary = evidence.with_name(f".{evidence.name}.{os.getpid()}.tmp")
temporary.write_text(text, encoding="utf-8")
os.replace(temporary, evidence)
PY
}

commit_ui_evidence() {
  local dest_dir="$1"
  local ordinal="$2"
  local slug="$3"
  local description="$4"
  local src_png="$5"
  local filename dest
  if [[ -z "${description//[[:space:]]/}" ]]; then
    description="$slug"
  fi
  filename="$(evidence_filename "$ordinal" "$slug")"
  if [[ ! -f "$src_png" || ! -s "$src_png" ]]; then
    echo "capture-ui-evidence: png is missing or empty: $src_png" >&2
    return 1
  fi
  mkdir -p "$dest_dir"
  dest="$dest_dir/$filename"
  cp -f "$src_png" "$dest"
  update_evidence_json "$dest_dir/evidence.json" "$filename" "$description"
}

find_window_id() {
  local title="$1"
  local id
  if [[ -z "$title" ]]; then
    echo "capture-ui-evidence: window title substring is empty" >&2
    return 1
  fi
  # Quartz is optional. Without it, stdlib ctypes calls the same CGWindowList
  # API. JXA cannot unwrap CGWindowListCopyWindowInfo refs on current macOS.
  if ! id="$(python3 - "$title" <<'PY'
import ctypes
import sys
from ctypes import (
    CDLL,
    byref,
    c_bool,
    c_char_p,
    c_int,
    c_long,
    c_longlong,
    c_uint32,
    c_ulong,
    c_void_p,
    create_string_buffer,
)

needle = sys.argv[1].casefold()
if not needle.strip():
    print("capture-ui-evidence: window title substring is empty", file=sys.stderr)
    raise SystemExit(1)

ONSCREEN = 1
EXCLUDE_DESKTOP = 16
UTF8 = 0x08000100


def windows_from_quartz():
    import Quartz

    raw = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    windows = []
    for item in raw or []:
        number = item.get("kCGWindowNumber")
        windows.append(
            {
                "name": item.get("kCGWindowName") or "",
                "owner": item.get("kCGWindowOwnerName") or "",
                "layer": int(item.get("kCGWindowLayer") or 0),
                "wid": int(number) if number is not None else None,
            }
        )
    return windows


def windows_from_coregraphics():
    cg = CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg.CGWindowListCopyWindowInfo.argtypes = [c_uint32, c_uint32]
    cg.CGWindowListCopyWindowInfo.restype = c_void_p
    cf.CFArrayGetCount.argtypes = [c_void_p]
    cf.CFArrayGetCount.restype = c_long
    cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
    cf.CFArrayGetValueAtIndex.restype = c_void_p
    cf.CFDictionaryGetValue.argtypes = [c_void_p, c_void_p]
    cf.CFDictionaryGetValue.restype = c_void_p
    cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
    cf.CFStringCreateWithCString.restype = c_void_p
    cf.CFStringGetLength.argtypes = [c_void_p]
    cf.CFStringGetLength.restype = c_long
    cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
    cf.CFStringGetCString.restype = c_bool
    cf.CFNumberGetValue.argtypes = [c_void_p, c_int, c_void_p]
    cf.CFNumberGetValue.restype = c_bool
    cf.CFGetTypeID.argtypes = [c_void_p]
    cf.CFGetTypeID.restype = c_ulong
    cf.CFStringGetTypeID.restype = c_ulong
    cf.CFNumberGetTypeID.restype = c_ulong
    cf.CFRelease.argtypes = [c_void_p]
    cf.CFRelease.restype = None

    def cfstr(text):
        return cf.CFStringCreateWithCString(None, text.encode(), UTF8)

    def as_text(ref):
        if not ref or cf.CFGetTypeID(ref) != cf.CFStringGetTypeID():
            return ""
        length = cf.CFStringGetLength(ref)
        buf = create_string_buffer(max(length * 4 + 1, 1))
        if not cf.CFStringGetCString(ref, buf, len(buf), UTF8):
            return ""
        return buf.value.decode()

    def as_int(ref):
        if not ref or cf.CFGetTypeID(ref) != cf.CFNumberGetTypeID():
            return None
        out = c_longlong()
        if not cf.CFNumberGetValue(ref, 4, byref(out)):
            return None
        return int(out.value)

    listed = cg.CGWindowListCopyWindowInfo(ONSCREEN | EXCLUDE_DESKTOP, 0)
    if not listed:
        return []
    try:
        keys = {
            "name": cfstr("kCGWindowName"),
            "owner": cfstr("kCGWindowOwnerName"),
            "number": cfstr("kCGWindowNumber"),
            "layer": cfstr("kCGWindowLayer"),
        }
        windows = []
        for index in range(cf.CFArrayGetCount(listed)):
            item = cf.CFArrayGetValueAtIndex(listed, index)
            windows.append(
                {
                    "name": as_text(cf.CFDictionaryGetValue(item, keys["name"])),
                    "owner": as_text(cf.CFDictionaryGetValue(item, keys["owner"])),
                    "layer": as_int(cf.CFDictionaryGetValue(item, keys["layer"])) or 0,
                    "wid": as_int(cf.CFDictionaryGetValue(item, keys["number"])),
                }
            )
        return windows
    finally:
        cf.CFRelease(listed)


def choose(windows):
    title_hits = []
    owner_hits = []
    for window in windows:
        wid = window["wid"]
        if wid is None:
            continue
        rank = 0 if window["layer"] == 0 else 1
        name = str(window["name"] or "").casefold()
        owner = str(window["owner"] or "").casefold()
        if name and needle in name:
            title_hits.append((rank, wid))
        elif owner and needle in owner:
            owner_hits.append((rank, wid))
    for group in (title_hits, owner_hits):
        if group:
            group.sort(key=lambda item: item[0])
            return group[0][1]
    return None


try:
    import Quartz  # noqa: F401
except ImportError:
    Quartz = None

windows = windows_from_quartz() if Quartz is not None else windows_from_coregraphics()
chosen = choose(windows)
if chosen is None:
    raise SystemExit(1)
print(chosen)
PY
  )"; then
    return 1
  fi
  id="${id//$'\r'/}"
  id="${id//$'\n'/}"
  if [[ ! "$id" =~ ^[0-9]+$ ]]; then
    echo "capture-ui-evidence: window lookup returned no numeric id" >&2
    return 1
  fi
  printf '%s\n' "$id"
}

run_screencapture() {
  local dest="$1"
  shift
  local bin="${CAPTURE_UI_EVIDENCE_SCREENCAPTURE:-screencapture}"
  if [[ "$bin" == */* ]]; then
    if [[ ! -x "$bin" ]]; then
      echo "capture-ui-evidence: capture command is not executable: $bin" >&2
      return 1
    fi
  elif ! command -v "$bin" >/dev/null 2>&1; then
    echo "capture-ui-evidence: capture command not found: $bin" >&2
    return 1
  fi
  if ! "$bin" "$@" "$dest"; then
    rm -f -- "$dest"
    echo "capture-ui-evidence: screencapture failed." >&2
    print_screen_recording_remediation
    return 1
  fi
  if [[ ! -s "$dest" ]]; then
    rm -f -- "$dest"
    echo "capture-ui-evidence: screencapture wrote an empty file." >&2
    print_screen_recording_remediation
    return 1
  fi
}

main() {
  local out="" slug="" ordinal="" describe="" window_title=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --out)
        [[ $# -ge 2 && -n "${2:-}" ]] || { echo "capture-ui-evidence: --out requires a directory" >&2; usage >&2; return 2; }
        out="$2"
        shift 2
        ;;
      --slug)
        [[ $# -ge 2 && -n "${2:-}" ]] || { echo "capture-ui-evidence: --slug requires a value" >&2; usage >&2; return 2; }
        slug="$2"
        shift 2
        ;;
      --ordinal)
        [[ $# -ge 2 && -n "${2:-}" ]] || { echo "capture-ui-evidence: --ordinal requires an integer" >&2; usage >&2; return 2; }
        ordinal="$2"
        shift 2
        ;;
      --describe)
        [[ $# -ge 2 && -n "${2:-}" ]] || { echo "capture-ui-evidence: --describe requires text" >&2; usage >&2; return 2; }
        describe="$2"
        shift 2
        ;;
      --window-title)
        [[ $# -ge 2 && -n "${2:-}" ]] || { echo "capture-ui-evidence: --window-title requires a substring" >&2; usage >&2; return 2; }
        window_title="$2"
        shift 2
        ;;
      -h|--help)
        usage
        return 0
        ;;
      *)
        echo "capture-ui-evidence: unknown argument: $1" >&2
        usage >&2
        return 2
        ;;
    esac
  done
  if [[ -z "$out" || -z "$slug" ]]; then
    usage >&2
    return 2
  fi
  if [[ -z "${describe//[[:space:]]/}" ]]; then
    describe="$slug"
  fi

  local dest_dir nnn tmp wid
  dest_dir="$(resolve_out_dir "$out")"
  mkdir -p "$dest_dir"
  if [[ -n "$ordinal" ]]; then
    nnn="$(format_ordinal "$ordinal")"
  else
    nnn="$(next_ordinal "$dest_dir")"
  fi
  tmp="$(mktemp "${dest_dir}/.capture.XXXXXX")"
  rm -f -- "$tmp"
  tmp="${tmp}.png"
  if [[ -n "$window_title" ]]; then
    if ! wid="$(find_window_id "$window_title")"; then
      echo "capture-ui-evidence: no on-screen window title or owner contains: $window_title" >&2
      echo "Window titles stay blank until Screen Recording is granted." >&2
      print_screen_recording_remediation
      rm -f -- "$tmp"
      return 1
    fi
    run_screencapture "$tmp" -x -l "$wid"
  else
    run_screencapture "$tmp" -x
  fi
  commit_ui_evidence "$dest_dir" "$nnn" "$slug" "$describe" "$tmp"
  rm -f -- "$tmp"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
