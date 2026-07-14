#!/usr/bin/env python3
"""Unit fixtures for the name-only deployment setting boundary ratchet."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / ".github" / "scripts" / "check_deployment_secret_boundary.py"
SPEC = importlib.util.spec_from_file_location("deployment_secret_boundary", CHECKER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {CHECKER_PATH}")
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)

POLICY = {
    "kinds": {
        "secret": ["FAKE_SERVER_SECRET"],
        "config": ["FAKE_RUNTIME_CONFIG"],
        "public_build": ["FAKE_PUBLIC_BUILD"],
    },
    "exceptions": {},
}


class RepositoryPathFixture(unittest.TestCase):
    def test_windows_repository_paths_use_git_separators(self) -> None:
        root = PureWindowsPath("C:/omi")
        path = root / ".github" / "workflows" / "deploy.yml"

        self.assertEqual(CHECKER._repository_relative_path(path, root), ".github/workflows/deploy.yml")


def git_environment() -> dict[str, str]:
    """Temporary fixture repositories must not inherit the hook's Git paths."""
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


class DeploymentSecretBoundaryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="omi-deployment-boundary-")
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env=git_environment())
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True, env=git_environment()
        )
        subprocess.run(
            ["git", "config", "user.name", "Boundary Test"], cwd=self.root, check=True, env=git_environment()
        )
        self.write("config/deployment-setting-classification.json", json.dumps(POLICY))
        self.write(".github/workflows/deploy.yml", "name: test\n")
        self.commit("baseline")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, relative_path: str, contents: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def commit(self, message: str) -> None:
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, env=git_environment())
        subprocess.run(["git", "commit", "-qm", message], cwd=self.root, check=True, env=git_environment())

    def errors(self) -> list[str]:
        policy = CHECKER.load_policy(self.root / "config/deployment-setting-classification.json")
        return CHECKER.validate_policy(policy) + CHECKER.validate_bindings(
            policy,
            CHECKER.extract_current_bindings(self.root),
            CHECKER.extract_base_bindings(self.root, "HEAD"),
        )

    def test_accepts_correct_secret_and_variable_bindings(self) -> None:
        self.write(
            ".github/workflows/deploy.yml",
            """name: deploy
jobs:
  deploy:
    env:
      CONFIG: ${{ vars.FAKE_RUNTIME_CONFIG }}
      TOKEN: ${{ secrets.FAKE_SERVER_SECRET }}
      BUILD: ${{ vars.FAKE_PUBLIC_BUILD }}
""",
        )

        self.assertEqual(self.errors(), [])

    def test_rejects_public_build_setting_from_github_secret(self) -> None:
        self.write(".github/workflows/deploy.yml", "BUILD: ${{ secrets.FAKE_PUBLIC_BUILD }}\n")

        self.assertIn(
            "public_build setting FAKE_PUBLIC_BUILD must use vars.FAKE_PUBLIC_BUILD", "\n".join(self.errors())
        )

    def test_rejects_config_external_secret_mapping(self) -> None:
        self.write(
            "backend/charts/backend-secrets/dev_omi_backend_secrets_values.yaml",
            """externalSecret:
  secretKeys:
    - secretKey: FAKE_RUNTIME_CONFIG
      remoteKey: FAKE_RUNTIME_CONFIG
""",
        )

        self.assertIn(
            "external_secret binding FAKE_RUNTIME_CONFIG is config; expected secret", "\n".join(self.errors())
        )

    def test_rejects_secret_from_github_variable(self) -> None:
        self.write(".github/workflows/deploy.yml", "TOKEN: ${{ vars.FAKE_SERVER_SECRET }}\n")

        self.assertIn(
            "github_vars binding FAKE_SERVER_SECRET is secret; expected config or public_build",
            "\n".join(self.errors()),
        )

    def test_rejects_config_loaded_from_secret_manager(self) -> None:
        self.write(
            ".github/workflows/deploy.yml",
            'echo "FAKE_RUNTIME_CONFIG=$(gcloud secrets versions access latest --secret=FAKE_SERVER_SECRET)"\n',
        )

        self.assertIn("secret_manager binding FAKE_RUNTIME_CONFIG is config; expected secret", "\n".join(self.errors()))

    def test_rejects_new_unclassified_binding_but_allows_legacy_baseline(self) -> None:
        self.write(".github/workflows/deploy.yml", "TOKEN: ${{ secrets.FAKE_LEGACY_NAME }}\n")
        self.commit("legacy binding")
        self.assertEqual(self.errors(), [])

        self.write(
            ".github/workflows/other.yml",
            "TOKEN: ${{ secrets.FAKE_LEGACY_NAME }}\n",
        )
        self.assertIn("github_secrets binding FAKE_LEGACY_NAME is unclassified", "\n".join(self.errors()))

    def test_rejects_malformed_exception_metadata(self) -> None:
        policy = dict(POLICY)
        policy["exceptions"] = {"FAKE_RUNTIME_CONFIG": {"owner": "platform"}}
        self.write("config/deployment-setting-classification.json", json.dumps(policy))

        errors = CHECKER.validate_policy(
            CHECKER.load_policy(self.root / "config/deployment-setting-classification.json")
        )

        self.assertIn("exception FAKE_RUNTIME_CONFIG is missing reason", errors)
        self.assertIn("exception FAKE_RUNTIME_CONFIG is missing expires", errors)
        self.assertIn("exception FAKE_RUNTIME_CONFIG is missing allowed_sources", errors)


if __name__ == "__main__":
    unittest.main()
