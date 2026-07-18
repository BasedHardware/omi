#!/usr/bin/env python3
"""Fixtures for the public-build contract, source preflight, and browser smoke."""

from __future__ import annotations

import base64
import importlib.util
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
            """steps:
  - uses: ./.github/actions/deploy-public-build
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
                    self.write_json("config/public-build-contract.json", contract)

                    with self.assertRaisesRegex(ValueError, "runtime binding groups cannot overlap"):
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
                                "valueSource": {"secretKeyRef": {"name": "FAKE_RUNTIME_SECRET", "key": "latest"}},
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
                                "valueSource": {"secretKeyRef": {"name": "stale-secret", "key": "latest"}},
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
                                "valueSource": {"secretKeyRef": {"name": "stale-secret", "key": "latest"}},
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
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "PRESERVED_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"name": "legacy-secret", "key": "7"}},
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
        self.write_json("config/public-build-contract.json", contract)
        service = {
            "template": {
                "containers": [
                    {
                        "env": [
                            {
                                "name": "PRESERVED_RUNTIME_SECRET",
                                "valueSource": {"secretKeyRef": {"name": "legacy-secret", "key": "7"}},
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

    def test_runtime_preflight_requires_a_live_service_to_preserve_secret_bindings(self) -> None:
        contract = fixture_contract()
        contract["targets"]["fake"]["deployment"]["preserve_runtime_secrets"] = ["PRESERVED_RUNTIME_SECRET"]
        self.write_json("config/public-build-contract.json", contract)
        original_validate = RUNTIME_PREFLIGHT.validate_secret_versions
        original_load = RUNTIME_PREFLIGHT.load_current_service
        RUNTIME_PREFLIGHT.validate_secret_versions = lambda **_kwargs: []
        RUNTIME_PREFLIGHT.load_current_service = lambda **_kwargs: None
        try:
            errors = RUNTIME_PREFLIGHT.preflight(target=self.target(), project_id="fake-project")
        finally:
            RUNTIME_PREFLIGHT.validate_secret_versions = original_validate
            RUNTIME_PREFLIGHT.load_current_service = original_load

        self.assertEqual(
            errors,
            ["fake: cannot preserve runtime secrets because current Cloud Run service fake-service is absent"],
        )

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
                                "valueSource": {"secretKeyRef": {"name": "incorrect", "key": "latest"}},
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
            {"LINKEDIN_RAPIDAPI_HOST": "linkedin-api8.p.rapidapi.com"},
        )
        self.assertEqual(
            personas.deployment.preserve_runtime_secrets,
            ("REDIS_HOST", "REDIS_PASSWORD", "NEXT_PUBLIC_OMI_APP_ID", "NEXT_PUBLIC_OMI_API_KEY"),
        )
        self.assertEqual(
            personas.deployment.remove_runtime_secrets,
            (
                "LINKEDIN_API_HOST",
                "NEXT_PUBLIC_FIREBASE_API_KEY",
                "NEXT_PUBLIC_FIREBASE_APP_ID",
                "NEXT_PUBLIC_FIREBASE_VAPID_KEY",
                "NEXT_PUBLIC_MIXPANEL_TOKEN",
                "NEXT_PUBLIC_RAPIDAPI_KEY",
                "NEXT_PUBLIC_RAPIDAPI_HOST",
                "NEXT_PUBLIC_LINKEDIN_API_KEY",
                "CLAUDE_API_KEY",
            ),
        )
        live_bindings = {
            name: {"valueSource": {"secretKeyRef": {"name": reference.rsplit(":", 1)[0], "key": "latest"}}}
            for name, reference in personas.deployment.runtime_secrets.items()
        }
        live_bindings.update(
            {
                "REDIS_HOST": {"valueSource": {"secretKeyRef": {"name": "legacy-redis-host", "key": "9"}}},
                "REDIS_PASSWORD": {"valueSource": {"secretKeyRef": {"name": "legacy-redis-password", "key": "4"}}},
                "NEXT_PUBLIC_OMI_APP_ID": {"valueSource": {"secretKeyRef": {"name": "legacy-app-id", "key": "2"}}},
                "NEXT_PUBLIC_OMI_API_KEY": {"valueSource": {"secretKeyRef": {"name": "legacy-api-key", "key": "6"}}},
                "LINKEDIN_API_HOST": {
                    "valueSource": {"secretKeyRef": {"name": "NEXT_PUBLIC_LINKEDIN_API_HOST", "key": "latest"}}
                },
                **{
                    name: {"valueSource": {"secretKeyRef": {"name": f"retired-{name.lower()}", "key": "latest"}}}
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


if __name__ == "__main__":
    unittest.main()
