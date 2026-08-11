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

    def test_rejects_run_sha_tag_with_operator_selected_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/deploy.yml",
                "jobs:\n"
                "  d:\n"
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          ref: ${{ github.event.inputs.branch }}\n"
                "      - run: echo \"tag=${GITHUB_SHA::7}\" >> \"$GITHUB_OUTPUT\"\n",
            )
            errors = validate(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("operator-selected", errors[0])

    def test_accepts_checked_out_head_tag_with_operator_selected_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/deploy.yml",
                "jobs:\n"
                "  d:\n"
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          ref: ${{ github.event.inputs.branch }}\n"
                "      - run: echo \"tag=$(git rev-parse --short=7 HEAD)\" >> \"$GITHUB_OUTPUT\"\n",
            )
            self.assertEqual(validate(root), [])

    def test_rejects_any_nested_component_workflow_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, ".github/workflows/noop.yml", "name: noop\n")
            write(root, "some-component/.github/workflows/local.yml", "name: local\n")
            errors = validate(root)
            self.assertTrue(any("some-component/.github/workflows" in e for e in errors))

    def test_ignores_vendored_nested_workflow_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, ".github/workflows/noop.yml", "name: noop\n")
            write(root, "fw/.pio/libdeps/dep/.github/workflows/build.yml", "name: upstream\n")
            write(root, "web/node_modules/dep/.github/workflows/ci.yml", "name: upstream\n")
            self.assertEqual(validate(root), [])

    def test_rejects_quoted_third_party_branch_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/bad.yml",
                "jobs:\n  t:\n    steps:\n      - uses: 'some-org/tool@main'\n",
            )
            self.assertTrue(any("@main" in e for e in validate(root)))

    def test_rejects_run_sha_with_workflow_level_inputs_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/promote.yml",
                "jobs:\n"
                "  d:\n"
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          ref: ${{ inputs.release_tag }}\n"
                "      - run: echo \"tag=${GITHUB_SHA::7}\"\n",
            )
            errors = validate(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("operator-selected", errors[0])

    def test_accepts_composite_action_inputs_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, ".github/workflows/noop.yml", "name: noop\n")
            write(
                root,
                ".github/actions/deploy/action.yml",
                "runs:\n"
                "  using: composite\n"
                "  steps:\n"
                "    - uses: actions/checkout@v7\n"
                "      with:\n"
                "        ref: ${{ inputs.admitted_sha }}\n"
                "    - run: echo \"${{ github.sha }}\"\n"
                "      shell: bash\n",
            )
            self.assertEqual(validate(root), [])

    def test_accepts_run_sha_in_sibling_job_without_operator_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/deploy.yml",
                "jobs:\n"
                "  deploy:\n"
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          ref: ${{ github.event.inputs.branch }}\n"
                "      - run: echo \"tag=$(git rev-parse --short=7 HEAD)\"\n"
                "  notify:\n"
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "      - run: echo \"built ${{ github.sha }}\"\n",
            )
            self.assertEqual(validate(root), [])

    def test_ignores_run_sha_in_trailing_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/deploy.yml",
                "jobs:\n"
                "  d:\n"
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          ref: ${{ github.event.inputs.branch }}\n"
                "      - run: echo ok  # never tag from GITHUB_SHA here\n",
            )
            self.assertEqual(validate(root), [])

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
