#!/usr/bin/env bash
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
CI_IMAGE=ghcr.io/zephyrproject-rtos/ci:v0.26.13@sha256:b0ac6334d1926cd0971a0a444f7adc6dd020e88ee3ce865aa070b6475a3ac4eb

docker run --rm \
  -v "$ROOT/omi/firmware:/omi/firmware" \
  -e CMAKE_PREFIX_PATH=/opt/toolchains \
  "$CI_IMAGE" \
  bash /omi/firmware/scripts/ci/run-bsim.sh
