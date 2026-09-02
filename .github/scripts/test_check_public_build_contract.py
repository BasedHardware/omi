#!/usr/bin/env python3
"""Fixtures for the public-build contract, source preflight, and browser smoke."""

from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
STATIC_PATH = ROOT / ".github" / "scripts" / "check_public_build_contract.py"
PREFLIGHT_PATH = ROOT / ".github" / "scripts" / "preflight_public_build_config.py"
SMOKE_PATH = ROOT / ".github" / "scripts" / "smoke_public_build_browser.py"
RUNTIME_PREFLIGHT_PATH = ROOT / ".github" / "scripts" / "preflight_public_build_runtime.py"


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
SMOKE = load_module("smoke_public_build_browser", SMOKE_PATH)
RUNTIME_PREFLIGHT = load_module("preflight_public_build_runtime", RUNTIME_PREFLIGHT_PATH)


def fixture_contract() -> dict:
    return {
        "schema_version": 4,
        "configuration": {
            "source": "repository_config",
            "path": "config/public-build-values.json",
            "environments": ["development", "prod"],
        },
        "targets": {
            "fake": {
                "service": "fake-service",
                "dockerfile": "web/fake/Dockerfile",
                "workflow": ".github/workflows/gcp_fake.yml",
                "deployment": {
                    "region": "us-central1",
                    "build_context": ".",
                    "platforms": ["linux/amd64"],
                    "flags": [],
                    "runtime_secrets": {"FAKE_RUNTIME_SECRET": "FAKE_RUNTIME_SECRET:latest"},
                    "preserve_runtime_secrets": [],
                    "runtime_env_vars": {},
                    "remove_runtime_secrets": [],
                },
                "canary_component": "web/fake/public-build-canary.tsx",
                "inputs": [
                    {
                        "name": "FAKE_PUBLIC_INPUT",
                        "required": True,
                        "source": "repository_config",
                        "allowed_scopes": ["repository"],
                    }
                ],
                "candidate_acceptance": {
                    "command": [
                        "python3",
                        ".github/scripts/smoke_public_build_browser.py",
                        "--target",
                        "fake",
                        "--base-url",
                        "{base_url}",
                    ],
                    "marker": "fake:ready",
                },
                "traffic_promotion": "candidate_after_browser_acceptance",
            }
        },
    }


def fixture_values(value: str = "configured") -> dict:
    return {
        "schema_version": 1,
        "environments": {
            "development": {"values": {"FAKE_PUBLIC_INPUT": value}},
            "prod": {"values": {"FAKE_PUBLIC_INPUT": value}},
        },
    }


class PublicBuildContractFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="omi-public-build-contract-")
        self.root = Path(self.temp_dir.name)
        self.write_json("config/public-build-contract.json", fixture_contract())
        self.write_json("config/public-build-values.json", fixture_values())
        self.write_json(
            "config/deployment-setting-classification.json",
            {"kinds": {"public_build": ["FAKE_PUBLIC_INPUT"]}},
        )
        self.write(
            "web/fake/Dockerfile",
            """ARG FAKE_PUBLIC_INPUT
ENV OMI_REQUIRED_PUBLIC_BUILD_INPUTS="FAKE_PUBLIC_INPUT"
RUN for name in $OMI_REQUIRED_PUBLIC_BUILD_INPUTS; do value="$(printenv "$name" || true)"; test -n "$value"; done
""",
        )
        self.write(
            ".github/workflows/gcp_fake.yml",
            """on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy to'
        required: false
        default: 'prod'
        type: choice
        options: [development, prod]
concurrency:
  group: fake-${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || github.ref == 'refs/heads/development' && 'development' || github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}
jobs:
  deploy:
    environment: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || (github.ref == 'refs/heads/development' && 'development') || 'prod' }}
    steps:
      - uses: ./.github/actions/deploy-public-build
        with:
          environment: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || (github.ref == 'refs/heads/development' && 'development') || 'prod' }}
""",
        )
        self.write(
            "web/fake/public-build-canary.tsx",
            '<span data-omi-public-build-canary="fake:ready" />\n',
        )
        self.write(
            ".github/workflows/public-build-config-preflight.yml",
            """on:
  pull_request:
  workflow_dispatch:
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

    def target(self):
        return STATIC.load_contract(self.root / "config/public-build-contract.json").targets["fake"]

    def errors(self) -> list[str]:
        return STATIC.validate_target(self.root, self.target(), {"FAKE_PUBLIC_INPUT"})

    def test_accepts_centralized_public_build_deployment(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_manual_development_dispatch_on_an_exact_pr_head_uses_development(self) -> None:
        self.assertEqual(
            STATIC.resolved_deploy_environment(
                event_name="workflow_dispatch",
                ref="refs/pull/10751/merge",
                requested_environment="development",
            ),
            "development",
        )
        for workflow_name in ("gcp_admin.yml", "gcp_app.yml"):
            with self.subTest(workflow=workflow_name):
                workflow_path = ROOT / ".github" / "workflows" / workflow_name
                self.assertEqual(
                    STATIC.validate_manual_environment_dispatch(
                        f".github/workflows/{workflow_name}", workflow_path.read_text(encoding="utf-8")
                    ),
                    [],
                )

    def test_manual_development_dispatch_rejects_an_unrecognized_environment(self) -> None:
        with self.assertRaisesRegex(ValueError, "must select development or prod"):
            STATIC.resolved_deploy_environment(
                event_name="workflow_dispatch",
                ref="refs/pull/10751/merge",
                requested_environment="preview",
            )

    def test_rejects_direct_build_or_deploy_wiring(self) -> None:
        self.write(
            ".github/workflows/gcp_fake.yml",
            (self.root / ".github/workflows/gcp_fake.yml").read_text(encoding="utf-8")
            + "  - uses: docker/build-push-action@v7\n",
        )

        self.assertIn("bypasses centralized public-build deployment", "\n".join(self.errors()))

    def test_rejects_missing_declared_build_context(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["build_context"] = "web/missing"
        self.write_json("config/public-build-contract.json", contract)

        self.assertIn("Docker build context is missing", "\n".join(self.errors()))

    def test_rejects_scheduled_public_build_reconciliation(self) -> None:
        self.write(
            ".github/workflows/public-build-config-preflight.yml",
            """on:
  pull_request:
  workflow_dispatch:
  schedule:
    - cron: '* * * * *'
""",
        )

        self.assertIn("must not schedule drift checks", "\n".join(STATIC.validate_jit_preflight_workflow(self.root)))

    def test_rejects_overlap_across_runtime_binding_groups(self) -> None:
        binding_groups = {
            "runtime_secrets": {"SHARED_RUNTIME_BINDING": "shared-runtime-binding:latest"},
            "preserve_runtime_secrets": ["SHARED_RUNTIME_BINDING"],
            "runtime_env_vars": {"SHARED_RUNTIME_BINDING": "reviewed.example"},
            "remove_runtime_secrets": ["SHARED_RUNTIME_BINDING"],
        }
        group_names = tuple(binding_groups)
        for index, left in enumerate(group_names):
            for right in group_names[index + 1 :]:
                with self.subTest(left=left, right=right):
                    contract = fixture_contract()
                    deployment = contract["targets"]["fake"]["deployment"]
                    for name in group_names:
                        deployment[name] = {} if name in {"runtime_secrets", "runtime_env_vars"} else []
                    deployment[left] = binding_groups[left]
                    deployment[right] = binding_groups[right]
                    deployment["fallback_runtime_secrets"] = {
                        name: f"fallback-{name.lower()}:latest" for name in deployment["preserve_runtime_secrets"]
                    }
                    self.write_json("config/public-build-contract.json", contract)

                    with self.assertRaisesRegex(ValueError, "runtime binding groups cannot overlap"):
                        self.target()

    def test_parses_remove_runtime_env_vars(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["remove_runtime_env_vars"] = ["STALE_PLAINTEXT"]
        self.write_json("config/public-build-contract.json", contract)

        self.assertEqual(self.target().deployment.remove_runtime_env_vars, ("STALE_PLAINTEXT",))

    def test_rejects_remove_runtime_env_vars_overlap_with_runtime_secrets(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["remove_runtime_env_vars"] = ["FAKE_RUNTIME_SECRET"]
        self.write_json("config/public-build-contract.json", contract)

        with self.assertRaisesRegex(ValueError, "remove_runtime_env_vars cannot overlap"):
            self.target()

    def test_rejects_remove_runtime_env_vars_overlap_with_runtime_env_vars(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["runtime_env_vars"] = {"FAKE_RUNTIME_CONFIG": "reviewed.example"}
        contract["targets"]["fake"]["deployment"]["remove_runtime_env_vars"] = ["FAKE_RUNTIME_CONFIG"]
        self.write_json("config/public-build-contract.json", contract)

        with self.assertRaisesRegex(ValueError, "remove_runtime_env_vars cannot overlap"):
            self.target()

    def test_rejects_remove_runtime_env_vars_overlap_with_preserve_runtime_secrets(self) -> None:
        contract = fixture_contract()
        deployment = contract["targets"]["fake"]["deployment"]
        deployment["preserve_runtime_secrets"] = ["FAKE_PRESERVED_SECRET"]
        deployment["fallback_runtime_secrets"] = {"FAKE_PRESERVED_SECRET": "fallback-fake-preserved-secret:latest"}
        deployment["remove_runtime_env_vars"] = ["FAKE_PRESERVED_SECRET"]
        self.write_json("config/public-build-contract.json", contract)

        with self.assertRaisesRegex(
            ValueError, "remove_runtime_env_vars cannot overlap.*preserve_runtime_secrets"
        ):
            self.target()

    def test_shared_flags_list_applies_to_every_environment(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["flags"] = ["--memory=2Gi"]
        self.write_json("config/public-build-contract.json", contract)
        deployment = self.target().deployment

        self.assertEqual(deployment.flags_for("development"), ("--memory=2Gi",))
        self.assertEqual(deployment.flags_for("prod"), ("--memory=2Gi",))

    def test_per_environment_flags_object_resolves_for_the_requested_environment(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["flags"] = {
            "prod": ["--ingress=internal-and-cloud-load-balancing"],
            "development": [],
        }
        self.write_json("config/public-build-contract.json", contract)
        deployment = self.target().deployment

        self.assertEqual(deployment.flags_for("prod"), ("--ingress=internal-and-cloud-load-balancing",))
        self.assertEqual(deployment.flags_for("development"), ())

    def test_rejects_flags_for_an_unknown_environment(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["flags"] = {"staging": ["--memory=2Gi"]}
        self.write_json("config/public-build-contract.json", contract)

        with self.assertRaisesRegex(ValueError, "unknown environment 'staging'"):
            self.target()

    def test_rejects_runtime_env_values_that_cannot_be_rendered_as_action_input(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["runtime_env_vars"] = {"FAKE_RUNTIME_CONFIG": "one,two"}
        self.write_json("config/public-build-contract.json", contract)

        with self.assertRaisesRegex(
            ValueError, "runtime_env_vars must map environment names to non-empty deploy-safe values"
        ):
            self.target()

    def test_runtime_env_vars_must_be_classified_as_reviewed_config(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["runtime_env_vars"] = {"FAKE_RUNTIME_CONFIG": "reviewed.example"}
        self.write_json("config/public-build-contract.json", contract)

        self.assertEqual(
            STATIC.validate_target(self.root, self.target(), {"FAKE_PUBLIC_INPUT"}, {"FAKE_RUNTIME_CONFIG"}),
            [],
        )
        self.assertEqual(
            STATIC.validate_target(self.root, self.target(), {"FAKE_PUBLIC_INPUT"}),
            ["fake: runtime env FAKE_RUNTIME_CONFIG is not classified config"],
        )

    def test_gateway_required_target_rejects_missing_or_empty_gateway_wiring(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["gateway_required"] = True
        self.write_json("config/public-build-contract.json", contract)

        self.assertEqual(
            STATIC.validate_target(self.root, self.target(), {"FAKE_PUBLIC_INPUT"}),
            [
                ".github/workflows/gcp_fake.yml: gateway-required target must source "
                "OMI_LLM_GATEWAY_URL from GitHub environment vars",
                ".github/workflows/gcp_fake.yml: gateway-required target must reject an empty " "OMI_LLM_GATEWAY_URL",
            ],
        )

    def test_runtime_preflight_rejects_literal_binding(self) -> None:
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {"name": "FAKE_RUNTIME_SECRET", "value": "not-a-secret-reference"},
                        ]
                    }
                ]
            }
        }

        self.assertEqual(
            RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service),
            [
                "fake: runtime binding FAKE_RUNTIME_SECRET is a literal; expected Secret Manager "
                "FAKE_RUNTIME_SECRET:latest"
            ],
        )

    def test_runtime_preflight_accepts_absent_or_matching_binding(self) -> None:
        matching_service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "FAKE_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "FAKE_RUNTIME_SECRET", "version": "latest"}},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), {"template": {}}), [])
        self.assertEqual(RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), matching_service), [])

    def test_runtime_preflight_accepts_v1_secret_binding(self) -> None:
        service = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {
                                        "name": "FAKE_RUNTIME_SECRET",
                                        "valueFrom": {"secretKeyRef": {"name": "FAKE_RUNTIME_SECRET", "key": "latest"}},
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }

        self.assertEqual(RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service), [])

    def test_runtime_preflight_normalizes_v1_and_v2_secret_binding_shapes(self) -> None:
        v1_service = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {
                                        "name": "FAKE_RUNTIME_SECRET",
                                        "valueFrom": {"secretKeyRef": {"name": "legacy-secret", "key": "7"}},
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
        v2_service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "FAKE_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "legacy-secret", "version": "7"}},
                            }
                        ]
                    }
                ]
            }
        }

        expected = {"FAKE_RUNTIME_SECRET": RUNTIME_PREFLIGHT.RuntimeBinding("secret", "legacy-secret:7")}
        self.assertEqual(RUNTIME_PREFLIGHT.current_bindings(v1_service), expected)
        self.assertEqual(RUNTIME_PREFLIGHT.current_bindings(v2_service), expected)

    def test_runtime_preflight_fails_closed_for_malformed_or_ambiguous_secret_binding_shapes(self) -> None:
        malformed_sources = (
            {"valueFrom": {"secretKeyRef": {"name": "legacy-secret"}}},
            {"valueFrom": {"secretKeyRef": {"key": "7"}}},
            {"valueSource": {"secretKeyRef": {"secret": "legacy-secret"}}},
            {"valueSource": {"secretKeyRef": {"version": "7"}}},
            {"valueSource": {"secretKeyRef": {"secret": "legacy-secret", "version": 7}}},
            {"valueFrom": {"secretKeyRef": {"secret": "legacy-secret", "version": "7"}}},
            {"valueSource": {"secretKeyRef": {"name": "legacy-secret", "key": "7"}}},
            {
                "valueSource": {
                    "secretKeyRef": {
                        "name": "legacy-secret",
                        "key": "7",
                        "secret": "other-secret",
                        "version": "8",
                    }
                }
            },
            {
                "valueSource": {
                    "secretKeyRef": {"secret": "legacy-secret", "version": "7"},
                    "configMapKeyRef": {"name": "other-source"},
                }
            },
            {
                "valueFrom": {"secretKeyRef": {"name": "legacy-secret", "key": "7"}},
                "valueSource": {"secretKeyRef": {"secret": "other-secret", "version": "8"}},
            },
            {
                "value": "literal",
                "valueFrom": {"secretKeyRef": {"name": "legacy-secret", "key": "7"}},
            },
            {
                "value": "literal",
                "valueSource": {"secretKeyRef": {"secret": "legacy-secret", "version": "7"}},
            },
        )

        for source in malformed_sources:
            with self.subTest(source=source):
                service = {"template": {"containers": [{"env": [{"name": "FAKE_RUNTIME_SECRET", **source}]}]}}

                self.assertEqual(
                    RUNTIME_PREFLIGHT.current_bindings(service),
                    {"FAKE_RUNTIME_SECRET": RUNTIME_PREFLIGHT.RuntimeBinding("invalid")},
                )
                self.assertEqual(
                    RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service),
                    ["fake-service: runtime binding FAKE_RUNTIME_SECRET has an ambiguous or malformed value source"],
                )

    def test_runtime_preflight_rejects_disabled_secret_version(self) -> None:
        original = RUNTIME_PREFLIGHT._gcloud_json
        RUNTIME_PREFLIGHT._gcloud_json = lambda _args: {"state": "DISABLED"}
        try:
            errors = RUNTIME_PREFLIGHT.validate_secret_versions(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original

        self.assertEqual(
            errors,
            [
                "fake-service: runtime binding FAKE_RUNTIME_SECRET requires enabled Secret Manager version "
                "FAKE_RUNTIME_SECRET:latest"
            ],
        )

    def test_runtime_preflight_reports_service_and_binding_for_an_unavailable_secret_version(self) -> None:
        original = RUNTIME_PREFLIGHT._gcloud_json

        def missing_version(_args):
            raise RUNTIME_PREFLIGHT.RuntimePreflightError("resource not found", category="not_found")

        RUNTIME_PREFLIGHT._gcloud_json = missing_version
        try:
            errors = RUNTIME_PREFLIGHT.validate_secret_versions(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original

        self.assertEqual(
            errors,
            [
                "fake-service: runtime binding FAKE_RUNTIME_SECRET requires Secret Manager version "
                "FAKE_RUNTIME_SECRET:latest, but it is unavailable (resource not found)"
            ],
        )

    def test_runtime_preflight_accepts_an_enabled_secret_version(self) -> None:
        original = RUNTIME_PREFLIGHT._gcloud_json
        RUNTIME_PREFLIGHT._gcloud_json = lambda _args: {"state": "ENABLED"}
        try:
            errors = RUNTIME_PREFLIGHT.validate_secret_versions(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original

        self.assertEqual(errors, [])

    def test_runtime_preflight_rejects_a_live_secret_binding_missing_from_the_deployment_contract(self) -> None:
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "STALE_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "stale-secret", "version": "latest"}},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(
            RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service),
            ["fake-service: secret binding STALE_RUNTIME_SECRET is missing from the deployment contract"],
        )

    def test_runtime_preflight_allows_a_live_secret_binding_rendered_for_removal(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["remove_runtime_secrets"] = ["STALE_RUNTIME_SECRET"]
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "STALE_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "stale-secret", "version": "latest"}},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service), [])

    def test_runtime_preflight_preserves_the_live_secret_reference_without_guessing_it(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        contract["targets"]["fake"]["deployment"]["fallback_runtime_secrets"] = {
            "PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"
        }
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "PRESERVED_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "legacy-secret", "version": "7"}},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service), [])
        calls: list[list[str]] = []
        original = RUNTIME_PREFLIGHT._gcloud_json

        def enabled(arguments):
            calls.append(arguments)
            return {"state": "ENABLED"}

        RUNTIME_PREFLIGHT._gcloud_json = enabled
        try:
            errors = RUNTIME_PREFLIGHT.validate_preserved_secret_versions(
                target=self.target(), service=service, project_id="fake-project"
            )
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original

        self.assertEqual(errors, [])
        self.assertIn("--secret=legacy-secret", calls[0])
        self.assertIn("7", calls[0])

    def test_runtime_preflight_rejects_a_disabled_preserved_secret_version(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        contract["targets"]["fake"]["deployment"]["fallback_runtime_secrets"] = {
            "PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"
        }
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "PRESERVED_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "legacy-secret", "version": "7"}},
                            }
                        ]
                    }
                ]
            }
        }
        original = RUNTIME_PREFLIGHT._gcloud_json
        RUNTIME_PREFLIGHT._gcloud_json = lambda _args: {"state": "DISABLED"}
        try:
            errors = RUNTIME_PREFLIGHT.validate_preserved_secret_versions(
                target=self.target(), service=service, project_id="fake-project"
            )
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original

        self.assertEqual(
            errors,
            [
                "fake-service: runtime binding PRESERVED_RUNTIME_SECRET requires enabled Secret Manager version "
                "legacy-secret:7"
            ],
        )

    def test_runtime_preflight_rejects_missing_or_literal_preserved_secret(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        contract["targets"]["fake"]["deployment"]["fallback_runtime_secrets"] = {
            "PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"
        }
        self.write_json("config/public-build-contract.json", contract)
        literal_service = {
            "template": {"containers": [{"env": [{"name": "PRESERVED_RUNTIME_SECRET", "value": "not-a-secret"}]}]}
        }

        self.assertEqual(
            RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), {"template": {}}),
            [
                "fake: preserved runtime secret PRESERVED_RUNTIME_SECRET is absent; expected an enabled Secret Manager binding"
            ],
        )
        self.assertEqual(
            RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), literal_service),
            [
                "fake: preserved runtime secret PRESERVED_RUNTIME_SECRET is a literal; expected an enabled Secret Manager binding"
            ],
        )

    def test_runtime_preflight_rejects_a_literal_secret_union_for_a_preserved_binding(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        contract["targets"]["fake"]["deployment"]["fallback_runtime_secrets"] = {
            "PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"
        }
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "PRESERVED_RUNTIME_SECRET",
                                "value": "literal",
                                "valueSource": {"secretKeyRef": {"secret": "legacy-secret", "version": "7"}},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(
            RUNTIME_PREFLIGHT.current_bindings(service),
            {"PRESERVED_RUNTIME_SECRET": RUNTIME_PREFLIGHT.RuntimeBinding("invalid")},
        )
        self.assertEqual(
            RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service),
            ["fake-service: runtime binding PRESERVED_RUNTIME_SECRET has an ambiguous or malformed value source"],
        )

    def test_runtime_preflight_uses_declared_fallback_bindings_for_a_first_create(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        contract["targets"]["fake"]["deployment"]["fallback_runtime_secrets"] = {
            "PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"
        }
        self.write_json("config/public-build-contract.json", contract)
        original_validate = RUNTIME_PREFLIGHT.validate_secret_versions
        original_load = RUNTIME_PREFLIGHT.load_current_service
        original_fallback = RUNTIME_PREFLIGHT.validate_fallback_secret_versions
        RUNTIME_PREFLIGHT.validate_secret_versions = lambda **_kwargs: []
        RUNTIME_PREFLIGHT.load_current_service = lambda **_kwargs: None
        RUNTIME_PREFLIGHT.validate_fallback_secret_versions = lambda **_kwargs: []
        try:
            errors, fallbacks = RUNTIME_PREFLIGHT.preflight_result(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT.validate_secret_versions = original_validate
            RUNTIME_PREFLIGHT.load_current_service = original_load
            RUNTIME_PREFLIGHT.validate_fallback_secret_versions = original_fallback

        self.assertEqual(errors, [])
        self.assertEqual(fallbacks, {"PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"})

    def test_runtime_preflight_reports_first_create_to_the_deployment_action(self) -> None:
        output = self.root / "runtime-preflight-output"
        original_result = RUNTIME_PREFLIGHT.preflight_deployment_result
        RUNTIME_PREFLIGHT.preflight_deployment_result = lambda **_kwargs: ([], {}, False)
        try:
            result = RUNTIME_PREFLIGHT.main(
                [
                    "--target",
                    "fake",
                    "--project-id",
                    "fake-project",
                    "--contract",
                    str(self.root / "config/public-build-contract.json"),
                    "--github-output",
                    str(output),
                ]
            )
        finally:
            RUNTIME_PREFLIGHT.preflight_deployment_result = original_result

        self.assertEqual(result, 0)
        self.assertIn("service_exists=false", output.read_text(encoding="utf-8"))

    def test_shared_action_handles_first_creates_and_fails_closed_for_production(self) -> None:
        deploy = (ROOT / ".github/actions/deploy-public-build/action.yml").read_text(encoding="utf-8")
        promotion = (ROOT / ".github/actions/public-build-candidate-promotion/action.yml").read_text(encoding="utf-8")

        self.assertIn("steps.runtime-preflight.outputs.service_exists", deploy)
        self.assertIn("no_traffic: ${{ steps.runtime-preflight.outputs.service_exists == 'true' }}", deploy)
        self.assertIn("Fail closed for a production first create", deploy)
        self.assertIn("refusing to create a public Cloud Run service outside development", deploy)
        self.assertIn("inputs.environment == 'development' && '--allow-unauthenticated' || ''", deploy)
        self.assertNotIn("first_create", promotion)

    def test_runtime_preflight_never_outputs_fallback_bindings_for_a_live_service(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        contract["targets"]["fake"]["deployment"]["fallback_runtime_secrets"] = {
            "PRESERVED_RUNTIME_SECRET": "fallback-secret:latest"
        }
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "PRESERVED_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"secret": "live-secret", "version": "7"}},
                            }
                        ]
                    }
                ]
            }
        }
        original_validate = RUNTIME_PREFLIGHT.validate_secret_versions
        original_load = RUNTIME_PREFLIGHT.load_current_service
        original_validate_current = RUNTIME_PREFLIGHT.validate_current_bindings
        original_validate_preserved = RUNTIME_PREFLIGHT.validate_preserved_secret_versions
        RUNTIME_PREFLIGHT.validate_secret_versions = lambda **_kwargs: []
        RUNTIME_PREFLIGHT.load_current_service = lambda **_kwargs: service
        RUNTIME_PREFLIGHT.validate_current_bindings = lambda *_args: []
        RUNTIME_PREFLIGHT.validate_preserved_secret_versions = lambda **_kwargs: []
        try:
            errors, fallbacks = RUNTIME_PREFLIGHT.preflight_result(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT.validate_secret_versions = original_validate
            RUNTIME_PREFLIGHT.load_current_service = original_load
            RUNTIME_PREFLIGHT.validate_current_bindings = original_validate_current
            RUNTIME_PREFLIGHT.validate_preserved_secret_versions = original_validate_preserved

        self.assertEqual(errors, [])
        self.assertEqual(fallbacks, {})

    def test_runtime_preflight_treats_an_authenticated_empty_service_list_as_first_create(self) -> None:
        original_run = RUNTIME_PREFLIGHT.subprocess.run
        RUNTIME_PREFLIGHT.subprocess.run = lambda *_args, **_kwargs: type("Result", (), {"stdout": "[]"})()
        try:
            self.assertIsNone(RUNTIME_PREFLIGHT.load_current_service(target=self.target(), project_id="fake-project"))
        finally:
            RUNTIME_PREFLIGHT.subprocess.run = original_run

    def test_runtime_preflight_does_not_infer_first_create_from_describe_text(self) -> None:
        original_run = RUNTIME_PREFLIGHT.subprocess.run
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if "list" in command:
                return type("Result", (), {"stdout": '[{"metadata": {"name": "fake-service"}}]'})()
            raise RUNTIME_PREFLIGHT.subprocess.CalledProcessError(
                1, command, stderr="ERROR: Service [fake-service] could not be found"
            )

        RUNTIME_PREFLIGHT.subprocess.run = run
        try:
            with self.assertRaisesRegex(
                RUNTIME_PREFLIGHT.RuntimePreflightError,
                "cannot inspect current Cloud Run service fake-service: gcloud command failed: ERROR: Service",
            ):
                RUNTIME_PREFLIGHT.load_current_service(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT.subprocess.run = original_run
        self.assertEqual(2, len(calls))

    def test_runtime_preflight_redacts_unknown_gcloud_diagnostic(self) -> None:
        original_run = RUNTIME_PREFLIGHT.subprocess.run
        RUNTIME_PREFLIGHT.subprocess.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RUNTIME_PREFLIGHT.subprocess.CalledProcessError(
                1, "gcloud", stderr="backend rejected access_token=should-not-appear"
            )
        )
        try:
            with self.assertRaises(RUNTIME_PREFLIGHT.RuntimePreflightError) as raised:
                RUNTIME_PREFLIGHT.load_current_service(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT.subprocess.run = original_run
        self.assertIn("access_token=[REDACTED]", str(raised.exception))
        self.assertNotIn("should-not-appear", str(raised.exception))

    def test_runtime_preflight_redacts_bearer_and_quoted_credentials(self) -> None:
        original_run = RUNTIME_PREFLIGHT.subprocess.run
        diagnostics = (
            ("Bearer ya29.standalone-secret-token", "standalone-secret-token"),
            ("Authorization: Bearer ya29.bearer-secret-token", "bearer-secret-token"),
            ('{"access_token": "ya29.quoted-secret"}', "ya29.quoted-secret"),
            ('{"authorization": "Bearer ya29.quoted-bearer"}', "ya29.quoted-bearer"),
        )
        try:
            for stderr, secret_fragment in diagnostics:
                with self.subTest(stderr=stderr):
                    RUNTIME_PREFLIGHT.subprocess.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        RUNTIME_PREFLIGHT.subprocess.CalledProcessError(1, "gcloud", stderr=stderr)
                    )
                    with self.assertRaises(RUNTIME_PREFLIGHT.RuntimePreflightError) as raised:
                        RUNTIME_PREFLIGHT.load_current_service(target=self.target(), project_id="fake-project")
                    self.assertNotIn(secret_fragment, str(raised.exception))
                    self.assertIn("[REDACTED]", str(raised.exception))
        finally:
            RUNTIME_PREFLIGHT.subprocess.run = original_run

    def test_runtime_preflight_rejects_secret_where_reviewed_runtime_config_will_be_applied(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["runtime_env_vars"] = {"FAKE_RUNTIME_CONFIG": "reviewed.example"}
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "FAKE_RUNTIME_CONFIG",
                                "valueSource": {"secretKeyRef": {"secret": "incorrect", "version": "latest"}},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(
            RUNTIME_PREFLIGHT.validate_current_bindings(self.target(), service),
            ["fake: runtime config FAKE_RUNTIME_CONFIG is a Secret Manager binding; expected a literal value"],
        )

    def test_personas_contract_reconciles_the_failed_live_runtime_bindings(self) -> None:
        # Static deployment-contract fixture: the handler must consume the
        # reviewed linkedin-api8 host for its documented profile-data endpoint
        # while the API key stays a runtime secret.
        contract = STATIC.load_contract(ROOT / "config" / "public-build-contract.json")
        personas = contract.targets["personas"]
        self.assertNotIn("LINKEDIN_API_HOST", personas.deployment.runtime_secrets)
        self.assertEqual(personas.deployment.runtime_secrets["LINKEDIN_API_KEY"], "NEXT_PUBLIC_LINKEDIN_API_KEY:latest")
        self.assertEqual(
            personas.deployment.runtime_env_vars,
            {
                "LINKEDIN_RAPIDAPI_HOST": "linkedin-api8.p.rapidapi.com",
            },
        )
        self.assertEqual(
            personas.deployment.preserve_runtime_secrets,
            ("REDIS_HOST", "REDIS_PASSWORD", "NEXT_PUBLIC_OMI_APP_ID", "NEXT_PUBLIC_OMI_API_KEY"),
        )
        self.assertEqual(
            personas.deployment.fallback_runtime_secrets,
            {
                "REDIS_HOST": "REDIS_HOST:latest",
                "REDIS_PASSWORD": "REDIS_PASSWORD:latest",
                "NEXT_PUBLIC_OMI_APP_ID": "NEXT_PUBLIC_OMI_APP_ID:latest",
                "NEXT_PUBLIC_OMI_API_KEY": "NEXT_PUBLIC_OMI_API_KEY:latest",
            },
        )
        self.assertEqual(
            personas.deployment.remove_runtime_secrets,
            (
                "LINKEDIN_API_HOST",
                "NEXT_PUBLIC_LINKEDIN_API_HOST",
                "NEXT_PUBLIC_FIREBASE_API_KEY",
                "NEXT_PUBLIC_FIREBASE_APP_ID",
                "NEXT_PUBLIC_FIREBASE_VAPID_KEY",
                "NEXT_PUBLIC_MIXPANEL_TOKEN",
                "NEXT_PUBLIC_RAPIDAPI_KEY",
                "NEXT_PUBLIC_RAPIDAPI_HOST",
                "NEXT_PUBLIC_LINKEDIN_API_KEY",
                "ANTHROPIC_API_KEY",
                "CLAUDE_API_KEY",
                "OPENAI_API_KEY",
                "OPENROUTER_API_KEY",
            ),
        )
        live_bindings = {
            name: {"valueSource": {"secretKeyRef": {"secret": reference.rsplit(":", 1)[0], "version": "latest"}}}
            for name, reference in personas.deployment.runtime_secrets.items()
        }
        live_bindings.update(
            {
                "REDIS_HOST": {"valueSource": {"secretKeyRef": {"secret": "legacy-redis-host", "version": "9"}}},
                "REDIS_PASSWORD": {
                    "valueSource": {"secretKeyRef": {"secret": "legacy-redis-password", "version": "4"}}
                },
                "NEXT_PUBLIC_OMI_APP_ID": {
                    "valueSource": {"secretKeyRef": {"secret": "legacy-app-id", "version": "2"}}
                },
                "NEXT_PUBLIC_OMI_API_KEY": {
                    "valueSource": {"secretKeyRef": {"secret": "legacy-api-key", "version": "6"}}
                },
                "LINKEDIN_API_HOST": {
                    "valueSource": {"secretKeyRef": {"secret": "NEXT_PUBLIC_LINKEDIN_API_HOST", "version": "latest"}}
                },
                **{
                    name: {"valueSource": {"secretKeyRef": {"secret": f"retired-{name.lower()}", "version": "latest"}}}
                    for name in personas.deployment.remove_runtime_secrets
                    if name != "LINKEDIN_API_HOST"
                },
            }
        )
        service = {
            "template": {
                "containers": [{"env": [{"name": name, **binding} for name, binding in live_bindings.items()]}]
            }
        }

        self.assertEqual(RUNTIME_PREFLIGHT.validate_current_bindings(personas, service), [])
        calls: list[list[str]] = []
        original = RUNTIME_PREFLIGHT._gcloud_json

        def enabled(arguments):
            calls.append(arguments)
            return {"state": "ENABLED"}

        RUNTIME_PREFLIGHT._gcloud_json = enabled
        try:
            self.assertEqual(RUNTIME_PREFLIGHT.validate_secret_versions(target=personas, project_id="fake-project"), [])
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original
        self.assertNotIn(
            "--secret=NEXT_PUBLIC_LINKEDIN_API_HOST",
            [argument for call in calls for argument in call],
        )
        route = (ROOT / "web/personas-open-source/src/app/api/social-profile/route.ts").read_text(encoding="utf-8")
        self.assertIn("process.env.LINKEDIN_RAPIDAPI_HOST", route)
        self.assertNotIn("process.env.LINKEDIN_API_HOST", route)
        self.assertIn("headers = rapidApiHeaders(linkedinApiKey, linkedinRapidApiHost);", route)
        self.assertIn(
            "https://${linkedinRapidApiHost}/profile-data-connection-count-posts?username=${encodeURIComponent(", route
        )
        readme = (ROOT / "web/personas-open-source/README.md").read_text(encoding="utf-8")
        self.assertIn("/rockapis-rockapis-default/api/linkedin-api8", readme)
        self.assertIn("LINKEDIN_RAPIDAPI_HOST=linkedin-api8.p.rapidapi.com", readme)

        personas_workflow = (ROOT / ".github/workflows/gcp_personas.yml").read_text(encoding="utf-8")
        self.assertIn("network: ${{ vars.CLOUD_RUN_VPC_NETWORK }}", personas_workflow)
        self.assertIn("subnet: ${{ vars.CLOUD_RUN_VPC_SUBNET }}", personas_workflow)
        self.assertIn(
            "runtime_env_vars: OMI_LLM_GATEWAY_URL=${{ vars.OMI_LLM_GATEWAY_URL }}",
            personas_workflow,
        )
        self.assertIn("require_gateway_url: true", personas_workflow)

    def test_rejects_a_required_value_missing_from_reviewed_source(self) -> None:
        contract = STATIC.load_contract(self.root / "config/public-build-contract.json")
        values = STATIC.parse_values_document(fixture_values(value=""), source="fixture")

        self.assertEqual(
            STATIC.validate_values(contract, values, contract.targets.values(), "prod"),
            ["fake: required input FAKE_PUBLIC_INPUT is missing or empty in prod"],
        )

    def test_preflight_blocks_an_absent_newly_referenced_input_before_build(self) -> None:
        original = PREFLIGHT.request_remote_values
        PREFLIGHT.request_remote_values = lambda **_kwargs: STATIC.parse_values_document(
            fixture_values(value=""), source="fixture"
        )
        try:
            result = PREFLIGHT.main(
                [
                    "--target",
                    "fake",
                    "--environment",
                    "prod",
                    "--repository",
                    "owner/repo",
                    "--ref",
                    "deadbeef",
                    "--token",
                    "token",
                    "--contract",
                    str(self.root / "config/public-build-contract.json"),
                ]
            )
        finally:
            PREFLIGHT.request_remote_values = original

        self.assertEqual(result, 1)

    def test_rejects_workflow_variable_bypass(self) -> None:
        self.write(
            ".github/workflows/gcp_fake.yml",
            (self.root / ".github/workflows/gcp_fake.yml").read_text(encoding="utf-8")
            + "FAKE_PUBLIC_INPUT=${{ vars.FAKE_PUBLIC_INPUT }}\n",
        )

        self.assertIn("bypasses repository_config", "\n".join(self.errors()))

    def test_rejects_missing_client_canary(self) -> None:
        self.write("web/fake/public-build-canary.tsx", "<span />\n")

        self.assertIn("must expose fake browser canary", "\n".join(self.errors()))

    def test_remote_preflight_decodes_reviewed_configuration_without_printing_values(self) -> None:
        remote = json.dumps(fixture_values()).encode("utf-8")

        class Response:
            def read(self) -> bytes:
                return json.dumps({"encoding": "base64", "content": base64.b64encode(remote).decode("ascii")}).encode(
                    "utf-8"
                )

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

        original = PREFLIGHT.urllib.request.urlopen
        PREFLIGHT.urllib.request.urlopen = lambda *_args, **_kwargs: Response()
        try:
            values = PREFLIGHT.request_remote_values(
                repository="owner/repo", ref="deadbeef", config_path="config/public-build-values.json", token="token"
            )
        finally:
            PREFLIGHT.urllib.request.urlopen = original

        self.assertEqual(values["prod"]["FAKE_PUBLIC_INPUT"], "configured")

    def test_browser_smoke_requires_the_ready_marker(self) -> None:
        original = SMOKE.render_candidate
        SMOKE.render_candidate = lambda **_kwargs: '<span data-omi-public-build-canary="fake:ready" />'
        try:
            SMOKE.smoke(
                target="fake",
                base_url="https://candidate.example",
                contract_path=self.root / "config/public-build-contract.json",
                environment={"OMI_BROWSER_BIN": "fake-browser"},
            )
        finally:
            SMOKE.render_candidate = original

        self.assertTrue(True)

    def test_browser_smoke_prints_a_sanitized_reason(self) -> None:
        original = SMOKE.smoke

        def fail_smoke(**_kwargs) -> None:
            raise SMOKE.BrowserSmokeError("client public-build canary did not become ready")

        SMOKE.smoke = fail_smoke
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                result = SMOKE.main(["--target", "fake", "--base-url", "https://candidate.example"])
        finally:
            SMOKE.smoke = original

        self.assertEqual(result, 1)
        self.assertIn("reason=client public-build canary did not become ready", stderr.getvalue())
        self.assertEqual(
            SMOKE.sanitized_browser_smoke_reason(SMOKE.BrowserSmokeError("secret=not-for-logs")),
            "unspecified browser smoke failure",
        )

    def test_acceptance_command_renders_sha_placeholder(self) -> None:
        command = (
            "python3",
            ".github/scripts/smoke_public_build_browser.py",
            "--target",
            "frontend",
            "--base-url",
            "{base_url}",
            "--expect-sha",
            "{sha}",
        )
        self.assertEqual(
            STATIC.render_acceptance_command(
                command,
                base_url="https://h.omi.me",
                sha="deadbeefcafebabe",
            ),
            (
                "python3",
                ".github/scripts/smoke_public_build_browser.py",
                "--target",
                "frontend",
                "--base-url",
                "https://h.omi.me",
                "--expect-sha",
                "deadbeefcafebabe",
            ),
        )
        without_sha = command[:-2]
        self.assertEqual(
            STATIC.render_acceptance_command(without_sha, base_url="https://h.omi.me", sha="ignored"),
            without_sha[:5] + ("https://h.omi.me",),
        )

    def test_acceptance_document_matches_marker_and_sha(self) -> None:
        document = (
            '<span data-omi-public-build-canary="frontend:ready" ' 'data-omi-public-build-sha="abc123" hidden></span>'
        )
        self.assertTrue(SMOKE.acceptance_document_matches(document, marker="frontend:ready"))
        self.assertTrue(SMOKE.acceptance_document_matches(document, marker="frontend:ready", expect_sha="abc123"))
        self.assertFalse(SMOKE.acceptance_document_matches(document, marker="frontend:ready", expect_sha="other"))
        self.assertFalse(
            SMOKE.acceptance_document_matches(
                '<span data-omi-public-build-canary="frontend:pending" data-omi-public-build-sha="abc123">',
                marker="frontend:ready",
                expect_sha="abc123",
            )
        )

    def test_browser_smoke_rejects_a_mismatched_sha_and_accepts_a_matching_one(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["candidate_acceptance"]["command"].extend(["--expect-sha", "{sha}"])
        self.write_json("config/public-build-contract.json", contract)
        original = SMOKE.render_candidate
        SMOKE.render_candidate = (
            lambda **_kwargs: '<span data-omi-public-build-canary="fake:ready" data-omi-public-build-sha="aaaa" />'
        )
        try:
            with self.assertRaises(SMOKE.BrowserSmokeError) as caught:
                SMOKE.smoke(
                    target="fake",
                    base_url="https://candidate.example",
                    contract_path=self.root / "config/public-build-contract.json",
                    environment={"OMI_BROWSER_BIN": "fake-browser"},
                    expect_sha="bbbb",
                )
            self.assertEqual(str(caught.exception), "client public-build sha did not match")
            SMOKE.smoke(
                target="fake",
                base_url="https://candidate.example",
                contract_path=self.root / "config/public-build-contract.json",
                environment={"OMI_BROWSER_BIN": "fake-browser"},
                expect_sha="aaaa",
            )
        finally:
            SMOKE.render_candidate = original
        self.assertIn("client public-build sha did not match", SMOKE.SAFE_BROWSER_SMOKE_REASONS)


class AcceptanceRouteFixture(unittest.TestCase):
    """Restricted ingress hides the tagged candidate URL; the route must say so."""

    RESTRICTED = "internal-and-cloud-load-balancing"

    def load(self, contract: dict):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "public-build-contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            return STATIC.load_contract(path)

    def with_public_urls(self, public_urls: dict) -> dict:
        contract = fixture_contract()
        contract["targets"]["fake"]["candidate_acceptance"]["public_urls"] = public_urls
        return contract

    def test_open_ingress_smokes_the_tagged_candidate(self) -> None:
        target = self.load(fixture_contract()).targets["fake"]
        for ingress in ("", "all", " all "):
            route = STATIC.acceptance_route(target, environment="prod", ingress=ingress)
            self.assertEqual(route, STATIC.AcceptanceRoute(route="candidate_url", public_url=""))

    def test_restricted_ingress_uses_the_declared_public_url(self) -> None:
        target = self.load(self.with_public_urls({"prod": "https://fake.example"})).targets["fake"]
        route = STATIC.acceptance_route(target, environment="prod", ingress=self.RESTRICTED)
        self.assertEqual(route, STATIC.AcceptanceRoute(route="public_url", public_url="https://fake.example"))

    def test_restricted_ingress_without_a_public_url_names_the_ingress(self) -> None:
        target = self.load(self.with_public_urls({"prod": "https://fake.example"})).targets["fake"]
        with self.assertRaises(ValueError) as caught:
            STATIC.acceptance_route(target, environment="development", ingress=self.RESTRICTED)
        self.assertIn(self.RESTRICTED, str(caught.exception))
        self.assertIn("development", str(caught.exception))

    def test_public_urls_must_be_https_for_known_environments(self) -> None:
        for public_urls in (
            {"staging": "https://fake.example"},
            {"prod": "http://fake.example"},
            {"prod": "https://fake.example/"},
            ["https://fake.example"],
        ):
            with self.subTest(public_urls=public_urls):
                with self.assertRaises(ValueError):
                    self.load(self.with_public_urls(public_urls))

    def test_serving_revision_prefers_the_largest_traffic_share(self) -> None:
        document = {
            "status": {
                "traffic": [
                    {"revisionName": "svc-old", "percent": 30},
                    {"revisionName": "svc-live", "percent": 70},
                    {"revisionName": "svc-candidate", "tag": "public-x", "percent": 0},
                    {"latestRevision": True},
                ]
            }
        }
        self.assertEqual(STATIC.serving_revision(document), "svc-live")
        self.assertEqual(STATIC.serving_revision({"status": {"traffic": []}}), "")
        self.assertEqual(STATIC.serving_revision({}), "")

    def test_shipped_frontend_contract_declares_its_balancer_hostname(self) -> None:
        # h.omi.me fronts the `frontend` service, whose contract restricts ingress
        # to the balancer; without this URL no prod frontend candidate can ever be accepted.
        target = STATIC.load_contract(STATIC.DEFAULT_CONTRACT).targets["frontend"]
        self.assertEqual(
            target.deployment.flags_for("prod"),
            ("--ingress=internal-and-cloud-load-balancing",),
        )
        self.assertEqual(target.deployment.flags_for("development"), ())
        self.assertEqual(target.deployment.remove_runtime_env_vars, ("OPENAI_API_KEY",))
        self.assertEqual(target.deployment.runtime_secrets["DD_API_KEY"], "DD_API_KEY:latest")
        self.assertEqual(target.candidate_acceptance.public_urls.get("prod"), "https://h.omi.me")

    def test_shipped_frontend_contract_declares_expect_sha(self) -> None:
        target = STATIC.load_contract(STATIC.DEFAULT_CONTRACT).targets["frontend"]
        self.assertIn("--expect-sha", target.candidate_acceptance.command)
        self.assertIn("{sha}", target.candidate_acceptance.command)
        self.assertEqual(
            STATIC.render_acceptance_command(
                target.candidate_acceptance.command,
                base_url="https://h.omi.me",
                sha="0123456789abcdef0123456789abcdef01234567",
            )[-2:],
            ("--expect-sha", "0123456789abcdef0123456789abcdef01234567"),
        )


class RuntimeServiceAccountPreflightTests(unittest.TestCase):
    SA = "frontend-invoker@fake-project.iam.gserviceaccount.com"

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="omi-public-build-sa-")
        self.root = Path(self.temp_dir.name)
        contract_path = self.root / "config/public-build-contract.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(json.dumps(fixture_contract()), encoding="utf-8")
        self.target = STATIC.load_contract(contract_path).targets["fake"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _stub_describe(self, *, describe):
        original = RUNTIME_PREFLIGHT._gcloud_json

        def fake_gcloud(arguments):
            if arguments[:3] == ["iam", "service-accounts", "describe"]:
                return describe(arguments)
            raise AssertionError(arguments)

        RUNTIME_PREFLIGHT._gcloud_json = fake_gcloud
        return original

    def test_skips_service_account_checks_when_none_is_supplied(self) -> None:
        self.assertEqual(RUNTIME_PREFLIGHT.validate_service_account(service_account="", project_id="fake-project"), [])

    def test_runtime_preflight_accepts_an_existing_service_account_the_deployer_can_act_as(self) -> None:
        describe_calls: list[list[str]] = []
        iam_calls: list[dict] = []
        original_gcloud = self._stub_describe(
            describe=lambda arguments: describe_calls.append(list(arguments)) or {"email": self.SA}
        )
        original_iam = RUNTIME_PREFLIGHT._test_service_account_iam_permissions

        def fake_iam(**kwargs):
            iam_calls.append(kwargs)
            return {"permissions": ["iam.serviceAccounts.actAs"]}

        RUNTIME_PREFLIGHT._test_service_account_iam_permissions = fake_iam
        try:
            self.assertEqual(
                RUNTIME_PREFLIGHT.validate_service_account(service_account=self.SA, project_id="fake-project"),
                [],
            )
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original_gcloud
            RUNTIME_PREFLIGHT._test_service_account_iam_permissions = original_iam

        self.assertEqual(describe_calls[0][:4], ["iam", "service-accounts", "describe", self.SA])
        self.assertEqual(iam_calls[0]["service_account"], self.SA)
        self.assertEqual(iam_calls[0]["project_id"], "fake-project")
        self.assertEqual(iam_calls[0]["permissions"], ("iam.serviceAccounts.actAs",))

    def test_runtime_preflight_rejects_a_missing_service_account(self) -> None:
        original_gcloud = RUNTIME_PREFLIGHT._gcloud_json
        original_iam = RUNTIME_PREFLIGHT._test_service_account_iam_permissions
        iam_called = False

        def missing(_arguments):
            raise RUNTIME_PREFLIGHT.RuntimePreflightError("resource not found", category="not_found")

        def fake_iam(**_kwargs):
            nonlocal iam_called
            iam_called = True
            raise AssertionError("testIamPermissions must not run when describe fails")

        RUNTIME_PREFLIGHT._gcloud_json = missing
        RUNTIME_PREFLIGHT._test_service_account_iam_permissions = fake_iam
        try:
            errors = RUNTIME_PREFLIGHT.validate_service_account(service_account=self.SA, project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original_gcloud
            RUNTIME_PREFLIGHT._test_service_account_iam_permissions = original_iam

        self.assertFalse(iam_called)
        self.assertEqual(len(errors), 1)
        self.assertIn(self.SA, errors[0])
        self.assertIn("does not exist", errors[0])

    def test_runtime_preflight_rejects_missing_act_as_permission(self) -> None:
        original_gcloud = self._stub_describe(describe=lambda _arguments: {"email": self.SA})
        original_iam = RUNTIME_PREFLIGHT._test_service_account_iam_permissions

        def fake_iam(**_kwargs):
            return {}

        RUNTIME_PREFLIGHT._test_service_account_iam_permissions = fake_iam
        try:
            errors = RUNTIME_PREFLIGHT.validate_service_account(service_account=self.SA, project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original_gcloud
            RUNTIME_PREFLIGHT._test_service_account_iam_permissions = original_iam

        self.assertEqual(
            errors,
            [f"{self.SA}: deployer is missing permission iam.serviceAccounts.actAs"],
        )

    def test_runtime_preflight_rejects_act_as_probe_http_failure(self) -> None:
        original_gcloud = self._stub_describe(describe=lambda _arguments: {"email": self.SA})
        original_iam = RUNTIME_PREFLIGHT._test_service_account_iam_permissions

        def fake_iam(**_kwargs):
            raise RUNTIME_PREFLIGHT.RuntimePreflightError("IAM testIamPermissions HTTP 401", category="unknown")

        RUNTIME_PREFLIGHT._test_service_account_iam_permissions = fake_iam
        try:
            errors = RUNTIME_PREFLIGHT.validate_service_account(service_account=self.SA, project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT._gcloud_json = original_gcloud
            RUNTIME_PREFLIGHT._test_service_account_iam_permissions = original_iam

        self.assertEqual(len(errors), 1)
        self.assertIn(self.SA, errors[0])
        self.assertIn("cannot test iam.serviceAccounts.actAs", errors[0])
        self.assertIn("HTTP 401", errors[0])

    def test_test_iam_permissions_posts_to_iam_rest_without_exposing_the_token(self) -> None:
        token = "super-secret-token-value"
        captured: dict[str, object] = {}
        original_token = RUNTIME_PREFLIGHT._gcloud_access_token
        original_urlopen = RUNTIME_PREFLIGHT.urllib.request.urlopen

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"permissions":["iam.serviceAccounts.actAs"]}'

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["body"] = request.data
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse()

        RUNTIME_PREFLIGHT._gcloud_access_token = lambda: token
        RUNTIME_PREFLIGHT.urllib.request.urlopen = fake_urlopen
        try:
            result = RUNTIME_PREFLIGHT._test_service_account_iam_permissions(
                service_account=self.SA,
                project_id="fake-project",
                permissions=("iam.serviceAccounts.actAs",),
            )
        finally:
            RUNTIME_PREFLIGHT._gcloud_access_token = original_token
            RUNTIME_PREFLIGHT.urllib.request.urlopen = original_urlopen

        self.assertEqual(result, {"permissions": ["iam.serviceAccounts.actAs"]})
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["timeout"], 30)
        self.assertEqual(
            captured["url"],
            "https://iam.googleapis.com/v1/projects/fake-project/serviceAccounts/"
            "frontend-invoker%40fake-project.iam.gserviceaccount.com:testIamPermissions",
        )
        self.assertEqual(json.loads(captured["body"]), {"permissions": ["iam.serviceAccounts.actAs"]})
        self.assertEqual(captured["authorization"], f"Bearer {token}")
        self.assertNotIn(token, captured["url"])

    def test_test_iam_permissions_token_failure_does_not_call_http(self) -> None:
        original_token = RUNTIME_PREFLIGHT._gcloud_access_token
        original_urlopen = RUNTIME_PREFLIGHT.urllib.request.urlopen
        http_called = False

        def fake_token():
            raise RUNTIME_PREFLIGHT.RuntimePreflightError(
                "gcloud auth print-access-token failed",
                category="unauthenticated",
            )

        def fake_urlopen(*_args, **_kwargs):
            nonlocal http_called
            http_called = True
            raise AssertionError("must not HTTP after token failure")

        RUNTIME_PREFLIGHT._gcloud_access_token = fake_token
        RUNTIME_PREFLIGHT.urllib.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(RUNTIME_PREFLIGHT.RuntimePreflightError) as caught:
                RUNTIME_PREFLIGHT._test_service_account_iam_permissions(
                    service_account=self.SA,
                    project_id="fake-project",
                    permissions=("iam.serviceAccounts.actAs",),
                )
        finally:
            RUNTIME_PREFLIGHT._gcloud_access_token = original_token
            RUNTIME_PREFLIGHT.urllib.request.urlopen = original_urlopen

        self.assertFalse(http_called)
        self.assertIn("print-access-token failed", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
