#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
USER_PROFILE="${1:-}"
if [ -z "$USER_PROFILE" ]; then
  echo "Usage: make desktop-run-local USER=<profile> (for example USER=alice)" >&2
  exit 2
fi

PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY' "$USER_PROFILE"
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from dev_harness import config, safety
from dev_harness.cli import _current_scenario_manifest, _scenario_users_from_seed_manifest

user = sys.argv[1]
repo = Path.cwd()
cfg = config.load_config(repo, create_layout=False)
print("Omi desktop local V17 manual-QA launcher")
print(f"instance: {cfg.instance}")
print(f"provider_mode: {cfg.provider_mode}")
print(f"state_root: {cfg.layout.state_root}")
print(f"backend: {cfg.backend_url}")
print(f"firebase_auth_emulator: {cfg.auth_host}")

if not cfg.layout.sentinel_path.is_file():
    print("Cannot launch desktop placeholder: harness sentinel is missing.")
    print("Next step: PROVIDER_MODE=offline make dev-up  # or configure real-provider dev credentials and run make dev-up")
    raise SystemExit(1)

safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=repo, instance=cfg.instance)
scenario = _current_scenario_manifest(cfg)
if not scenario:
    print("Cannot launch desktop placeholder: no V17 scenario has been seeded.")
    print("Next step: make seed-v17-scenario SCENARIO=happy_path")
    raise SystemExit(1)

users = _scenario_users_from_seed_manifest(cfg)
if user not in users:
    print(f"Cannot launch desktop placeholder: USER={user!r} is not in seeded users: {', '.join(users) if users else 'none'}")
    print("Next step: choose one of the seeded synthetic users, e.g. make desktop-run-local USER=alice")
    raise SystemExit(1)

run_sh = repo / "desktop" / "macos" / "run.sh"
if not run_sh.is_file():
    print(f"Cannot launch desktop placeholder: missing {run_sh}")
    raise SystemExit(1)

app_name = f"omi-local-v17-{user}"
print(f"scenario_id: {scenario.get('scenario_id')}")
print(f"selected_user: {scenario.get('selected_user')}")
print(f"local_desktop_profile: {app_name}")
print("TICKET-050 desktop local profile/auth bootstrap is not implemented in this slice, so this wrapper does not embed provider credentials or start the app automatically.")
print("Exact next step after TICKET-050 lands:")
print(
    "  cd desktop/macos && "
    f"OMI_APP_NAME={app_name!r} OMI_SKIP_BACKEND=1 OMI_SKIP_TUNNEL=1 "
    f"OMI_DESKTOP_API_URL={cfg.backend_url!r} OMI_PYTHON_API_URL={cfg.backend_url!r} "
    f"FIREBASE_AUTH_EMULATOR_HOST={cfg.auth_host!r} FIREBASE_PROJECT_ID={cfg.project_id!r} "
    f"OMI_LOCAL_AUTH_USER={user!r} ./run.sh"
)

if platform.system() != "Darwin":
    print("Current platform is not macOS; desktop launch is intentionally a safe handoff only here.")
raise SystemExit(0)
PY
