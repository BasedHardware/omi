#!/usr/bin/env python3
"""Fail closed when community mobile Firebase setup can recreate #9404.

Profiles after #11273:

| Profile | API | Firebase identity |
| --- | --- | --- |
| Community local / emulator (default) | local backend | ``*-local`` prebuilt trio (e.g. ``demo-omi-local``) |
| Mobile beta / remote staging | ``https://api.omiapi.com/`` | ``based-hardware`` via FlutterFire + SA |

``api.omiapi.com`` verifies Firebase ID tokens against ``based-hardware``.
Tokens from ``based-hardware-dev`` are rejected with 401 after an apparently
successful sign-in (#9404 / #5939).

This checker:

1. Requires ``setup_firebase`` / ``SetupFirebase`` to validate the ``*-local``
   trio the app actually copies (json + dart + plist agree; not
   ``based-hardware-dev``).
2. Forbids FlutterFire generators that reintroduce ``based-hardware-dev``.
3. Requires beta FlutterFire to target ``based-hardware``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_LOCAL_PROJECT = "based-hardware-dev"
REQUIRED_BETA_FIREBASE = "based-hardware"
LOCAL_PREBUILT_RELATIVE = (
    "app/setup/prebuilt/firebase_options_local.dart",
    "app/setup/prebuilt/google-services-local.json",
    "app/setup/prebuilt/GoogleService-Info-Local.plist",
)
SETUP_SCRIPTS = (
    "app/setup.sh",
    "app/setup/scripts/setup.ps1",
)
ALIGNMENT_CALL_NAMES = (
    "validate_firebase_api_alignment",
    "Validate-FirebaseApiAlignment",
)
FORBIDDEN_FLUTTERFIRE_DEV_PROJECT = re.compile(
    r"flutterfire\s+config[\s\S]{0,400}?--project=[\"']based-hardware-dev[\"']",
    re.IGNORECASE,
)
REQUIRED_BETA_FLUTTERFIRE_PROJECT = re.compile(
    r"flutterfire\s+config[\s\S]{0,400}?--project=[\"']based-hardware[\"']",
    re.IGNORECASE,
)
# PowerShell StrictMode: a single unique Match pipeline result is a scalar
# string; .Count throws unless the result is forced to an array with @(...).
POWERSHELL_DART_ARRAY_CAST = re.compile(
    r"\$ids\s*=\s*@\(\s*\[regex\]::Matches\(",
    re.MULTILINE,
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
    ids = re.findall(r"projectId:\s*'([^']+)'", text)
    if not ids:
        return None
    unique = set(ids)
    if len(unique) != 1:
        return f"__inconsistent__:{','.join(sorted(unique))}"
    return next(iter(unique))


def _has_alignment_invocation(setup_text: str) -> bool:
    """Require a real call site, not merely the function definition name."""
    for raw_line in setup_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"function\s+validate_firebase_api_alignment\b", line):
            continue
        if re.match(r"function\s+Validate-FirebaseApiAlignment\b", line):
            continue
        if re.match(r"function\s+_firebase_project_id_from_prebuilt\b", line):
            continue
        if re.match(r"function\s+Get-FirebaseProjectIdFromPrebuilt\b", line):
            continue
        if any(name in line for name in ALIGNMENT_CALL_NAMES):
            return True
    return False


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    projects: dict[str, str] = {}
    for relative in LOCAL_PREBUILT_RELATIVE:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing local Firebase prebuilt: {relative}")
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
        errors.append(f"local Firebase prebuilt configs disagree on project id: {detail}")

    prebuilt_project = next(iter(unique_projects), None)
    if prebuilt_project == FORBIDDEN_LOCAL_PROJECT:
        errors.append(
            f"local Firebase prebuilt must not target {FORBIDDEN_LOCAL_PROJECT!r} "
            f"(remote staging rejects those tokens — #9404/#5939)"
        )

    for relative in SETUP_SCRIPTS:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing setup script: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_alignment_invocation(text):
            errors.append(
                f"{relative}: must call Firebase alignment validation "
                f"({ALIGNMENT_CALL_NAMES[0]} / {ALIGNMENT_CALL_NAMES[1]}) — see #9404"
            )
        if FORBIDDEN_FLUTTERFIRE_DEV_PROJECT.search(text):
            errors.append(
                f"{relative}: must not regenerate FlutterFire configs with "
                f"--project=based-hardware-dev (reintroduces the #9404/#5939 401 mismatch)"
            )
        # Beta path must keep based-hardware. setup.sh always has it; ps1 android beta too.
        if relative.endswith("setup.sh") and not REQUIRED_BETA_FLUTTERFIRE_PROJECT.search(text):
            errors.append(
                f"{relative}: beta FlutterFire must target --project={REQUIRED_BETA_FIREBASE!r}"
            )
        if relative.endswith("setup.ps1"):
            if not POWERSHELL_DART_ARRAY_CAST.search(text):
                errors.append(
                    f"{relative}: Dart projectId Match pipeline must use @(...) so "
                    f"$ids.Count works under Set-StrictMode (single unique id is a scalar)"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()

    root = repo_root(str(args.root) if args.root else None)
    errors = validate(root)
    if errors:
        print("FAIL: community mobile Firebase/API alignment (#9404)")
        print(*errors, sep="\n")
        return 1
    print("OK: community mobile Firebase/API alignment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
