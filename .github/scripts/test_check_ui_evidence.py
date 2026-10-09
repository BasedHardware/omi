#!/usr/bin/env python3
"""Hermetic Git fixtures for the UI screenshot evidence contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ui_evidence", SCRIPT_DIR / "check_ui_evidence.py")
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECK
SPEC.loader.exec_module(CHECK)
UI_FILE = "desktop/macos/Desktop/Sources/Chat/Home.swift"
IMAGE = ".agent-artifacts/ui-evidence/test-branch/001-desktop-macos-chat-home.png"


class UIEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.write("README.md", "Fixture\n")
        self.write(UI_FILE, "original\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("update-ref", "refs/remotes/origin/main", self.base)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=UI Evidence Test", "-c", "user.email=ui-test@example.invalid", *args],
            cwd=self.root, env=CHECK.clean_git_env(), check=True, capture_output=True, text=True,
        )

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self) -> None:
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def add_ui(self) -> None:
        self.write(UI_FILE, "modified\n")

    def add_image(self, relative: str = IMAGE) -> None:
        # Deliberately not PNG bytes: content inspection is outside this gate.
        self.write(relative, "image content is not inspected\n")
        entry = {
            "file": Path(relative).name,
            "platform": "desktop-macos",
            "description": "Chat home",
            "captured_by": "agent",
            "source": "visual-audit",
        }
        self.write(str(Path(relative).parent / "evidence.json"), json.dumps({"version": 1, "images": [entry]}, indent=2) + "\n")

    def run_check(self, body: str = "", *, absent_body: bool = False) -> subprocess.CompletedProcess[str]:
        # Keep check inputs outside the repository so no fixture commit includes them.
        with tempfile.TemporaryDirectory() as inputs:
            files = Path(inputs) / "changed-files.txt"
            files.write_text(self.git("diff", "--name-only", "--no-renames", f"{self.base}...HEAD").stdout, encoding="utf-8")
            body_file = Path(inputs) / "body.md"
            if not absent_body:
                body_file.write_text(body, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "check_ui_evidence.py"), "--root", str(self.root), "--changed-files", str(files), "--base", "origin/main", "--head", "HEAD", "--pr-body-file", str(body_file)],
                env=CHECK.clean_git_env(), capture_output=True, text=True, check=False,
            )

    def assert_pass(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK:", result.stdout)

    def assert_fail(self, result: subprocess.CompletedProcess[str], message: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)
        self.assertIn(CHECK.CONTRACT, result.stderr)

    def test_no_ui_passes_without_body(self) -> None:
        self.write("README.md", "updated\n")
        self.commit()
        self.assert_pass(self.run_check(absent_body=True))

    def test_body_image_passes(self) -> None:
        self.add_ui()
        self.add_image()
        self.commit()
        self.assert_pass(self.run_check(f"![Chat home]({IMAGE})"))

    def test_preexisting_tracked_image_passes(self) -> None:
        self.add_image()
        self.commit()
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.add_ui()
        self.commit()
        self.assert_pass(self.run_check(f"UI screenshot: `{IMAGE}`"))

    def test_escape_passes_with_or_without_reason(self) -> None:
        self.add_ui()
        self.commit()
        for line in ("UI-Evidence: none", "UI-Evidence: none -- Internal state only"):
            with self.subTest(line=line):
                self.assert_pass(self.run_check(line))

    def test_escape_must_be_an_exact_line(self) -> None:
        self.add_ui()
        self.commit()
        for line in (" UI-Evidence: none", "UI-Evidence: none.", "Example UI-Evidence: none", "UI-Evidence: none -- "):
            with self.subTest(line=line):
                self.assert_fail(self.run_check(line), "no tracked UI screenshot")

    def test_missing_or_empty_body_fails_with_bootstrap_guidance(self) -> None:
        self.add_ui()
        self.commit()
        for absent in (False, True):
            with self.subTest(absent=absent):
                result = self.run_check(absent_body=absent)
                self.assert_fail(result, "no tracked UI screenshot")
                self.assertIn("OMI_PR_BODY_FILE=/tmp/pr-body.md git push", result.stderr)

    def test_missing_image_fails(self) -> None:
        self.add_ui()
        self.commit()
        self.assert_fail(self.run_check(f"![Missing]({IMAGE})"), "no tracked UI screenshot")

    def test_untracked_image_and_manifest_do_not_count(self) -> None:
        self.add_ui()
        self.commit()
        self.add_image()
        self.assert_fail(self.run_check(f"![Untracked]({IMAGE})"), "no tracked UI screenshot")

    def test_directory_and_symlink_do_not_count(self) -> None:
        self.add_ui()
        (self.root / IMAGE).mkdir(parents=True)
        self.write(IMAGE + "/placeholder", "directory\n")
        link = ".agent-artifacts/ui-evidence/test-branch/001-desktop-macos-link.png"
        (self.root / link).symlink_to("../../../README.md")
        self.commit()
        self.assert_fail(self.run_check(f"![Directory]({IMAGE})"), "no tracked UI screenshot")
        self.assert_fail(self.run_check(f"![Link]({link})"), "regular tracked file")

    def test_bad_filenames_fail_even_with_escape(self) -> None:
        names = ("chat-home.png", "000-desktop-macos-home.png", "001-linux-home.png", "001-web-Upper.png", "001-web-home.jpg", "001-web-" + "a" * 41 + ".png")
        for name in names:
            with self.subTest(name=name):
                relative = CHECK.EVIDENCE_ROOT + "test-branch/" + name
                self.add_ui()
                self.add_image(relative)
                self.commit()
                self.assert_fail(self.run_check("UI-Evidence: none"), "invalid screenshot directory or filename")

    def test_valid_reference_does_not_hide_another_bad_image(self) -> None:
        self.add_ui()
        self.add_image()
        self.write(CHECK.EVIDENCE_ROOT + "test-branch/bad.png", "bad\n")
        self.commit()
        self.assert_fail(self.run_check(f"![Chat]({IMAGE})"), "invalid screenshot directory or filename")

    def test_missing_manifest_fails(self) -> None:
        self.add_ui()
        self.write(IMAGE, "image\n")
        self.commit()
        self.assert_fail(self.run_check(f"![Chat]({IMAGE})"), "missing sibling")

    def test_invalid_manifest_fails(self) -> None:
        self.add_ui()
        self.add_image()
        manifest = str(Path(IMAGE).parent / "evidence.json")
        for text in ("not json", "[]", '{"version": 2, "images": []}', '{"version": 1, "images": []}'):
            with self.subTest(text=text):
                self.write(manifest, text)
                self.commit()
                self.assert_fail(self.run_check(f"![Chat]({IMAGE})"), "evidence.json")

    def test_invalid_entry_metadata_fails(self) -> None:
        self.add_ui()
        self.add_image()
        manifest = str(Path(IMAGE).parent / "evidence.json")
        data = json.loads((self.root / manifest).read_text(encoding="utf-8"))
        data["images"][0]["platform"] = "web"
        self.write(manifest, json.dumps(data, indent=2) + "\n")
        self.commit()
        self.assert_fail(self.run_check(f"![Chat]({IMAGE})"), "invalid metadata")

    def test_deleted_only_ui_does_not_trigger(self) -> None:
        (self.root / UI_FILE).unlink()
        self.commit()
        self.assert_pass(self.run_check(absent_body=True))

    def test_added_ui_triggers(self) -> None:
        self.write("app/lib/main.dart", "new\n")
        self.commit()
        self.assert_fail(self.run_check(), "no tracked UI screenshot")

    def test_ui_paths_match_manifest_globs_in_both_lanes(self) -> None:
        from run_checks import load_manifest, resolve_checks

        manifest = load_manifest(SCRIPT_DIR.parent / "checks-manifest.yaml")
        paths = ("app/lib/main.dart", UI_FILE, "desktop/macos/Desktop/Sources/Main.swift", "desktop/windows/src/main.ts", "desktop/windows/src/views/Home.tsx", "web/frontend/src/Home.tsx", "web/admin/app/page.tsx")
        for path in paths:
            self.assertTrue(CHECK.is_ui_source(path), path)
            for lane in ("local", "ci"):
                self.assertIn("ui-evidence", {check.id for check in resolve_checks(manifest, [path], lane)}, (path, lane))
        for path in ("backend/main.py", "app/test/home.dart", "desktop/windows/src/main.js", "web/admin/lib/api.ts"):
            self.assertFalse(CHECK.is_ui_source(path), path)


if __name__ == "__main__":
    unittest.main()
