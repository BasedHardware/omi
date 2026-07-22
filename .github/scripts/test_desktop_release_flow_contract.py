#!/usr/bin/env python3
"""Static release-control contract for the one-path desktop operator model."""

# omi-test-quality: source-inspection -- static contract: GitHub workflow authority is YAML-only.
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GITLINK_RELATIVE = Path("omiGlass/firmware/.pio/libdeps/seeed_xiao_esp32s3/libopus")
PRECLEAN_NAME = "Remove stale uninitialized PlatformIO gitlink"
POSTCLEAN_NAME = "Remove regenerated uninitialized PlatformIO gitlink before checkout post-action"


def workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def codemagic() -> str:
    return (ROOT / "codemagic.yaml").read_text(encoding="utf-8")


class DesktopReleaseFlowContractTests(unittest.TestCase):
    def _qualification_identity_expressions(self) -> tuple[str, str]:
        qualification = workflow("desktop_qualify_beta.yml")
        candidate_step = qualification.split("      - name: Download and validate newest candidate evidence", 1)[1]
        candidate_step = candidate_step.split("\n      - name:", 1)[0]
        target = re.search(r"^\s*TARGET_SHA=\$\((.+)\)$", candidate_step, re.MULTILINE)
        checkout = re.search(r"^\s*CHECKOUT_SHA=\$\((.+)\)$", candidate_step, re.MULTILINE)
        self.assertIsNotNone(target)
        self.assertIsNotNone(checkout)
        return target.group(1), checkout.group(1)

    def _qualification_step(self, name: str) -> str:
        qualification = workflow("desktop_qualify_beta.yml")
        marker = f"      - name: {name}"
        self.assertEqual(qualification.count(marker), 1)
        return qualification.split(marker, 1)[1].split("\n      - name:", 1)[0]

    def _gitlink_cleanup_script(self, name: str) -> str:
        script = self._qualification_step(name).split("        run: |\n", 1)[1]
        return "\n".join(line[10:] if line.startswith("          ") else line for line in script.splitlines())

    def _gitlink_cleanup_scripts(self) -> tuple[tuple[str, str], ...]:
        return tuple((name, self._gitlink_cleanup_script(name)) for name in (PRECLEAN_NAME, POSTCLEAN_NAME))

    def _run_gitlink_cleanup(self, workspace: Path, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", script],
            cwd=workspace,
            env={**os.environ, "GITHUB_WORKSPACE": str(workspace)},
            check=False,
            capture_output=True,
            text=True,
        )

    def _assert_qualification_tag_identity(self, *, annotated: bool) -> None:
        target_expression, checkout_expression = self._qualification_identity_expressions()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

            def run_git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=repo, env=git_env, check=True)

            run_git("init", "-q")
            run_git("config", "user.name", "Contract Test")
            run_git("config", "user.email", "contract@example.com")
            (repo / "candidate.txt").write_text("immutable candidate\n", encoding="utf-8")
            run_git("add", "candidate.txt")
            run_git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "candidate")
            release_tag = "v0.12.105+12105-macos"
            tag_args = ["git", "tag"]
            if annotated:
                tag_args.extend(["-a", "-m", "candidate"])
            tag_args.append(release_tag)
            subprocess.run(tag_args, cwd=repo, env=git_env, check=True)
            run_git("checkout", "-q", release_tag)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f'TARGET_SHA=$({target_expression}); CHECKOUT_SHA=$({checkout_expression}); '
                    'test "$TARGET_SHA" = "$CHECKOUT_SHA"',
                ],
                cwd=repo,
                env={"PATH": "/usr/bin:/bin", "RELEASE_TAG": release_tag},
                check=False,
            )
            self.assertEqual(result.returncode, 0)

    def test_canonical_release_and_qualification_use_lowercase_dmg_asset(self) -> None:
        build_identity = codemagic().split("- name: Resolve trusted source and build identity", 1)[1]
        build_identity = build_identity.split("- name: ", 1)[0]
        preview_branch, canonical_branch = build_identity.split("          else\n", 1)
        qualification = workflow("desktop_qualify_beta.yml")

        self.assertIn('DMG_PATH="$BUILD_DIR/Omi-Preview.dmg"', preview_branch)
        self.assertIn('DMG_PATH="$BUILD_DIR/omi.dmg"', canonical_branch)
        self.assertNotIn('DMG_PATH="$BUILD_DIR/$APP_NAME.dmg"', canonical_branch)
        self.assertIn("--pattern 'Omi.zip' --pattern 'omi.dmg'", qualification)
        self.assertIn("STABLE_DMG=/tmp/desktop-beta-qualification/assets/omi.dmg", qualification)
        self.assertIn('--asset "omi.dmg=$STABLE_DMG"', qualification)

    def test_has_one_automatic_candidate_to_beta_authority(self) -> None:
        candidate = workflow("desktop_auto_release.yml")
        qualification = workflow("desktop_qualify_beta.yml")
        beta = workflow("desktop_promote_beta.yml")
        self.assertIn("schedule:", candidate)
        self.assertNotIn("workflow_dispatch:", candidate)
        self.assertNotIn("uses: ./.github/workflows/desktop_promote_beta.yml", qualification)
        self.assertNotIn("promote-qualified-beta:", qualification)
        self.assertIn('workflows: ["Qualify Desktop Beta Candidate"]', beta)
        self.assertIn("types: [completed]", beta)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", beta)
        self.assertIn("github.event.workflow_run.event == 'workflow_dispatch'", beta)
        self.assertIn("github.event.workflow_run.head_branch", beta)
        self.assertIn("github.event.workflow_run.head_sha", beta)
        self.assertIn("Invalid immutable macOS release tag", beta)
        self.assertIn("does not match successful qualification SHA", beta)
        self.assertIn("workflow_call:", beta)
        self.assertNotIn("workflow_dispatch:", beta)
        self.assertEqual(beta.count("/v2/desktop/beta/promote-qualified"), 1)

    def test_beta_qualification_workflow_uses_supported_exact_cli(self) -> None:
        qualification = workflow("desktop_qualify_beta.yml")
        qualification_script = (ROOT / "desktop/macos/scripts/qualify-desktop-beta.sh").read_text(
            encoding="utf-8"
        )
        qualify_step_name = "      - name: Qualify exact candidate on hermetic stack"
        qualify_step = qualification.split(qualify_step_name, 1)[1]
        qualify_step = qualify_step.split("\n      - name:", 1)[0]
        invoked_options = tuple(
            re.findall(r"^\s+(--[a-z0-9-]+)(?:\s+[^\\]+)? \\$", qualify_step, re.MULTILINE)
        )
        supported_options = set(re.findall(r"^    (--[a-z0-9-]+)\)$", qualification_script, re.MULTILINE))

        self.assertEqual(
            invoked_options,
            (
                "--automatic",
                "--github-actions-artifact",
                "--signed-smoke-result",
                "--candidate-gate-result",
            ),
        )
        self.assertTrue(set(invoked_options).issubset(supported_options))
        self.assertNotIn("--no-promote", qualify_step)

    def test_beta_qualification_peels_every_compared_identity_to_a_commit(self) -> None:
        target_expression, checkout_expression = self._qualification_identity_expressions()
        self.assertEqual(target_expression, 'git rev-parse "$RELEASE_TAG^{commit}"')
        self.assertEqual(checkout_expression, 'git rev-parse "HEAD^{commit}"')
        self.assertEqual(
            workflow("desktop_qualify_beta.yml").count('TARGET_SHA=$(git rev-parse "$RELEASE_TAG^{commit}")'),
            2,
        )

    def test_beta_qualification_accepts_annotated_tag_at_exact_checkout_commit(self) -> None:
        self._assert_qualification_tag_identity(annotated=True)

    def test_beta_qualification_accepts_lightweight_tag_at_exact_checkout_commit(self) -> None:
        self._assert_qualification_tag_identity(annotated=False)

    def test_beta_qualification_bounds_checkout_with_identical_exact_cleanup(self) -> None:
        qualification = workflow("desktop_qualify_beta.yml")
        checkout_name = "Checkout qualification controls"
        attach_name = "Attach immutable qualification evidence to the candidate release"
        self.assertLess(qualification.index(PRECLEAN_NAME), qualification.index(checkout_name))
        self.assertLess(qualification.index(checkout_name), qualification.index(POSTCLEAN_NAME))
        self.assertLess(qualification.index(attach_name), qualification.index(POSTCLEAN_NAME))
        self.assertEqual(re.findall(r"^      - name: (.+)$", qualification, re.MULTILINE)[-1], POSTCLEAN_NAME)

        preclean_step = self._qualification_step(PRECLEAN_NAME)
        postclean_step = self._qualification_step(POSTCLEAN_NAME)
        self.assertNotIn("        if: always()", preclean_step)
        self.assertIn("        if: always()", postclean_step)
        self.assertNotIn("continue-on-error:", preclean_step + postclean_step)

        preclean_script = self._gitlink_cleanup_script(PRECLEAN_NAME)
        postclean_script = self._gitlink_cleanup_script(POSTCLEAN_NAME)
        self.assertEqual(preclean_script, postclean_script)
        self.assertEqual(preclean_script.count(str(GITLINK_RELATIVE)), 1)
        self.assertEqual(preclean_script.count('rmdir "$stale_gitlink"'), 1)
        self.assertNotIn("rm -rf", preclean_script)
        self.assertNotIn(".gitmodules", preclean_script)

    def test_beta_qualification_cleanup_accepts_missing_gitlink(self) -> None:
        for name, script in self._gitlink_cleanup_scripts():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                result = self._run_gitlink_cleanup(workspace, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((workspace / GITLINK_RELATIVE).exists())

    def test_beta_qualification_cleanup_removes_empty_gitlink(self) -> None:
        for name, script in self._gitlink_cleanup_scripts():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                stale = workspace / GITLINK_RELATIVE
                stale.mkdir(parents=True)
                result = self._run_gitlink_cleanup(workspace, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(stale.exists())

    def test_beta_qualification_cleanup_preserves_git_file(self) -> None:
        for name, script in self._gitlink_cleanup_scripts():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                initialized = workspace / GITLINK_RELATIVE
                initialized.mkdir(parents=True)
                git_file = initialized / ".git"
                git_file.write_text("gitdir: elsewhere\n", encoding="utf-8")
                result = self._run_gitlink_cleanup(workspace, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(git_file.read_text(encoding="utf-8"), "gitdir: elsewhere\n")

    def test_beta_qualification_cleanup_preserves_git_directory(self) -> None:
        for name, script in self._gitlink_cleanup_scripts():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                initialized = workspace / GITLINK_RELATIVE
                (initialized / ".git").mkdir(parents=True)
                result = self._run_gitlink_cleanup(workspace, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((initialized / ".git").is_dir())

    def test_beta_qualification_cleanup_fails_closed_on_nonempty_gitlink(self) -> None:
        for name, script in self._gitlink_cleanup_scripts():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                nonempty = workspace / GITLINK_RELATIVE
                nonempty.mkdir(parents=True)
                marker = nonempty / "preserve.txt"
                marker.write_text("do not delete\n", encoding="utf-8")
                result = self._run_gitlink_cleanup(workspace, script)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(marker.read_text(encoding="utf-8"), "do not delete\n")
                self.assertIn("Refusing to remove nonempty uninitialized gitlink", result.stderr)

    def test_beta_qualification_cleanup_ignores_sibling_decoy(self) -> None:
        for name, script in self._gitlink_cleanup_scripts():
            with self.subTest(step=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                stale = workspace / GITLINK_RELATIVE
                decoy = stale.with_name(f"{stale.name}-decoy")
                stale.mkdir(parents=True)
                decoy.mkdir()
                result = self._run_gitlink_cleanup(workspace, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(stale.exists())
                self.assertTrue(decoy.is_dir())

    def test_stable_is_manual_and_uses_one_explicit_confirmation(self) -> None:
        stable = workflow("desktop_promote_prod.yml")
        self.assertIn("workflow_dispatch:", stable)
        self.assertNotIn("\n  schedule:", stable)
        self.assertNotIn("\n  push:", stable)
        self.assertIn("confirm:", stable)
        self.assertIn("promote-stable", stable)
        self.assertNotIn("operation:", stable)
        self.assertNotIn("repoint", stable)
        self.assertNotIn("qualification_run_id", stable)
        self.assertNotIn("expected_current_release_id:", stable)

    def test_manual_beta_hatches_reuse_prod_authority_and_cannot_reach_stable(self) -> None:
        recovery = workflow("desktop_recover_beta.yml")
        rollback = workflow("desktop_rollback_beta.yml")
        rollout = workflow("desktop_breakglass_rollout_beta.yml")
        beta = workflow("desktop_promote_beta.yml")
        qualification_script = (ROOT / "desktop/macos/scripts/qualify-desktop-beta.sh").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", recovery)
        for required in ("release_tag:", "confirm:", "reason:", "recover-beta", "github.actor"):
            self.assertIn(required, recovery)
        self.assertIn("uses: ./.github/workflows/desktop_promote_beta.yml", recovery)
        self.assertNotIn("/v2/desktop/beta/promote-qualified", recovery)
        self.assertNotIn("gh workflow run desktop_promote_beta.yml", qualification_script)
        self.assertNotIn("workflow_dispatch:", beta)
        for hatch, operation in (
            (rollback, "--arg operation rollback"),
            (rollout, "--arg operation rollout"),
        ):
            self.assertIn("workflow_dispatch:", hatch)
            self.assertNotIn("push:", hatch)
            self.assertNotIn("schedule:", hatch)
            self.assertIn("environment: prod", hatch)
            self.assertIn("group: desktop-beta-promotion", hatch)
            self.assertIn("cancel-in-progress: false", hatch)
            self.assertIn("secrets.GCP_CREDENTIALS", hatch)
            self.assertIn("gcloud secrets versions access latest --secret=ADMIN_KEY", hatch)
            self.assertNotIn("BETA_BREAKGLASS", hatch)
            self.assertNotIn("beta-breakglass", hatch)
            self.assertIn("/v2/desktop/beta/breakglass", hatch)
            self.assertIn(operation, hatch)
            for required in ("incident_url", "reason", "current_release_id", "target_release_id", "expected_generation", "github.run_id", "github.actor"):
                self.assertIn(required, hatch)
            self.assertNotIn("stable", hatch.lower().replace("macos-beta", ""))
        self.assertIn("normal_path_unavailable", rollout)
        self.assertNotIn("source_sha", rollout)
        self.assertNotIn("build_number", rollout)

    def test_breakglass_credential_preflight_is_read_only_and_beta_scoped(self) -> None:
        preflight = workflow("desktop_breakglass_credential_preflight.yml")
        self.assertIn("workflow_dispatch:", preflight)
        self.assertIn("environment: prod", preflight)
        self.assertIn("permissions: {}", preflight)
        self.assertIn("secrets.GCP_CREDENTIALS", preflight)
        self.assertIn("gcloud secrets versions access latest --secret=ADMIN_KEY", preflight)
        self.assertIn("/v2/desktop/releases/$RELEASE_TAG", preflight)
        self.assertNotIn("--request POST", preflight)
        self.assertNotIn("/v2/desktop/beta/breakglass", preflight)
        self.assertNotIn("/v2/desktop/channels/promote", preflight)
        self.assertNotIn("stable", preflight.lower())

    def test_beta_admission_control_is_manual_protected_and_beta_only(self) -> None:
        admission = workflow("desktop_beta_admission_control.yml")
        self.assertIn("workflow_dispatch:", admission)
        for forbidden_trigger in ("\n  schedule:", "\n  push:", "\n  workflow_call:", "\n  workflow_run:"):
            self.assertNotIn(forbidden_trigger, admission)
        self.assertIn("permissions: {}", admission)
        self.assertIn("environment: prod", admission)
        self.assertIn("timeout-minutes: 5", admission)
        self.assertIn("group: desktop-beta-promotion", admission)
        self.assertIn("cancel-in-progress: false", admission)
        self.assertIn("- enable", admission)
        self.assertIn("- disable", admission)
        self.assertIn("ENABLE BETA AUTOMATION", admission)
        self.assertIn("DISABLE BETA AUTOMATION", admission)
        validation = admission.index("      - name: Validate explicit Beta admission intent")
        authentication = admission.index("      - name: Use the existing production Google identity")
        mutation = admission.index("      - name: Change only the desktop Beta admission fence")
        self.assertLess(validation, authentication)
        self.assertLess(authentication, mutation)
        self.assertIn("secrets.GCP_CREDENTIALS", admission)
        self.assertIn("gcloud secrets versions access latest --secret=ADMIN_KEY", admission)
        self.assertIn('[[ -n "$ADMIN_KEY" ]]', admission)
        self.assertIn('echo "::add-mask::$ADMIN_KEY"', admission)
        self.assertIn("unset ADMIN_KEY", admission)
        self.assertEqual(admission.count("https://api.omi.me/v2/desktop/beta/admission"), 1)
        self.assertIn("--request PUT", admission)
        self.assertIn("'{promotion_enabled: $promotion_enabled}'", admission)
        self.assertIn('keys == ["generation", "promotion_enabled"]', admission)
        self.assertIn(".promotion_enabled == $expected", admission)
        self.assertIn(".generation | type == \"number\"", admission)
        for forbidden_authority in (
            "BETA_PROMOTION_TOKEN",
            "/v2/desktop/beta/breakglass",
            "/v2/desktop/beta/promote-qualified",
            "/v2/desktop/channels/promote",
        ):
            self.assertNotIn(forbidden_authority, admission)
        self.assertNotIn("stable", admission.lower())

    def test_backend_release_vector_verifies_after_prod_traffic_shift(self) -> None:
        backend = workflow("gcp_backend.yml")
        shift = backend.index("      - name: Shift Cloud Run traffic to validated revisions")
        verify = backend.index("      - name: Verify serving backend release vector")
        status = backend.index("      - name: Cloud Run deploy status report", verify)
        self.assertLess(shift, verify)
        self.assertLess(verify, status)
        evidence = backend[verify:status]
        self.assertIn("$DEPLOY_CONTROL_SCRIPTS/verify_backend_release_vector.py", evidence)
        self.assertIn("--deploy-run-id \"${{ github.run_id }}\"", evidence)
        self.assertIn("--deploy-run-attempt \"${{ github.run_attempt }}\"", evidence)


if __name__ == "__main__":
    unittest.main()
