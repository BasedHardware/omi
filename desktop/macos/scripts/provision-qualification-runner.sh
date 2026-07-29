#!/usr/bin/env bash
# Provision (or reconfigure) a macOS GitHub Actions runner for desktop beta
# qualification. Idempotent when the runner is already configured.
#
# Usage:
#   ./provision-qualification-runner.sh \
#     --name m1-mac-studio-qualification \
#     --labels omi-desktop-qualification,omi-qual-m1-studio
#
# Requires: gh (authenticated with admin:org / repo runner rights), curl, and a
# downloaded actions/runner tree at --runner-home (default
# ~/.local/share/omi-actions-runner).
set -euo pipefail

REPO="${OMI_QUAL_GITHUB_REPO:-BasedHardware/omi}"
RUNNER_HOME="${OMI_QUAL_RUNNER_HOME:-$HOME/.local/share/omi-actions-runner}"
RUNNER_NAME=""
LABELS=""
WORK_DIR="_work"

usage() {
  cat <<'USAGE'
Provision a self-hosted macOS qualification runner.

Required:
  --name NAME       Runner name registered with GitHub
  --labels CSV      Extra labels (comma-separated). Always include
                    omi-desktop-qualification. The official M1 qualifier also
                    needs omi-qual-m1-studio (see desktop_qualify_beta.yml).

Optional:
  --runner-home DIR  Unpacked actions/runner directory
                     (default: ~/.local/share/omi-actions-runner)
  --repo SLUG        GitHub repo (default: BasedHardware/omi)
  --work DIR         Runner work folder (default: _work)
  --help             Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      RUNNER_NAME="${2:?}"
      shift 2
      ;;
    --labels)
      LABELS="${2:?}"
      shift 2
      ;;
    --runner-home)
      RUNNER_HOME="${2:?}"
      shift 2
      ;;
    --repo)
      REPO="${2:?}"
      shift 2
      ;;
    --work)
      WORK_DIR="${2:?}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$RUNNER_NAME" ]] || { echo "--name is required" >&2; exit 2; }
[[ -n "$LABELS" ]] || { echo "--labels is required" >&2; exit 2; }

command -v gh >/dev/null || { echo "gh CLI is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
docker info >/dev/null || { echo "docker daemon must be running" >&2; exit 1; }

if [[ ! -x "$RUNNER_HOME/config.sh" ]]; then
  echo "missing $RUNNER_HOME/config.sh — download actions/runner into that directory first" >&2
  exit 1
fi

if [[ -f "$RUNNER_HOME/.runner" ]]; then
  echo "runner already configured at $RUNNER_HOME (.runner present); leaving config unchanged"
  exit 0
fi

api_token=$(gh auth token)
registration_token=$(curl -fsS --retry 3 --retry-all-errors --connect-timeout 10 --max-time 60 \
  -X POST \
  -H "Authorization: Bearer $api_token" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO}/actions/runners/registration-token" \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])')

"$RUNNER_HOME/config.sh" --unattended \
  --url "https://github.com/${REPO}" \
  --token "$registration_token" \
  --name "$RUNNER_NAME" \
  --labels "$LABELS" \
  --work "$WORK_DIR"

echo "configured runner name=$RUNNER_NAME labels=$LABELS home=$RUNNER_HOME"
echo "next: install a KeepAlive launch agent that execs $RUNNER_HOME/run.sh"
