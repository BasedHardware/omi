#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
# shellcheck source=_resolve_python.sh
source "$(dirname "$0")/_resolve_python.sh"
cd "$(dirname "$0")/../.."
USER_PROFILE="${1:-alice}"

PYTHON_BIN="$(dev_harness_python)"

PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" - <<'PY' "$USER_PROFILE"
from __future__ import annotations

import os
import json
import re
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

desktop_dir = repo / "desktop" / "windows"
if not (desktop_dir / "package.json").is_file():
    print(f"Cannot launch desktop local profile: missing {desktop_dir / 'package.json'}")
    raise SystemExit(1)

profile_env = {
    **os.environ,
    "OMI_APP_NAME": os.environ.get("OMI_APP_NAME") or os.environ.get("DESKTOP_APP_NAME") or "omi-memory",
}
profile = desktop_profile.resolve_profile(cfg, user=user, seeded_users=users, env=profile_env)
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
print("Firebase Auth emulator bootstrap: scenario seed creates local_default_user, alice, and bob; this launch uses the selected seeded email/password through the Tauri renderer.")
print("Static safety scan: PASS (localhost endpoints, demo-omi-local, no provider credential env in resolved profile).")

profile_root = cfg.layout.state_root / "desktop-tauri" / profile.app_name / profile.selected_user
data_root = profile_root / "data"
profile_root.mkdir(parents=True, exist_ok=True)
data_root.mkdir(parents=True, exist_ok=True)
user_suffix = re.sub(r"[^a-z0-9]+", "-", profile.selected_user.lower()).strip("-")
if not user_suffix:
    print(f"Cannot launch desktop local profile: selected user {profile.selected_user!r} cannot form a Tauri identifier.")
    raise SystemExit(2)
local_identifier = f"{profile.bundle_id}.{user_suffix}"
tauri_config = profile_root / "tauri.local.conf.json"
tauri_config.write_text(
    json.dumps({"productName": f"{profile.app_name}-{profile.selected_user}", "identifier": local_identifier}),
    encoding="utf-8",
)
local_env = {
    **profile.env,
    "OMI_DB_PATH": str(profile_root / "omi.db"),
    "OMI_DATA_ROOT": str(data_root),
    "OMI_API_BASE_URL": profile.python_api_url,
    "OMI_AGENT_STATE_DIR": str(data_root / "AgentRuntime" / profile.bundle_id),
    "OMI_AGENT_ARTIFACTS_DIR": str(data_root / "Artifacts" / profile.bundle_id),
    "VITE_OMI_DESKTOP_LOCAL_PROFILE": "1",
    "VITE_OMI_API_BASE": profile.python_api_url,
    "VITE_OMI_DESKTOP_API_BASE": profile.desktop_api_url,
    "VITE_FIREBASE_API_KEY": profile.firebase_api_key,
    "VITE_FIREBASE_AUTH_DOMAIN": f"{profile.firebase_project_id}.firebaseapp.com",
    "VITE_FIREBASE_PROJECT_ID": profile.firebase_project_id,
    "VITE_FIREBASE_AUTH_EMULATOR_HOST": profile.firebase_auth_emulator_host,
    "VITE_OMI_LOCAL_AUTH_EMAIL": profile.selected_user_email,
    "VITE_OMI_LOCAL_AUTH_PASSWORD": profile.selected_user_password,
}
command = ["bun", "run", "tauri", "dev", "--config", str(tauri_config)]
env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(local_env.items()))
print("Launch command:")
print(f"  cd desktop/windows && {env_prefix} bun run tauri dev --config {shlex.quote(str(tauri_config))}")

env = os.environ.copy()
for key in (
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "ELEVENLABS_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
):
    env.pop(key, None)
env.update(local_env)
subprocess.run(command, cwd=desktop_dir, env=env, check=True)
PY
