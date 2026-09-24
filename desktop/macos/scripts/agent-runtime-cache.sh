#!/bin/bash
# Shared, side-effect-free primitives for prepare-agent-runtime.sh's local cache.
# This file is sourced by production code and its hermetic shell tests.

arc_sha256_stream() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  else
    sha256sum | awk '{print $1}'
  fi
}

arc_sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

arc_file_matches_sha256() {
  local file="$1"
  local expected="$2"
  [ -f "$file" ] || return 1
  [ "$(arc_sha256_file "$file")" = "$expected" ]
}

arc_restore_verified_cache_file() {
  local cache_file="$1"
  local expected="$2"
  local destination="$3"
  arc_file_matches_sha256 "$cache_file" "$expected" || return 1
  cp -f "$cache_file" "$destination"
  arc_file_matches_sha256 "$destination" "$expected"
}

# Hash names, kinds, permission modes, symlink destinations, and file contents
# deterministically. Input callers exclude working node_modules; output callers
# intentionally include the complete prepared trees copied into the app bundle.
arc_hash_paths() {
  python3 - "$@" <<'PY' | arc_sha256_stream
import hashlib
import os
import sys

for raw in sys.argv[1:]:
    path = os.path.abspath(raw)
    if not os.path.lexists(path):
        print(f"missing\0{path}\0")
        continue
    roots = [path]
    if os.path.isdir(path) and not os.path.islink(path):
        roots = []
        for current, dirs, files in os.walk(path):
            dirs.sort()
            files.sort()
            roots.append(current)
            roots.extend(os.path.join(current, name) for name in files)
            roots.extend(os.path.join(current, name) for name in dirs if os.path.islink(os.path.join(current, name)))
    for entry in roots:
        relative = entry
        mode = os.lstat(entry).st_mode & 0o7777
        if os.path.islink(entry):
            print(f"link\0{relative}\0{mode:o}\0{os.readlink(entry)}\0")
        elif os.path.isfile(entry):
            digest = hashlib.sha256()
            with open(entry, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            print(f"file\0{relative}\0{mode:o}\0{digest.hexdigest()}\0")
        elif os.path.isdir(entry):
            print(f"dir\0{relative}\0{mode:o}\0")
PY
}

arc_stamp_field() {
  local stamp="$1"
  local field="$2"
  [ -f "$stamp" ] || return 1
  sed -n "s/^${field}=//p" "$stamp" | head -1
}

arc_cache_status() {
  local stamp="$1"
  local expected_key="$2"
  local expected_output_digest="$3"
  local stamped_key stamped_output_digest
  stamped_key="$(arc_stamp_field "$stamp" key || true)"
  stamped_output_digest="$(arc_stamp_field "$stamp" output_digest || true)"
  [ "$stamped_key" = "$expected_key" ] || return 1
  [ "$stamped_output_digest" = "$expected_output_digest" ] || return 1
}

arc_cache_policy() {
  local ci_value="${1:-}"
  local skip_npm="${2:-0}"
  local force_rebuild="${3:-0}"
  if [ "$ci_value" = "true" ] || [ "$ci_value" = "1" ]; then
    printf '%s\n' "bypass:CI clean preparation"
  elif [ "$skip_npm" = "1" ]; then
    printf '%s\n' "bypass:--skip-npm"
  elif [ "$force_rebuild" = "1" ]; then
    printf '%s\n' "bypass:OMI_AGENT_RUNTIME_FORCE_REBUILD=1"
  else
    printf '%s\n' "eligible"
  fi
}

# How prepare-agent-runtime.sh may use the shared Node binary cache.
#   reuse   — stage a validated cached binary, or publish one on miss
#   refresh — ignore the cached binary, rebuild, then publish
#   direct  — CI: write the worktree binary only; do not read or write the cache
arc_node_runtime_cache_policy() {
  local ci_value="${1:-}"
  local force_rebuild="${2:-0}"
  if [ "$ci_value" = "true" ] || [ "$ci_value" = "1" ]; then
    printf '%s\n' "direct"
  elif [ "$force_rebuild" = "1" ]; then
    printf '%s\n' "refresh"
  else
    printf '%s\n' "reuse"
  fi
}

arc_node_runtime_cache_name() {
  local version="$1"
  local mode="$2"
  local material="$3"
  local sha
  sha="$(printf '%s' "$material" | arc_sha256_stream)"
  printf '%s-%s-%s\n' "$version" "$mode" "$sha"
}

arc_node_runtime_cache_file() {
  local cache_dir="$1"
  local version="$2"
  local mode="$3"
  local material="$4"
  local name
  name="$(arc_node_runtime_cache_name "$version" "$mode" "$material")"
  printf '%s/%s/node\n' "$cache_dir" "$name"
}

# Prefer an APFS clone. cp -c falls back to a full copy on this macOS when the
# destination is a different volume; if it fails outright, copy explicitly.
arc_clone_or_copy_file() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    rm -f "$dest"
  fi
  if cp -c "$src" "$dest" 2>/dev/null; then
    return 0
  fi
  rm -f "$dest"
  cp -f "$src" "$dest"
}

# Exit 0 when both paths are regular files sharing an APFS clone id.
arc_same_clone() {
  local left="$1"
  local right="$2"
  python3 - "$left" "$right" <<'PY'
import ctypes
import ctypes.util
import struct
import sys

if sys.platform != "darwin":
    raise SystemExit(1)

libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


class AttrList(ctypes.Structure):
    _fields_ = [
        ("bitmapcount", ctypes.c_ushort),
        ("reserved", ctypes.c_uint16),
        ("commonattr", ctypes.c_uint32),
        ("volattr", ctypes.c_uint32),
        ("dirattr", ctypes.c_uint32),
        ("fileattr", ctypes.c_uint32),
        ("forkattr", ctypes.c_uint32),
    ]


ATTR_BIT_MAP_COUNT = 5
ATTR_CMNEXT_CLONEID = 0x00000100
FSOPT_ATTR_CMN_EXTENDED = 0x00000020


def clone_id(path):
    attrs = AttrList()
    attrs.bitmapcount = ATTR_BIT_MAP_COUNT
    attrs.forkattr = ATTR_CMNEXT_CLONEID
    buf = ctypes.create_string_buffer(64)
    rc = libc.getattrlist(
        path.encode(),
        ctypes.byref(attrs),
        buf,
        ctypes.sizeof(buf),
        FSOPT_ATTR_CMN_EXTENDED,
    )
    if rc != 0:
        raise SystemExit(1)
    raw = bytes(buf)
    length = struct.unpack_from("<I", raw, 0)[0]
    if length < 12:
        raise SystemExit(1)
    return struct.unpack_from("<Q", raw, 4)[0]


left_id = clone_id(sys.argv[1])
right_id = clone_id(sys.argv[2])
raise SystemExit(0 if left_id == right_id else 1)
PY
}

arc_remove_broken_symlinks() {
  local directory="$1"
  python3 - "$directory" <<'PY'
import os
import sys

directory = sys.argv[1]
if not os.path.isdir(directory):
    raise SystemExit(0)

for name in os.listdir(directory):
    path = os.path.join(directory, name)
    if os.path.islink(path) and not os.path.exists(path):
        os.unlink(path)
PY
}

arc_write_stamp() {
  local stamp="$1"
  local key="$2"
  local output_digest="$3"
  local temp
  mkdir -p "$(dirname "$stamp")"
  temp="$(mktemp "${stamp}.tmp.XXXXXX")"
  printf 'version=1\nkey=%s\noutput_digest=%s\n' "$key" "$output_digest" >"$temp"
  mv -f "$temp" "$stamp"
}

arc_acquire_lock() {
  local lock_dir="$1"
  local timeout_seconds="${2:-600}"
  local started now owner
  mkdir -p "$(dirname "$lock_dir")"
  started="$(date +%s)"
  while ! mkdir "$lock_dir" 2>/dev/null; do
    owner="$(cat "$lock_dir/pid" 2>/dev/null || true)"
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      rm -rf "$lock_dir"
      continue
    fi
    now="$(date +%s)"
    if [ $((now - started)) -ge "$timeout_seconds" ]; then
      echo "ERROR: timed out waiting for agent runtime preparation lock: $lock_dir" >&2
      return 1
    fi
    sleep 0.1
  done
  printf '%s\n' "$$" >"$lock_dir/pid"
}

arc_release_lock() {
  local lock_dir="$1"
  [ -d "$lock_dir" ] || return 0
  local owner
  owner="$(cat "$lock_dir/pid" 2>/dev/null || true)"
  if [ -z "$owner" ] || [ "$owner" = "$$" ]; then
    rm -rf "$lock_dir"
  fi
}
