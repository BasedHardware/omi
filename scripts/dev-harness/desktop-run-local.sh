#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
cd "$(dirname "$0")/../.."
USER_PROFILE="${1:-alice}"

PYTHON_BIN="${PYTHON:-backend/venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" - <<'PY' "$USER_PROFILE"
from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

from dev_harness import config, desktop_profile, safety
from dev_harness.cli import _current_scenario_manifest, _scenario_users_from_seed_manifest

user = sys.argv[1]
repo = Path.cwd()
cfg = config.load_config(repo, create_layout=False)
print("Omi Dev local harness desktop launcher")
print(f"instance: {cfg.instance}")
print(f"provider_mode: {cfg.provider_mode}")
print(f"state_root: {cfg.layout.state_root}")
print(f"backend: {cfg.backend_url}")
print(f"firebase_auth_emulator: {cfg.auth_host}")

if not cfg.layout.sentinel_path.is_file():
    print("Cannot launch desktop local profile: harness sentinel is missing.")
    print("Next step: PROVIDER_MODE=offline make dev-up  # or configure real-provider dev credentials and run make dev-up")
    raise SystemExit(1)

safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=repo, instance=cfg.instance)
scenario = _current_scenario_manifest(cfg)
if not scenario:
    print("Cannot launch desktop local profile: no memory scenario has been seeded.")
    print("Next step: make seed-memory-scenario SCENARIO=happy_path")
    raise SystemExit(1)

users = _scenario_users_from_seed_manifest(cfg)
if user not in users:
    print(f"Cannot launch desktop local profile: USER={user!r} is not in seeded users: {', '.join(users) if users else 'none'}")
    print("Next step: choose one of the seeded synthetic users, e.g. make desktop-run-local DESKTOP_USER=alice")
    raise SystemExit(1)

run_sh = repo / "desktop" / "macos" / "run.sh"
if not run_sh.is_file():
    print(f"Cannot launch desktop local profile: missing {run_sh}")
    raise SystemExit(1)

profile = desktop_profile.resolve_profile(cfg, user=user, seeded_users=users, env=os.environ)
errors = desktop_profile.validate_profile(profile)
if errors:
    print("Static local desktop profile safety scan failed:")
    for error in errors:
        print(f"  - {error}")
    raise SystemExit(2)

resolved_path = cfg.layout.reports_dir / "desktop-local-profile-resolved.json"
desktop_profile.write_resolved_profile(profile, resolved_path)
print(f"scenario_id: {scenario.get('scenario_id')}")
print(f"scenario_selected_user: {scenario.get('selected_user')}")
print(f"selected_desktop_user: {profile.selected_user}")
print(f"selected_desktop_email: {profile.selected_user_email}")
print(f"local_desktop_profile: {profile.display_name} ({profile.app_name}.app)")
print(f"bundle_id: {profile.bundle_id}")
print(f"url_scheme: {profile.url_scheme}")
print(f"preferences_domain: {profile.preferences_domain}")
print(f"application_support: {profile.application_support_dir}")
print(f"caches: {profile.caches_dir}")
print(f"firebase_project: {profile.firebase_project_id}")
print(f"auth_emulator: {profile.firebase_auth_emulator_host}")
print(f"resolved_profile: {resolved_path}")
print("Firebase Auth emulator bootstrap: scenario seed creates local_default_user, alice, and bob; this launch selects the requested USER and Swift signs in to the Auth emulator with the seeded synthetic email/password.")
print("Static safety scan: PASS (localhost endpoints, demo-omi-local, no provider credential env in resolved profile).")

command = ["./run.sh"]
env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(profile.env.items()))
print("Launch command:")
print(f"  cd desktop/macos && {env_prefix} ./run.sh")

if platform.system() != "Darwin":
    print(f"Current platform is {platform.system()}, not macOS/Darwin; native Swift desktop build/launch is blocked here and intentionally not faked.")
    raise SystemExit(0)

env = os.environ.copy()
env.update(profile.env)
subprocess.run(command, cwd=repo / "desktop" / "macos", env=env, check=True)
PY
