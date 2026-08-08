#!/usr/bin/env python3
"""Regression contract for community mobile Firebase ↔ API alignment (#9404)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/check-mobile-community-firebase-alignment.py"
SPEC = importlib.util.spec_from_file_location("check_mobile_community_firebase_alignment", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

# Deterministic mismatch fixtures — do not copy live prebuilt, so negative-path
# coverage survives FlutterFire regen to based-hardware.
_DEV_JSON = '{\n  "project_id": "based-hardware-dev"\n}\n'
_DEV_DART = "const FirebaseOptions android = FirebaseOptions(\n  projectId: 'based-hardware-dev',\n);\n"
_DEV_PLIST = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<plist><dict>"
    "<key>PROJECT_ID</key><string>based-hardware-dev</string>"
    "</dict></plist>\n"
)
_HW_JSON = '{\n  "project_id": "based-hardware"\n}\n'
_HW_DART = "const FirebaseOptions android = FirebaseOptions(\n  projectId: 'based-hardware',\n);\n"
_HW_PLIST = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<plist><dict>"
    "<key>PROJECT_ID</key><string>based-hardware</string>"
    "</dict></plist>\n"
)

_MIN_SETUP_SH = """#!/usr/bin/env bash
API_BASE_URL="${API_BASE_URL:-https://api.omiapi.com/}"
function setup_firebase() {
  validate_firebase_api_alignment
}
function validate_firebase_api_alignment() {
  true
}
"""

_MIN_SETUP_PS1 = """
if ([string]::IsNullOrWhiteSpace($env:API_BASE_URL)) {
    $script:API_BASE_URL = "https://api.omiapi.com/"
} else {
    $script:API_BASE_URL = $env:API_BASE_URL
}
function SetupFirebase {
    Validate-FirebaseApiAlignment
}
function Validate-FirebaseApiAlignment {
}
"""


def _write_prebuilt(root: Path, *, project: str) -> None:
    mapping = {
        "based-hardware-dev": (_DEV_DART, _DEV_JSON, _DEV_PLIST),
        "based-hardware": (_HW_DART, _HW_JSON, _HW_PLIST),
    }
    dart, json_text, plist = mapping[project]
    files = {
        "app/setup/prebuilt/firebase_options.dart": dart,
        "app/setup/prebuilt/google-services.json": json_text,
        "app/setup/prebuilt/GoogleService-Info.plist": plist,
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _write_setup_scripts(root: Path, *, setup_sh: str = _MIN_SETUP_SH, setup_ps1: str = _MIN_SETUP_PS1) -> None:
    sh = root / "app/setup.sh"
    ps1 = root / "app/setup/scripts/setup.ps1"
    sh.parent.mkdir(parents=True, exist_ok=True)
    ps1.parent.mkdir(parents=True, exist_ok=True)
    sh.write_text(setup_sh, encoding="utf-8")
    ps1.write_text(setup_ps1, encoding="utf-8")


def _write_allowlist(root: Path, allowed: list[str]) -> Path:
    path = root / ".github/scripts/mobile_community_firebase_alignment_allowlist.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "issue": "https://github.com/BasedHardware/omi/issues/9404",
                "allowed_prebuilt_projects_while_api_is_remote_staging": allowed,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _seed_live_tree(root: Path) -> Path:
    """Copy the real prebuilt + setup scripts into a temp tree for mutation tests."""
    for relative in CHECKER.PREBUILT_RELATIVE + CHECKER.SETUP_SCRIPTS:
        src = ROOT / relative
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return _write_allowlist(
        root,
        json.loads(
            (ROOT / ".github/scripts/mobile_community_firebase_alignment_allowlist.json").read_text(
                encoding="utf-8"
            )
        )["allowed_prebuilt_projects_while_api_is_remote_staging"],
    )


class CommunityFirebaseAlignmentContractTests(unittest.TestCase):
    def test_current_tree_passes_with_known_debt_allowlist(self) -> None:
        self.assertEqual(
            CHECKER.validate(ROOT, ROOT / CHECKER.DEFAULT_ALLOWLIST),
            [],
        )

    def test_rejects_missing_alignment_invocation_in_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_prebuilt(root, project="based-hardware-dev")
            allowlist = _write_allowlist(root, ["based-hardware-dev"])
            # Function defined but never called — must fail closed.
            _write_setup_scripts(
                root,
                setup_sh="""#!/usr/bin/env bash
API_BASE_URL="${API_BASE_URL:-https://api.omiapi.com/}"
function validate_firebase_api_alignment() { true; }
function setup_firebase() { echo skip; }
""",
            )
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("alignment validation" in e for e in errors), errors)

    def test_rejects_flutterfire_based_hardware_dev_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist = _seed_live_tree(root)
            setup = root / "app/setup.sh"
            setup.write_text(
                setup.read_text(encoding="utf-8")
                + '\nflutterfire config --project="based-hardware-dev" --yes\n',
                encoding="utf-8",
            )
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("based-hardware-dev" in e and "FlutterFire" in e for e in errors), errors)

    def test_rejects_wrong_default_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_prebuilt(root, project="based-hardware-dev")
            allowlist = _write_allowlist(root, ["based-hardware-dev"])
            _write_setup_scripts(
                root,
                setup_sh="""#!/usr/bin/env bash
API_BASE_URL="${API_BASE_URL:-https://api.omi.me/}"
function setup_firebase() { validate_firebase_api_alignment; }
function validate_firebase_api_alignment() { true; }
""",
            )
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("default API_BASE_URL" in e for e in errors), errors)

    def test_allowlist_must_shrink_when_prebuilt_is_based_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_prebuilt(root, project="based-hardware")
            _write_setup_scripts(root)
            allowlist = _write_allowlist(root, ["based-hardware-dev"])
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("shrink" in e and "based-hardware" in e for e in errors), errors)

    def test_fixed_prebuilt_passes_with_empty_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_prebuilt(root, project="based-hardware")
            _write_setup_scripts(root)
            allowlist = _write_allowlist(root, [])
            self.assertEqual(CHECKER.validate(root, allowlist), [])

    def test_rejects_unallowlisted_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_prebuilt(root, project="based-hardware-dev")
            _write_setup_scripts(root)
            allowlist = _write_allowlist(root, [])
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("requires Firebase 'based-hardware'" in e for e in errors), errors)

    def test_rejects_arbitrary_allowlisted_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Write a non-dev mismatch that someone might try to admit.
            dart = "const FirebaseOptions android = FirebaseOptions(\n  projectId: 'evil-project',\n);\n"
            json_text = '{\n  "project_id": "evil-project"\n}\n'
            plist = (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                "<plist><dict>"
                "<key>PROJECT_ID</key><string>evil-project</string>"
                "</dict></plist>\n"
            )
            for relative, content in (
                ("app/setup/prebuilt/firebase_options.dart", dart),
                ("app/setup/prebuilt/google-services.json", json_text),
                ("app/setup/prebuilt/GoogleService-Info.plist", plist),
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            _write_setup_scripts(root)
            allowlist = _write_allowlist(root, ["evil-project"])
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("evil-project" in e for e in errors), errors)
            self.assertTrue(any("only allowlist exactly" in e or "Temporary CI debt" in e for e in errors), errors)

    def test_allowlist_wrong_top_level_type_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_prebuilt(root, project="based-hardware")
            _write_setup_scripts(root)
            path = root / ".github/scripts/mobile_community_firebase_alignment_allowlist.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[]\n", encoding="utf-8")
            errors = CHECKER.validate(root, path)
            self.assertTrue(any("invalid allowlist" in e for e in errors), errors)
            self.assertTrue(any("JSON object" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
