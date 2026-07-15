#!/usr/bin/env python3
"""Fixtures for public-build wiring and live-configuration preflights."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC_PATH = ROOT / ".github" / "scripts" / "check_public_build_contract.py"
PREFLIGHT_PATH = ROOT / ".github" / "scripts" / "preflight_public_build_config.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STATIC = load_module("check_public_build_contract", STATIC_PATH)
PREFLIGHT = load_module("preflight_public_build_config", PREFLIGHT_PATH)


class PublicBuildContractFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="omi-public-build-contract-")
        self.root = Path(self.temp_dir.name)
        self.write_json(
            "config/deployment-setting-classification.json",
            {"kinds": {"public_build": ["FAKE_PUBLIC_ONE", "FAKE_PUBLIC_TWO"]}},
        )
        self.write_json(
            "config/public-build-contract.json",
            {
                "targets": {
                    "fake": {
                        "dockerfile": "web/fake/Dockerfile",
                        "workflow": ".github/workflows/fake.yml",
                        "inputs": [
                            {"name": "FAKE_PUBLIC_ONE", "scope": "repository"},
                            {"name": "FAKE_PUBLIC_TWO", "scope": "environment"},
                        ],
                    }
                }
            },
        )
        self.write(
            "web/fake/Dockerfile",
            """ARG FAKE_PUBLIC_ONE
ARG FAKE_PUBLIC_TWO
ENV OMI_REQUIRED_PUBLIC_BUILD_INPUTS="FAKE_PUBLIC_ONE FAKE_PUBLIC_TWO"
RUN for name in $OMI_REQUIRED_PUBLIC_BUILD_INPUTS; do value="$(printenv \"$name\")"; test -n "$value"; done
""",
        )
        self.write(
            ".github/workflows/fake.yml",
            """run: |
  docker build \\
    --build-arg "FAKE_PUBLIC_ONE=${{ vars.FAKE_PUBLIC_ONE }}" \\
    --build-arg "FAKE_PUBLIC_TWO=${{ vars.FAKE_PUBLIC_TWO }}" \\
    -f web/fake/Dockerfile .
""",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, relative_path: str, contents: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def write_json(self, relative_path: str, value: object) -> None:
        self.write(relative_path, json.dumps(value))

    def static_errors(self) -> list[str]:
        targets = STATIC.load_contract(self.root / "config/public-build-contract.json")
        return STATIC.validate(
            self.root,
            targets.values(),
            STATIC.public_build_names(self.root / "config/deployment-setting-classification.json"),
        )

    def test_accepts_matching_contract_dockerfile_and_workflow(self) -> None:
        self.assertEqual(self.static_errors(), [])

    def test_rejects_missing_workflow_build_argument(self) -> None:
        self.write(
            ".github/workflows/fake.yml",
            "--build-arg FAKE_PUBLIC_ONE=${{ vars.FAKE_PUBLIC_ONE }}\n",
        )

        self.assertIn("required public build arg FAKE_PUBLIC_TWO is missing", "\n".join(self.static_errors()))

    def test_rejects_unguarded_dockerfile_input(self) -> None:
        self.write(
            "web/fake/Dockerfile",
            """ARG FAKE_PUBLIC_ONE
ARG FAKE_PUBLIC_TWO
ENV OMI_REQUIRED_PUBLIC_BUILD_INPUTS="FAKE_PUBLIC_ONE"
RUN for name in $OMI_REQUIRED_PUBLIC_BUILD_INPUTS; do value="$(printenv \"$name\")"; test -n "$value"; done
""",
        )

        self.assertIn("empty-value guard omits FAKE_PUBLIC_TWO", "\n".join(self.static_errors()))

    def test_rejects_unclassified_contract_input(self) -> None:
        self.write_json(
            "config/deployment-setting-classification.json",
            {"kinds": {"public_build": ["FAKE_PUBLIC_ONE"]}},
        )

        self.assertIn("required input FAKE_PUBLIC_TWO is not classified public_build", "\n".join(self.static_errors()))

    def test_live_preflight_rejects_effective_scope_drift_and_empty_values(self) -> None:
        target = STATIC.load_contract(self.root / "config/public-build-contract.json")["fake"]
        errors = PREFLIGHT.validate_target(
            target,
            {
                "organization": {},
                "repository": {"FAKE_PUBLIC_ONE": "configured"},
                "environment": {"FAKE_PUBLIC_TWO": "", "FAKE_PUBLIC_ONE": "override"},
            },
        )

        self.assertEqual(
            errors,
            [
                "fake: FAKE_PUBLIC_ONE resolves from environment, expected repository",
                "fake: required FAKE_PUBLIC_TWO is empty in environment",
            ],
        )

    def test_live_preflight_paginates_variable_inventory(self) -> None:
        requests: list[str] = []

        def requester(url: str, _token: str) -> dict:
            requests.append(url)
            if url.endswith("page=1"):
                return {"total_count": 2, "variables": [{"name": "ONE", "value": "one"}]}
            return {"total_count": 2, "variables": [{"name": "TWO", "value": "two"}]}

        self.assertEqual(
            PREFLIGHT.list_variables("https://example.test/variables", "token", requester),
            {"ONE": "one", "TWO": "two"},
        )
        self.assertEqual(len(requests), 2)


if __name__ == "__main__":
    unittest.main()
