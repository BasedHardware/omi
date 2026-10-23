#!/usr/bin/env bash
# Pin the complete apt universe, not just ffmpeg's top-level version. Bump the
# snapshot deliberately for security updates; the script hash invalidates cache.
set -euo pipefail
snapshot=20261022T000000Z

if [[ ${1:-} == fetch ]]; then
  # Called under a single wall-clock timeout, including index and archive fetch.
  cache=$2
  sources=$3
  lists=$4
  options=(-o "Dir::Etc::sourcelist=$sources" -o Dir::Etc::sourceparts=-
    -o "Dir::State::lists=$lists" -o "Dir::Cache::archives=$cache"
    -o Acquire::Retries=0 -o Acquire::http::Timeout=15
    -o Acquire::https::Timeout=15 -o Acquire::Check-Valid-Until=false
    -o APT::Update::Error-Mode=any)
  apt-get "${options[@]}" update -qq
  apt-get "${options[@]}" install --download-only --reinstall -y --no-install-recommends ffmpeg libopus0
  exit
fi

cache=${1:?usage: native-audio-replay-deps.sh CACHE_DIRECTORY}
mkdir -p "$cache"
shopt -s nullglob
packages=("$cache"/*.deb)
if [[ -f $cache/SHA256SUMS ]]; then
  # Corruption is a hard failure, not permission to silently fetch new packages.
  (cd "$cache" && sha256sum --check SHA256SUMS)
else
  if ((${#packages[@]})); then
    echo '::error::Native audio cache has packages but no checksum manifest' >&2
    exit 1
  fi
  work=$(mktemp -d)
  trap 'sudo rm -rf "$work"' EXIT
  chmod 755 "$work"
  mkdir -p "$work/lists/partial" "$cache/partial"
  cat > "$work/sources.list" <<EOF
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/$snapshot noble main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/$snapshot noble-updates main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/$snapshot noble-security main universe
EOF
  for attempt in 1 2 3; do
    echo "Native audio snapshot fetch: attempt $attempt/3"
    if sudo timeout --signal=TERM --kill-after=5s 70s bash "$0" fetch "$cache" "$work/sources.list" "$work/lists"; then
      break
    fi
    if ((attempt == 3)); then
      echo '::error::Native audio snapshot fetch failed after 3 attempts' >&2
      exit 1
    fi
    delay=$((5 * attempt))
    echo "::warning::Native audio fetch failed; retrying in ${delay}s" >&2
    sleep "$delay"
  done
  packages=("$cache"/*.deb)
  if ((${#packages[@]} == 0)); then
    echo '::error::Native audio download produced no packages' >&2
    exit 1
  fi
  # apt authenticates the snapshot indexes and package hashes on download.
  # Persist hashes so restored artifacts are checked before the offline install.
  (cd "$cache" && sha256sum ./*.deb > SHA256SUMS)
fi

# No apt repair or live mirror fallback: a bad closure must fail visibly.
((${#packages[@]} > 0))
sudo dpkg -i "${packages[@]}"
ffmpeg -version
python3 -c 'import ctypes; ctypes.CDLL("libopus.so.0")'
