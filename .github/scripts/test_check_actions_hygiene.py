#!/usr/bin/env python3
"""Unit tests for check_actions_hygiene.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_actions_hygiene import validate


def write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ActionsHygieneTests(unittest.TestCase):
    def test_accepts_sha_pinned_third_party_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ok.yml",
                "name: ok\n"
                "jobs:\n"
                "  t:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: pypa/gh-action-pypi-publish@"
                "dc37677b2e1c63e2034f94d8a5b11f265b73ba33\n",
            )
            self.assertEqual(validate(root), [])

    def test_rejects_latest_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/bad.yml",
                "name: bad\n"
                "jobs:\n"
                "  t:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: some-org/some-action@latest\n",
            )
            errors = validate(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("@latest", errors[0])

    def test_rejects_pypi_release_branch_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/publish.yml",
                "jobs:\n  p:\n    steps:\n      - uses: pypa/gh-action-pypi-publish@release/v1\n",
            )
            self.assertTrue(any("pypa/gh-action-pypi-publish@release/" in e for e in validate(root)))

    def test_rejects_rust_toolchain_channel_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/rust.yml",
                "jobs:\n  r:\n    steps:\n      - uses: dtolnay/rust-toolchain@stable\n",
            )
            self.assertTrue(any("dtolnay/rust-toolchain@stable" in e for e in validate(root)))

    def test_rejects_flutter_cache_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/mobile.yml",
                "jobs:\n"
                "  g:\n"
                "    steps:\n"
                "      - uses: actions/cache@v6\n"
                "        with:\n"
                "          key: ${{ runner.os }}-flutter-buildrunner-abc-${{ github.run_id }}\n",
            )
            errors = validate(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("github.run_id", errors[0])

    def test_rejects_nested_backend_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, ".github/workflows/noop.yml", "name: noop\n")
            write(root, "backend/.github/workflows/legacy.yml", "name: legacy\n")
            errors = validate(root)
            self.assertTrue(any("backend/.github/workflows" in e for e in errors))

    def test_rejects_third_party_master_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/bad.yml",
                "jobs:\n  t:\n    steps:\n      - uses: some-org/tool@master\n",
            )
            self.assertTrue(any("@master" in e for e in validate(root)))


if __name__ == "__main__":
    unittest.main()
