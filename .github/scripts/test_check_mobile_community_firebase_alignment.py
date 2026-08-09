#!/usr/bin/env python3
"""Regression contract for community mobile Firebase alignment (#9404 / #11273)."""

from __future__ import annotations

import importlib.util
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

_LOCAL_JSON = '{\n  "project_id": "demo-omi-local"\n}\n'
_LOCAL_DART = "const FirebaseOptions android = FirebaseOptions(\n  projectId: 'demo-omi-local',\n);\n"
_LOCAL_PLIST = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<plist><dict>"
    "<key>PROJECT_ID</key><string>demo-omi-local</string>"
    "</dict></plist>\n"
)
_DEV_JSON = '{\n  "project_id": "based-hardware-dev"\n}\n'
_DEV_DART = "const FirebaseOptions android = FirebaseOptions(\n  projectId: 'based-hardware-dev',\n);\n"
_DEV_PLIST = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<plist><dict>"
    "<key>PROJECT_ID</key><string>based-hardware-dev</string>"
    "</dict></plist>\n"
)

_MIN_SETUP_SH = """#!/usr/bin/env bash
BETA_API_BASE_URL="${OMI_BETA_API_BASE_URL:-https://api.omiapi.com/}"
function setup_firebase() {
  validate_firebase_api_alignment
}
function validate_firebase_api_alignment() {
  true
}
function setup_firebase_with_service_account_ios() {
  flutterfire config --project="based-hardware" --yes
}
"""

_MIN_SETUP_PS1 = """
Set-StrictMode -Version Latest
function SetupFirebase {
    Validate-FirebaseApiAlignment
}
function Validate-FirebaseApiAlignment {
}
function Get-FirebaseProjectIdFromPrebuilt {
    param([string]$Path)
    $text = Get-Content -Raw $Path
    if ($Path -like "*.dart") {
        $ids = @([regex]::Matches($text, "projectId:\\s*'([^']+)'") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
        if ($ids.Count -eq 1) { return $ids[0] }
        return ""
    }
    return ""
}
"""


def _write_local_prebuilt(root: Path, *, project: str = "demo-omi-local") -> None:
    mapping = {
        "demo-omi-local": (_LOCAL_DART, _LOCAL_JSON, _LOCAL_PLIST),
        "based-hardware-dev": (_DEV_DART, _DEV_JSON, _DEV_PLIST),
    }
    dart, json_text, plist = mapping[project]
    files = {
        "app/setup/prebuilt/firebase_options_local.dart": dart,
        "app/setup/prebuilt/google-services-local.json": json_text,
        "app/setup/prebuilt/GoogleService-Info-Local.plist": plist,
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


def _seed_live_tree(root: Path) -> None:
    for relative in CHECKER.LOCAL_PREBUILT_RELATIVE + CHECKER.SETUP_SCRIPTS:
        src = ROOT / relative
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


class CommunityFirebaseAlignmentContractTests(unittest.TestCase):
    def test_current_tree_passes(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_rejects_missing_alignment_invocation_in_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_local_prebuilt(root)
            _write_setup_scripts(
                root,
                setup_sh="""#!/usr/bin/env bash
function validate_firebase_api_alignment() { true; }
function setup_firebase() { echo skip; }
function setup_firebase_with_service_account_ios() {
  flutterfire config --project="based-hardware" --yes
}
""",
            )
            errors = CHECKER.validate(root)
            self.assertTrue(any("alignment validation" in e for e in errors), errors)

    def test_rejects_flutterfire_based_hardware_dev_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _seed_live_tree(root)
            setup = root / "app/setup.sh"
            setup.write_text(
                setup.read_text(encoding="utf-8")
                + '\nflutterfire config --project="based-hardware-dev" --yes\n',
                encoding="utf-8",
            )
            errors = CHECKER.validate(root)
            self.assertTrue(any("based-hardware-dev" in e and "FlutterFire" in e for e in errors), errors)

    def test_rejects_based_hardware_dev_local_prebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_local_prebuilt(root, project="based-hardware-dev")
            _write_setup_scripts(root)
            errors = CHECKER.validate(root)
            self.assertTrue(any("based-hardware-dev" in e for e in errors), errors)

    def test_rejects_disagreeing_local_trio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_local_prebuilt(root)
            bad = root / "app/setup/prebuilt/google-services-local.json"
            bad.write_text('{\n  "project_id": "other-project"\n}\n', encoding="utf-8")
            _write_setup_scripts(root)
            errors = CHECKER.validate(root)
            self.assertTrue(any("disagree" in e for e in errors), errors)

    def test_rejects_powershell_dart_parser_without_array_cast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_local_prebuilt(root)
            broken_ps1 = """
function SetupFirebase { Validate-FirebaseApiAlignment }
function Validate-FirebaseApiAlignment {}
function Get-FirebaseProjectIdFromPrebuilt {
    param([string]$Path)
    $text = Get-Content -Raw $Path
    if ($Path -like "*.dart") {
        $ids = [regex]::Matches($text, "projectId:\\s*'([^']+)'") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
        if ($ids.Count -eq 1) { return $ids[0] }
        return ""
    }
    return ""
}
"""
            _write_setup_scripts(root, setup_ps1=broken_ps1)
            errors = CHECKER.validate(root)
            self.assertTrue(any("Set-StrictMode" in e or "@(...)" in e for e in errors), errors)

    def test_live_setup_ps1_forces_dart_match_pipeline_to_array(self) -> None:
        text = (ROOT / "app/setup/scripts/setup.ps1").read_text(encoding="utf-8")
        self.assertRegex(text, CHECKER.POWERSHELL_DART_ARRAY_CAST)


if __name__ == "__main__":
    unittest.main()
