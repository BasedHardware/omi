#!/usr/bin/env python3
"""Behavioral regression tests for the check-manifest shrink ratchet."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("checks_manifest_ratchet", SCRIPT_DIR / "check_checks_manifest_ratchet.py")
assert SPEC and SPEC.loader
RATCHET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RATCHET)

REPO_ROOT = SCRIPT_DIR.parents[1]


def manifest_text(ids: list[str]) -> str:
    lines = ["checks:"]
    for check_id in ids:
        lines.append(f"  - id: {check_id}")
        lines.append('    command: ["python3", ".github/scripts/check_checks_manifest_ratchet.py"]')
        lines.append('    triggers: ["all"]')
        lines.append('    lanes: ["local", "ci"]')
        lines.append(f'    reason: "guards {check_id}"')
    return "\n".join(lines) + "\n"


class ChecksManifestShrinkRatchetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".github/scripts").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, encoding="utf-8")

    def write_manifest(self, ids: list[str]) -> None:
        (self.root / RATCHET.MANIFEST_RELATIVE).write_text(manifest_text(ids), encoding="utf-8")

    def write_retired(self, retired: dict[str, str]) -> None:
        (self.root / RATCHET.RETIRED_IDS_RELATIVE).write_text(json.dumps({"retired": retired}), encoding="utf-8")

    def commit_base(self, ids: list[str]) -> None:
        self.git("init", "--quiet")
        self.git("config", "user.email", "ratchet@example.invalid")
        self.git("config", "user.name", "ratchet")
        self.write_manifest(ids)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "base")

    def run_main(self) -> int:
        parsed = RATCHET.argparse.Namespace(root=str(self.root), base="HEAD")
        original = RATCHET.parse_args
        RATCHET.parse_args = lambda: parsed
        try:
            return RATCHET.main()
        finally:
            RATCHET.parse_args = original

    def test_ids_survive_unchanged(self) -> None:
        self.commit_base(["alpha", "beta"])
        self.assertEqual(self.run_main(), 0)

    def test_added_check_is_allowed(self) -> None:
        self.commit_base(["alpha"])
        self.write_manifest(["alpha", "gamma"])
        self.assertEqual(self.run_main(), 0)

    def test_silent_deletion_fails(self) -> None:
        self.commit_base(["alpha", "beta"])
        self.write_manifest(["alpha"])
        self.assertEqual(self.run_main(), 1)

    def test_recorded_retirement_is_admitted(self) -> None:
        self.commit_base(["alpha", "beta"])
        self.write_manifest(["alpha"])
        self.write_retired({"beta": "superseded by alpha in #1234"})
        self.assertEqual(self.run_main(), 0)

    def test_stale_retirement_entry_fails(self) -> None:
        self.commit_base(["alpha", "beta"])
        self.write_retired({"beta": "superseded by alpha in #1234"})
        self.assertEqual(self.run_main(), 1)

    def test_malformed_retirement_reason_fails(self) -> None:
        self.commit_base(["alpha", "beta"])
        self.write_manifest(["alpha"])
        self.write_retired({"beta": "  "})
        self.assertEqual(self.run_main(), 2)

    def test_missing_base_manifest_is_not_an_error(self) -> None:
        self.git("init", "--quiet")
        self.git("config", "user.email", "ratchet@example.invalid")
        self.git("config", "user.name", "ratchet")
        (self.root / "README").write_text("seed\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "base")
        self.write_manifest(["alpha"])
        self.assertEqual(self.run_main(), 0)

    def test_live_repository_ledger_is_well_formed(self) -> None:
        retired = RATCHET.load_retired_ids(REPO_ROOT)
        live = RATCHET.check_ids(REPO_ROOT / RATCHET.MANIFEST_RELATIVE)
        self.assertIn("checks-manifest-shrink-ratchet", live)
        self.assertEqual(RATCHET.removal_failures(live, live, retired), [])


if __name__ == "__main__":
    unittest.main()
