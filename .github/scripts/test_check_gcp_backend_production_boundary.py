#!/usr/bin/env python3
"""Mutation tests for the rollback-first Cloud Run-only production boundary."""

from __future__ import annotations

import importlib.util
from itertools import takewhile
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import re
import tempfile
import textwrap
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".github" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from workflow_composite_contract import backend_deploy_contract_text

UPDATES_SOURCE = (ROOT / "backend/routers/updates.py").read_text(encoding="utf-8")

MODULE_PATH = ROOT / ".github/scripts/check-gcp-backend-production-boundary.py"
SPEC = importlib.util.spec_from_file_location("check_gcp_backend_production_boundary", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class GcpBackendProductionBoundaryTests(unittest.TestCase):
    def test_all_service_production_smoke_requires_completed_http_401(self) -> None:
        composite = (ROOT / CHECKER.DEPLOY_BACKEND_STACK_ACTION).read_text(encoding="utf-8")
        smoke = composite.split(f"- name: {CHECKER.PROD_SMOKE}\n", 1)[1].split("\n    - name: ", 1)[0]
        script = textwrap.dedent(smoke.split("\n      run: |\n", 1)[1])
        cases = {
            "unauthorized": ("401", 0, 0, ["POST"]),
            "timeout_after_headers": ("401", 28, 28, []),
            "unexpected_response": ("403", 0, 1, []),
        }
        for scenario, (http_status, curl_exit, smoke_exit, expected_calls) in cases.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                curl = root / "curl"
                curl.write_text(
                    '#!/bin/sh\ncase " $* " in *" --connect-timeout 5 --max-time 10 "*) ;; *) exit 2 ;; esac\n'
                    'printf "%s" "$FIXTURE_HTTP_STATUS"\nexit "$FIXTURE_CURL_EXIT"\n',
                    encoding="utf-8",
                )
                curl.chmod(0o700)
                (root / "firebase_release_probe_token.py").write_text(
                    "import sys\nfrom pathlib import Path\nPath(sys.argv[-1]).touch()\n",
                    encoding="utf-8",
                )
                (root / "transcription_capability_probe.py").write_text(
                    textwrap.dedent("""\
                        import os
                        from pathlib import Path
                        import sys

                        root = Path(os.environ["RUNNER_TEMP"])
                        token_file = root / "firebase-production-serving-token"
                        assert token_file.exists()
                        assert sys.argv[1:] == [
                            "--candidate-api-url", "https://api.omi.me",
                            "--bearer-token-file", str(token_file), "--json-only",
                        ]
                        with (root / "calls").open("a") as stream:
                            stream.write("POST\\n")
                        """),
                    encoding="utf-8",
                )
                env = {
                    **os.environ,
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "RUNNER_TEMP": directory,
                    "DEPLOY_CONTROL_SCRIPTS": directory,
                    "PROBE_SECRET_PROJECT": "fixture",
                    "FIREBASE_AUTH_PROJECT_ID": "fixture",
                    "SMOKE_CLOUD_RUN_SERVICE": "all",
                    "FIXTURE_HTTP_STATUS": http_status,
                    "FIXTURE_CURL_EXIT": str(curl_exit),
                }
                result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, smoke_exit, result.stderr)
                calls = root / "calls"
                self.assertEqual(calls.read_text().splitlines() if calls.exists() else [], expected_calls)
                self.assertFalse((root / "firebase-production-serving-token").exists())

        rollback = composite.split("    - name: Restore Cloud Run traffic snapshot after failed promotion")[-1]
        rollback_condition = rollback.split("\n      shell:", 1)[0]
        self.assertIn("inputs.deploy_profile == 'manual' && (failure() || cancelled())", rollback_condition)
        self.assertIn(CHECKER.ROLLBACK_CONDITION, rollback_condition)

    def test_selected_production_smoke_retries_only_before_an_http_response(self) -> None:
        composite = (ROOT / CHECKER.DEPLOY_BACKEND_STACK_ACTION).read_text(encoding="utf-8")
        smoke = composite.split(f"- name: {CHECKER.PROD_SMOKE}\n", 1)[1].split("\n    - name: ", 1)[0]
        run_block = smoke.split("\n      run: |\n", 1)[1]
        # Stop at the end of the YAML block, before any step-level comments.
        run_lines = takewhile(lambda line: not line.strip() or line.startswith("        "), run_block.splitlines(True))
        script = textwrap.dedent("".join(run_lines))
        cases = {
            "pass": (0, 1),
            "transport_then_pass": (0, 2),
            "persistent_transport": (1, 2),
            "hard_failure": (1, 1),
            "body_timeout": (1, 1),
            "reservation_rejected": (1, 0),
            "deadline": (1, 0),
            "cancel_during_delay": (143, 1),
        }
        for scenario, (exit_code, attempts) in cases.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                curl = root / "curl"
                curl.write_text(
                    '#!/bin/sh\ncase " $* " in *" --connect-timeout 5 --max-time 10 "*) ;; *) exit 2 ;; esac\n'
                    'if [ "$SCENARIO" = reservation_rejected ]; then printf 403; else printf 401; fi\n',
                    encoding="utf-8",
                )
                curl.chmod(0o700)
                (root / "firebase_release_probe_token.py").write_text(
                    "import sys\nfrom pathlib import Path\nPath(sys.argv[-1]).touch()\n",
                    encoding="utf-8",
                )
                (root / "transcription_capability_probe.py").write_text(
                    textwrap.dedent("""\
                        import os
                        import json
                        from pathlib import Path
                        import sys
                        import time

                        scenario = os.environ["SCENARIO"]
                        assert sys.argv[-4:] == ["--timeout-seconds", "30", "--no-redirects", "--json-only"]
                        calls = Path(os.environ["RUNNER_TEMP"]) / "calls"
                        with calls.open("a") as stream:
                            stream.write("POST\\n")
                        attempts = len(calls.read_text().splitlines())
                        if scenario == "deadline":
                            time.sleep(20)
                        passed = scenario == "pass" or (scenario == "transport_then_pass" and attempts == 2)
                        details = {"error_kind": "network_error"}
                        if scenario == "hard_failure":
                            details = {"http_status": 200, "phrase_match": False}
                        if scenario == "body_timeout":
                            details["http_status"] = 200
                        print(json.dumps({"status": "PASS" if passed else "FAIL", "checks": [{"details": details}]}))
                        sys.exit(0 if passed else 1)
                        """),
                    encoding="utf-8",
                )
                env = {
                    **os.environ,
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "RUNNER_TEMP": directory,
                    "DEPLOY_CONTROL_SCRIPTS": directory,
                    "PROBE_SECRET_PROJECT": "fixture",
                    "FIREBASE_AUTH_PROJECT_ID": "fixture",
                    "SMOKE_CLOUD_RUN_SERVICE": "backend",
                    "SCENARIO": scenario,
                }
                attempt_script = script
                if scenario == "deadline":
                    self.assertIn("deadline = time.monotonic() + 65", script)
                    attempt_script = script.replace("deadline = time.monotonic() + 65", "deadline = time.monotonic() + 1")
                command = ["bash", "-c", attempt_script]
                if scenario == "cancel_during_delay":
                    log = root / "smoke.log"
                    with log.open("w") as stdout, subprocess.Popen(command, env=env, stdout=stdout) as process:
                        wait_until = time.monotonic() + 4
                        while "Retrying transcription smoke in 5 seconds" not in log.read_text():
                            self.assertLess(time.monotonic(), wait_until, "retry delay never started")
                            time.sleep(0.02)
                        process.terminate()
                        self.assertEqual(process.wait(timeout=2), exit_code)
                    output = log.read_text()
                else:
                    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    output = result.stdout
                reports = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
                self.assertEqual([report["attempt"] for report in reports], list(range(1, attempts + 1)))
                calls = root / "calls"
                expected_calls = 1 if scenario == "deadline" else attempts
                self.assertEqual(len(calls.read_text().splitlines()) if calls.exists() else 0, expected_calls)
                self.assertFalse((root / "firebase-production-serving-token").exists())

        rollback = composite.split("    - name: Restore Cloud Run traffic snapshot after failed promotion")[-1]
        self.assertIn("steps.smoke-promoted-production-serving-api.outcome == 'cancelled'", rollback)

    def stage_contract(self, root: Path) -> None:
        workflow_path = root / CHECKER.WORKFLOW
        composite_path = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        composite_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / CHECKER.WORKFLOW, workflow_path)
        shutil.copy2(ROOT / CHECKER.DEPLOY_BACKEND_STACK_ACTION, composite_path)

    def mutate_contract(self, root: Path, expected: str, replacement: str) -> None:
        workflow_path = root / CHECKER.WORKFLOW
        composite_path = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
        workflow = workflow_path.read_text(encoding="utf-8")
        composite = composite_path.read_text(encoding="utf-8")
        contract = backend_deploy_contract_text(workflow, root, CHECKER.DEPLOY_BACKEND_STACK_ACTION)
        self.assertIn(expected, contract)
        if expected in workflow:
            workflow_path.write_text(workflow.replace(expected, replacement, 1), encoding="utf-8")
        else:
            composite_path.write_text(composite.replace(expected, replacement, 1), encoding="utf-8")

    def test_current_workflow_preserves_the_rollback_first_cloud_run_only_boundary(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_production_reservation_smoke_uses_a_schema_valid_inert_tag(self) -> None:
        workflow = (ROOT / CHECKER.WORKFLOW).read_text(encoding="utf-8")
        contract = backend_deploy_contract_text(workflow, ROOT, CHECKER.DEPLOY_BACKEND_STACK_ACTION)
        smoke = contract[contract.index(CHECKER.PROD_SMOKE) :]
        match = re.search(r'''--data '\{"tag":"(?P<tag>[^"]+)"\}'\)''', smoke)
        if match is None:
            self.fail("production reservation smoke must send an exact tag body")

        schema = re.search(
            r'class BetaCandidatePromotionRequest\(BaseModel\):.*?tag: str = Field\(pattern=r"(?P<pattern>[^"]+)"\)',
            UPDATES_SOURCE,
            re.DOTALL,
        )
        if schema is None:
            self.fail("Beta candidate tag schema must remain statically inspectable")
        self.assertRegex(match.group("tag"), re.compile(schema.group("pattern")))

        reserve = UPDATES_SOURCE[
            UPDATES_SOURCE.index("async def reserve_beta_candidate_endpoint(") : UPDATES_SOURCE.index(
                '@router.put("/v2/desktop/beta/admission")'
            )
        ]
        self.assertIn("if not _has_beta_promotion_authorization(authorization):", reserve)
        self.assertIn('raise HTTPException(status_code=401, detail="Unauthorized")', reserve)

    def test_rejects_production_boundary_regressions(self) -> None:
        mutations = {
            "defaults_to_all": ("default: 'cloud-run-only'", "default: 'all'"),
            "permits_prod_all": (CHECKER.PROD_ALL_REJECTION, "if false; then"),
            "reintroduces_tagged_url": (
                "inputs.deploy_profile == 'manual' && inputs.environment == 'development'",
                "inputs.deploy_profile == 'manual' && inputs.environment == 'prod'",
            ),
            "moves_smoke_before_serving_verification": (CHECKER.PROD_SMOKE, "Smoke production candidate API"),
            "omits_schema_valid_unauthenticated_smoke": (
                "schema-valid inert tag reaches the authorization wall",
                "unexpected response",
            ),
            "uses_invalid_empty_reservation_body": (
                '--data \'{"tag":"v0.0.0+1-macos"}\'',
                "--data '{}')",
            ),
            "omits_smoke_rollback": (CHECKER.ROLLBACK_CONDITION, "false"),
            "leaks_smoke_token_to_output": (
                "trap 'rm -f \"$token_file\"' EXIT",
                "trap 'rm -f \"$token_file\"' EXIT\n          echo firebase-production-serving-token >> \"$GITHUB_OUTPUT\"",
            ),
        }
        for name, (expected, replacement) in mutations.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.stage_contract(root)
                self.mutate_contract(root, expected, replacement)
                self.assertTrue(CHECKER.validate(root))

    def test_commented_composite_reference_does_not_expand_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.stage_contract(root)
            workflow_path = root / CHECKER.WORKFLOW
            composite_path = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8").replace(
                    "        uses: ./.github/actions/deploy-backend-stack",
                    "        # uses: ./.github/actions/deploy-backend-stack",
                ),
                encoding="utf-8",
            )
            composite_path.write_text(
                composite_path.read_text(encoding="utf-8").replace(
                    CHECKER.PROD_ALL_REJECTION,
                    "if false; then",
                ),
                encoding="utf-8",
            )
            self.assertTrue(CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()
