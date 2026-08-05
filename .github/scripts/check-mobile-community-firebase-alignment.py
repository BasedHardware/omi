#!/usr/bin/env python3
"""Fail closed when community mobile remote-staging auth cannot work (#9404).

Profiles (see issue #9404):

| Profile | API | Firebase identity |
| --- | --- | --- |
| Community remote staging | ``https://api.omiapi.com/`` | ``based-hardware`` |
| Isolated local development | local backend / emulator | emulator or ``based-hardware-dev`` |

The live ``api.omiapi.com`` backend verifies Firebase ID tokens against
``based-hardware`` (data plane). Tokens minted by ``based-hardware-dev`` are
rejected with 401 after an apparently successful sign-in.

This checker:

1. Requires community ``setup.sh`` / ``setup.ps1`` to default to the remote
   staging API and to refuse (or allowlist-escape) a Firebase/API mismatch.
2. Forbids dead FlutterFire generators that would reintroduce
   ``based-hardware-dev`` configs for that default API.
3. Asserts every prebuilt Firebase file agrees on one project id.
4. Allowlists the known prebuilt mismatch only while configs still declare
   ``based-hardware-dev`` — the allowlist may shrink to empty, never grow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST = Path(".github/scripts/mobile_community_firebase_alignment_allowlist.json")

REMOTE_STAGING_API = "https://api.omiapi.com/"
REQUIRED_REMOTE_STAGING_FIREBASE = "based-hardware"
PREBUILT_RELATIVE = (
    "app/setup/prebuilt/firebase_options.dart",
    "app/setup/prebuilt/google-services.json",
    "app/setup/prebuilt/GoogleService-Info.plist",
)
SETUP_SCRIPTS = (
    "app/setup.sh",
    "app/setup/scripts/setup.ps1",
)
ALIGNMENT_MARKERS = (
    "validate_firebase_api_alignment",
    "Validate-FirebaseApiAlignment",
)
FORBIDDEN_FLUTTERFIRE_DEV_PROJECT = re.compile(
    r"flutterfire\s+config[\s\S]{0,400}?--project=[\"']based-hardware-dev[\"']",
    re.IGNORECASE,
)


def repo_root(explicit: str | None = None) -> Path:
    return Path(explicit).resolve() if explicit else REPOSITORY_ROOT


def _project_from_prebuilt(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        match = re.search(r'"project_id"\s*:\s*"([^"]+)"', text)
        return match.group(1) if match else None
    if path.suffix == ".plist":
        match = re.search(
            r"<key>PROJECT_ID</key>\s*<string>([^<]+)</string>",
            text,
        )
        return match.group(1) if match else None
    # firebase_options.dart — require a single projectId across platforms
    ids = re.findall(r"projectId:\s*'([^']+)'", text)
    if not ids:
        return None
    unique = set(ids)
    if len(unique) != 1:
        return f"__inconsistent__:{','.join(sorted(unique))}"
    return next(iter(unique))


def _setup_default_api(setup_text: str) -> str | None:
    # bash: API_BASE_URL=https://...
    match = re.search(r"(?m)^API_BASE_URL=(https?://\S+)\s*$", setup_text)
    if match:
        return match.group(1).strip()
    # powershell: $API_BASE_URL = "https://..."
    match = re.search(r'(?m)\$API_BASE_URL\s*=\s*"(https?://[^"]+)"', setup_text)
    if match:
        return match.group(1).strip()
    return None


def load_allowlist(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = raw.get("allowed_prebuilt_projects_while_api_is_remote_staging")
    if not isinstance(allowed, list) or not all(isinstance(x, str) for x in allowed):
        raise ValueError(
            "allowlist must contain allowed_prebuilt_projects_while_api_is_remote_staging: string[]"
        )
    return list(allowed)


def validate(root: Path, allowlist_path: Path) -> list[str]:
    errors: list[str] = []

    if not allowlist_path.is_file():
        return [f"missing allowlist {allowlist_path}"]

    try:
        allowed_mismatches = load_allowlist(allowlist_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid allowlist {allowlist_path}: {exc}"]

    projects: dict[str, str] = {}
    for relative in PREBUILT_RELATIVE:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing prebuilt Firebase config: {relative}")
            continue
        project = _project_from_prebuilt(path)
        if not project:
            errors.append(f"{relative}: could not parse Firebase project id")
            continue
        if project.startswith("__inconsistent__:"):
            errors.append(f"{relative}: inconsistent projectId values ({project.split(':', 1)[1]})")
            continue
        projects[relative] = project

    unique_projects = set(projects.values())
    if len(unique_projects) > 1:
        detail = ", ".join(f"{path}={proj}" for path, proj in sorted(projects.items()))
        errors.append(f"prebuilt Firebase configs disagree on project id: {detail}")

    prebuilt_project = next(iter(unique_projects), None)

    for relative in SETUP_SCRIPTS:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing setup script: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        api = _setup_default_api(text)
        if api != REMOTE_STAGING_API:
            errors.append(
                f"{relative}: default API_BASE_URL must be {REMOTE_STAGING_API!r} "
                f"(community remote staging); found {api!r}"
            )
        if not any(marker in text for marker in ALIGNMENT_MARKERS):
            errors.append(
                f"{relative}: must call Firebase/API alignment validation "
                f"({ALIGNMENT_MARKERS[0]} / {ALIGNMENT_MARKERS[1]}) — see #9404"
            )
        if FORBIDDEN_FLUTTERFIRE_DEV_PROJECT.search(text):
            errors.append(
                f"{relative}: must not regenerate FlutterFire configs with "
                f"--project=based-hardware-dev for the community remote-staging default "
                f"(reintroduces the #9404/#5939 401 mismatch)"
            )

    if prebuilt_project is None:
        return errors

    if prebuilt_project == REQUIRED_REMOTE_STAGING_FIREBASE:
        if allowed_mismatches:
            errors.append(
                "prebuilt Firebase already targets based-hardware; shrink "
                "allowed_prebuilt_projects_while_api_is_remote_staging to [] "
                f"(still lists {allowed_mismatches!r})"
            )
        return errors

    # Mismatch against the remote-staging contract.
    if prebuilt_project in allowed_mismatches:
        # Known debt: only based-hardware-dev is expected while FlutterFire regen is pending.
        unexpected = [p for p in allowed_mismatches if p != prebuilt_project]
        if unexpected:
            errors.append(
                "allowlist lists projects that are not the current prebuilt project; "
                f"shrink to exactly [{prebuilt_project!r}] (extra: {unexpected!r})"
            )
        return errors

    errors.append(
        f"community remote staging requires Firebase {REQUIRED_REMOTE_STAGING_FIREBASE!r} "
        f"when API is {REMOTE_STAGING_API!r}, but prebuilt declares {prebuilt_project!r}. "
        f"Regenerate app/setup/prebuilt/* via FlutterFire against based-hardware "
        f"(do not text-replace project ids — see #5945). "
        f"Or, if this is still the known #9404 debt, allowlist must contain "
        f"{prebuilt_project!r} and may only shrink."
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    args = parser.parse_args()

    root = repo_root(str(args.root) if args.root else None)
    allowlist_path = args.allowlist if args.allowlist.is_absolute() else root / args.allowlist
    errors = validate(root, allowlist_path)
    if errors:
        print("FAIL: community mobile Firebase/API alignment (#9404)")
        print(*errors, sep="\n")
        return 1
    print("OK: community mobile Firebase/API alignment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
