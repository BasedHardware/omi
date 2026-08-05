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


def _seed_minimal_tree(root: Path) -> Path:
    """Copy the real prebuilt + setup scripts into a temp tree for mutation tests."""
    for relative in CHECKER.PREBUILT_RELATIVE + CHECKER.SETUP_SCRIPTS:
        src = ROOT / relative
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    allowlist = root / ".github/scripts/mobile_community_firebase_alignment_allowlist.json"
    allowlist.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".github/scripts/mobile_community_firebase_alignment_allowlist.json",
        allowlist,
    )
    return allowlist


class CommunityFirebaseAlignmentContractTests(unittest.TestCase):
    def test_current_tree_passes_with_known_debt_allowlist(self) -> None:
        self.assertEqual(
            CHECKER.validate(ROOT, ROOT / CHECKER.DEFAULT_ALLOWLIST),
            [],
        )

    def test_rejects_missing_alignment_validator_in_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist = _seed_minimal_tree(root)
            setup = root / "app/setup.sh"
            text = setup.read_text(encoding="utf-8")
            # Strip every alignment marker so the contract fails closed.
            for marker in CHECKER.ALIGNMENT_MARKERS:
                text = text.replace(marker, "alignment_hook_removed")
            setup.write_text(text, encoding="utf-8")
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("alignment validation" in e for e in errors), errors)

    def test_rejects_flutterfire_based_hardware_dev_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist = _seed_minimal_tree(root)
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
            allowlist = _seed_minimal_tree(root)
            setup = root / "app/setup.sh"
            setup.write_text(
                setup.read_text(encoding="utf-8").replace(
                    "API_BASE_URL=https://api.omiapi.com/",
                    "API_BASE_URL=https://api.omi.me/",
                    1,
                ),
                encoding="utf-8",
            )
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("default API_BASE_URL" in e for e in errors), errors)

    def test_allowlist_must_shrink_when_prebuilt_is_based_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist = _seed_minimal_tree(root)
            for relative in CHECKER.PREBUILT_RELATIVE:
                path = root / relative
                path.write_text(
                    path.read_text(encoding="utf-8")
                    .replace("based-hardware-dev", "based-hardware")
                    .replace("based-hardware-dev", "based-hardware"),
                    encoding="utf-8",
                )
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("shrink" in e and "based-hardware" in e for e in errors), errors)

    def test_fixed_prebuilt_passes_with_empty_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist = _seed_minimal_tree(root)
            for relative in CHECKER.PREBUILT_RELATIVE:
                path = root / relative
                text = path.read_text(encoding="utf-8")
                path.write_text(text.replace("based-hardware-dev", "based-hardware"), encoding="utf-8")
            allowlist.write_text(
                json.dumps(
                    {
                        "issue": "https://github.com/BasedHardware/omi/issues/9404",
                        "allowed_prebuilt_projects_while_api_is_remote_staging": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(CHECKER.validate(root, allowlist), [])

    def test_rejects_unallowlisted_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist = _seed_minimal_tree(root)
            allowlist.write_text(
                json.dumps(
                    {
                        "issue": "https://github.com/BasedHardware/omi/issues/9404",
                        "allowed_prebuilt_projects_while_api_is_remote_staging": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            errors = CHECKER.validate(root, allowlist)
            self.assertTrue(any("requires Firebase 'based-hardware'" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
