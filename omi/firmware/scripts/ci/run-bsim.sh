#!/usr/bin/env bash
set -euo pipefail

FW=${FW:-/omi/firmware}
NCS_VERSION=v2.9.0
WORKSPACE="$FW/$NCS_VERSION"
BSIM_OUT_PATH="$WORKSPACE/tools/bsim"
BSIM_COMPONENTS_PATH="$BSIM_OUT_PATH/components"
export BSIM_OUT_PATH BSIM_COMPONENTS_PATH

git config --global --add safe.directory '*'
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

if [ ! -d .west ]; then
  west init -m https://github.com/nrfconnect/sdk-nrf --mr "$NCS_VERSION" .
fi

west config manifest.group-filter -- +babblesim
west update -o=--depth=1 -n
west zephyr-export
make -C "$BSIM_OUT_PATH" everything -j"$(nproc)"

west build -b nrf5340bsim/nrf5340/cpuapp "$FW/bsim" --sysbuild -d build-bsim-omi --pristine always
west build -b nrf52_bsim "$FW/bsim/client" -d build-bsim-client --pristine always

OMI_EXE="$WORKSPACE/build-bsim-omi/zephyr/zephyr.exe"
if [ ! -x "$OMI_EXE" ]; then
  OMI_EXE="$WORKSPACE/build-bsim-omi/bsim/zephyr/zephyr.exe"
fi
CLIENT_EXE="$WORKSPACE/build-bsim-client/zephyr/zephyr.exe"
PHY_EXE="$BSIM_OUT_PATH/bin/bs_2G4_phy_v1"
test -x "$OMI_EXE"
test -x "$CLIENT_EXE"
test -x "$PHY_EXE"

RUN_DIR=$(mktemp -d)
SIMULATION="omi_$$"
PIDS=()
cleanup() {
  if [ "${#PIDS[@]}" -gt 0 ]; then
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
  fi
  rm -rf "$RUN_DIR"
}
trap cleanup EXIT

"$OMI_EXE" -s="$SIMULATION" -d=0 >"$RUN_DIR/omi.log" 2>&1 &
PIDS+=("$!")
"$CLIENT_EXE" -s="$SIMULATION" -d=1 >"$RUN_DIR/client.log" 2>&1 &
PIDS+=("$!")
"$PHY_EXE" -s="$SIMULATION" -D=2 -sim_length=30e6 >"$RUN_DIR/phy.log" 2>&1 &
PIDS+=("$!")

RESULT=1
for _ in $(seq 1 120); do
  if grep -q OMI_BSIM_PASS "$RUN_DIR/client.log"; then
    RESULT=0
    break
  fi
  if grep -q OMI_BSIM_FAIL "$RUN_DIR/omi.log" "$RUN_DIR/client.log"; then
    break
  fi
  sleep 1
done

cat "$RUN_DIR/omi.log"
cat "$RUN_DIR/client.log"
if [ "$RESULT" -ne 0 ]; then
  cat "$RUN_DIR/phy.log"
fi
cleanup
trap - EXIT
exit "$RESULT"
