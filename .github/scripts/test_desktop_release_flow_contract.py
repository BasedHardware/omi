#!/usr/bin/env python3
"""Workflow contracts for M1-Studio-only macOS Beta qualification."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_TAG = "v0.12.124+12124-macos"


def clean_git_environment(env: dict[str, str]) -> dict[str, str]:
    """Keep hook-local Git state out of isolated qualification fixtures."""
    return {key: value for key, value in env.items() if not key.startswith("GIT_")}


class DesktopReleaseFlowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github/workflows/desktop_qualify_beta.yml").read_text(encoding="utf-8")
        self.recovery = (ROOT / ".github/workflows/desktop_recover_beta.yml").read_text(encoding="utf-8")
        self.codemagic = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        self.release_guard = (ROOT / ".github/scripts/check-release-process-guards.py").read_text(encoding="utf-8")
        self.promotion = (ROOT / ".github/workflows/desktop_promote_beta.yml").read_text(encoding="utf-8")

    def _workflow_script(self, step_name: str) -> str:
        marker = f"      - name: {step_name}\n"
        self.assertEqual(self.workflow.count(marker), 1)
        block = self.workflow.split(marker, 1)[1].split("\n      - ", 1)[0]
        script = block.split("        run: |\n", 1)[1]
        return "\n".join(line[10:] if line.startswith("          ") else line for line in script.splitlines())

    def _run_workflow_script(
        self,
        step_name: str,
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        # Git invokes hooks with repository-scoped GIT_* variables. This test
        # runs workflow commands in an independent disposable repository, so
        # do not let the hook's index/worktree leak into that shell.
        isolated_env = {name: value for name, value in env.items() if not name.startswith("GIT_")}
        return subprocess.run(
            ["bash", "-c", self._workflow_script(step_name)],
            cwd=cwd,
            env=isolated_env,
            check=False,
            capture_output=True,
            text=True,
        )

    def _create_candidate_remote(self, root: Path) -> tuple[Path, str]:
        server = root / "git-server"
        remote = server / "BasedHardware" / "omi.git"
        source = root / "candidate-source"
        remote.parent.mkdir(parents=True)
        source.mkdir()
        git_env = clean_git_environment(dict(os.environ))

        def git(*args: str, cwd: Path = source) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=git_env,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        git("init", "--quiet")
        git("config", "user.name", "Qualification Contract")
        git("config", "user.email", "qualification-contract@example.com")
        (source / "candidate.txt").write_text("immutable candidate\n", encoding="utf-8")
        reclaim_source = ROOT / "desktop/macos/scripts/qualification-cache-reclaim.py"
        reclaim_target = source / "desktop/macos/scripts/qualification-cache-reclaim.py"
        reclaim_target.parent.mkdir(parents=True)
        reclaim_target.write_bytes(reclaim_source.read_bytes())
        reclaim_target.chmod(0o755)
        for name in ("qualification-runner-self-clean.py", "qualification-watchdog.py"):
            target = reclaim_target.parent / name
            target.write_bytes((reclaim_source.parent / name).read_bytes())
            target.chmod(0o755)
        shutil.copytree(
            ROOT / "scripts/dev-harness/dev_harness",
            source / "scripts/dev-harness/dev_harness",
        )
        git("add", "candidate.txt", "desktop/macos/scripts", "scripts/dev-harness/dev_harness")
        git("-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "candidate")
        candidate_sha = git("rev-parse", "HEAD")
        git("tag", "-a", RELEASE_TAG, "-m", "candidate")
        git("init", "--quiet", "--bare", str(remote), cwd=root)
        git("remote", "add", "origin", remote.as_uri())
        git("push", "--quiet", "origin", "HEAD:refs/heads/main", f"refs/tags/{RELEASE_TAG}")
        return server, candidate_sha

    def test_only_m1_studio_can_qualify(self) -> None:
        self.assertIn("qualify-m1-studio:", self.workflow)
        self.assertIn("omi-qual-m1-studio", self.workflow)
        self.assertIn("needs: qualify-m1-studio", self.workflow)
        self.assertNotIn("codemagic-lane", self.workflow)
        self.assertNotIn("omi-qual-m4-mini", self.workflow)
        self.assertNotIn("omi-desktop-qualification:", self.codemagic)
        self.assertNotIn("desktop_codemagic_qualification", self.workflow)

    def test_m1_qualification_binds_the_immutable_tag(self) -> None:
        for fragment in (
            'checkout --quiet --detach "refs/tags/$RELEASE_TAG"',
            "ref: ${{ inputs.release_tag }}",
            'test "$ref" = "$RELEASE_TAG"',
            'git rev-parse "$RELEASE_TAG^{commit}"',
            "git rev-parse 'HEAD^{commit}'",
            "check-desktop-auto-beta-candidate.py",
            "--automatic",
            "--github-actions-artifact",
            "group: desktop-beta-qualification-m1",
            "cancel-in-progress: false",
        ):
            self.assertIn(fragment, self.workflow)

    def test_m1_qualification_requires_live_desktop_backend_contract(self) -> None:
        for fragment in (
            "Verify live desktop-backend chat compatibility",
            '.chat_contract_version == "1"',
            "https://api.omiapi.com/v1/health",
            '.status == "ok"',
            "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/health",
            "desktop-backend-compatibility.json",
            "Prove production Firebase UID continuity on Beta development authorities",
            "probe_beta_uid_continuity.py",
            "beta-uid-continuity.json",
            "FIREBASE_AUTH_PROJECT_ID: based-hardware",
            "Checkout trusted qualification controls",
        ):
            self.assertIn(fragment, self.workflow)
        compatibility = self.workflow.index("Verify live desktop-backend chat compatibility")
        qualify = self.workflow.index("Qualify exact candidate on the M1 Studio hermetic stack")
        self.assertLess(compatibility, qualify)

    def test_uid_continuity_probe_removes_the_signer_before_candidate_scripts(self) -> None:
        probe = self._workflow_script("Prove production Firebase UID continuity on Beta development authorities")
        for fragment in (
            "umask 077",
            'gha_application_credentials_file="${GOOGLE_APPLICATION_CREDENTIALS:?google-github-actions/auth did not provide credentials}"',
            'gha_credentials_file="${GOOGLE_GHA_CREDS_PATH:-$gha_application_credentials_file}"',
            "trap 'rm -f -- \"$gha_application_credentials_file\" \"$gha_credentials_file\" \"$signer_file\" \"$token_file\"' EXIT",
            'rm -f -- "$signer_file"',
            'rm -f -- "$gha_application_credentials_file" "$gha_credentials_file"',
            "unset GOOGLE_APPLICATION_CREDENTIALS GOOGLE_GHA_CREDS_PATH CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
            "unset FIREBASE_PROBE_SIGNER_B64",
            "probe_beta_uid_continuity.py",
        ):
            self.assertIn(fragment, probe)
        self.assertLess(probe.index("firebase_release_probe_token.py"), probe.rindex('rm -f -- "$signer_file"'))
        self.assertLess(probe.rindex('rm -f -- "$signer_file"'), probe.index("probe_beta_uid_continuity.py"))
        self.assertLess(
            probe.index('rm -f -- "$gha_application_credentials_file" "$gha_credentials_file"'),
            probe.index("probe_beta_uid_continuity.py"),
        )
        self.assertLess(
            self.workflow.index("Prove production Firebase UID continuity on Beta development authorities"),
            self.workflow.index("Fetch candidate release inputs into this run only"),
        )
        self.assertIn(
            "      - name: Prove production Firebase UID continuity on Beta development authorities\n"
            "        working-directory: qualification-controls",
            self.workflow,
        )

    def test_recovery_can_read_the_retained_qualification_artifact(self) -> None:
        for fragment in (
            "actions: read",
            "uses: ./.github/workflows/desktop_promote_beta.yml",
            "qualification_run_id:",
            "qualification_run_attempt:",
        ):
            self.assertIn(fragment, self.recovery)

    def test_reusable_promotion_validates_retained_run_identity_before_artifact_selection(self) -> None:
        self.assertIn('[[ "$QUALIFICATION_RUN_ID" =~ ^[1-9][0-9]*$ ]]', self.promotion)
        self.assertIn('[[ "$QUALIFICATION_RUN_ATTEMPT" =~ ^[1-9][0-9]*$ ]]', self.promotion)

    def test_reusable_promotion_requires_uid_continuity_only_for_beta_artifact_topology(self) -> None:
        # omi-test-quality: source-inspection -- static workflow condition gates immutable evidence topology.
        self.assertIn('if jq -e \'.artifacts | has("Omi.Beta.zip") and has("omi-beta.dmg")\'', self.promotion)
        self.assertIn("qualification evidence lacks production Firebase UID continuity proof", self.promotion)

    def test_release_process_guard_accepts_the_run_isolated_tag_checkout(self) -> None:
        tree = ast.parse(self.release_guard)
        guard = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "check_desktop_qualification_runner"
        )
        fragments = {
            node.value for node in ast.walk(guard) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn('git -C "$source_dir" checkout --quiet --detach "refs/tags/$RELEASE_TAG"', fragments)
        self.assertNotIn("ref: ${{ inputs.release_tag }}", fragments)

    def test_release_process_guard_matches_trusted_auto_promotion(self) -> None:
        trusted_repository = "github.event.workflow_run.head_repository.full_name == github.repository"
        obsolete_dispatch_gate = "github.event.workflow_run.event == 'workflow_dispatch'"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative_path in (
                ".github/workflows/desktop_qualify_beta.yml",
                ".github/workflows/desktop_promote_beta.yml",
                ".github/scripts/check-desktop-auto-beta-candidate.py",
            ):
                source = ROOT / relative_path
                target = root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            promotion = root / ".github/workflows/desktop_promote_beta.yml"
            self.assertIn(trusted_repository, self.promotion)
            self.assertNotIn(obsolete_dispatch_gate, self.promotion)
            promotion.write_text(self.promotion.replace(trusted_repository, "", 1), encoding="utf-8")
            spec = importlib.util.spec_from_file_location(
                "release_process_guards",
                ROOT / ".github/scripts/check-release-process-guards.py",
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader if spec else None)
            guard = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(guard)
            guard.ROOT = root
            errors = guard.check_desktop_qualification_runner()
            self.assertTrue(any(trusted_repository in error for error in errors), errors)
            promotion.write_text(self.promotion, encoding="utf-8")
            self.assertEqual(guard.check_desktop_qualification_runner(), [])

    def test_run_staging_evidence_and_cleanup_are_isolated_and_rerun_safe(self) -> None:
        for fragment in (
            "${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
            "Refusing reused qualification staging directory",
            "OMI_QUALIFICATION_CLEANUP_CONTEXT",
            "Finalize only this authenticated qualification lease",
            "if: always()",
            "qualification-lease-command.sh\" release",
            "runner-hygiene.json",
            "qualification-runner-self-clean.py",
            "qualification-watchdog.py",
            "--minimum-age-seconds 3600",
            "--max-entries 16",
            "--max-reclaim-kib 134217728",
            "33554432",
            "desktop-qualification-evidence-${{ inputs.release_tag }}-m1-${{ github.run_id }}-${{ github.run_attempt }}",
            "desktop-qualification-backend-compatibility-${{ inputs.release_tag }}-m1-${{ github.run_id }}-${{ github.run_attempt }}",
            "overwrite: false",
            "qualification-evidence-${TARGET_SHA}-${digest}.json",
        ):
            self.assertIn(fragment, self.workflow)

    def test_checkout_ignores_stale_shared_workspace_and_uses_fresh_run_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            server, candidate_sha = self._create_candidate_remote(root)
            runner_temp = root / "runner-temp"
            runner_temp.mkdir()
            stale_workspace = root / "shared-workspace"
            stale_gitlink = stale_workspace / "omiGlass/firmware/.pio/libdeps/seeed_xiao_esp32s3/libopus"
            stale_gitlink.mkdir(parents=True)
            sentinel = stale_gitlink / "stale-runner-residue"
            sentinel.write_text("must remain untouched\n", encoding="utf-8")
            (stale_workspace / ".gitmodules").write_text(
                '[submodule "stale"]\n\tpath = omiGlass/firmware/.pio/libdeps/seeed_xiao_esp32s3/libopus\n'
                "\turl = https://invalid.example/stale.git\n",
                encoding="utf-8",
            )

            run_id = "30179386741"
            run_attempt = "2"
            stage = runner_temp / "desktop-beta-qualification" / f"{run_id}-{run_attempt}"
            env = {
                **os.environ,
                "RUNNER_TEMP": str(runner_temp),
                "TMPDIR": str(runner_temp),
                "GITHUB_RUN_ID": run_id,
                "GITHUB_RUN_ATTEMPT": run_attempt,
                "QUALIFICATION_STAGE": str(stage),
                "GITHUB_SERVER_URL": server.as_uri(),
                "GITHUB_REPOSITORY": "BasedHardware/omi",
                "RELEASE_TAG": RELEASE_TAG,
                "ref": RELEASE_TAG,
                "OMI_QUALIFICATION_MINIMUM_FREE_KIB": "1",
                "OMI_QUALIFICATION_MINIMUM_FREE_INODES": "1",
                "OMI_QUALIFICATION_SWIFT_CACHE_ROOT": str(root / "qualification-swiftpm-v2"),
                "OMI_QUALIFICATION_LEASE_ROOT": str(root / "omi-desktop-qualification"),
            }
            stage_result = self._run_workflow_script(
                "Create run-isolated qualification staging",
                cwd=stale_workspace,
                env=env,
            )
            self.assertEqual(stage_result.returncode, 0, stage_result.stderr)
            authority_result = self._run_workflow_script(
                "Checkout cache reclaim authority from exact candidate",
                cwd=stale_workspace,
                env=env,
            )
            self.assertEqual(authority_result.returncode, 0, authority_result.stderr)
            capacity_result = self._run_workflow_script(
                "Reclaim idle qualification cache and enforce runner capacity",
                cwd=stale_workspace,
                env=env,
            )
            self.assertEqual(capacity_result.returncode, 0, capacity_result.stderr)
            checkout_result = self._run_workflow_script(
                "Expand exact candidate checkout",
                cwd=stale_workspace,
                env=env,
            )
            self.assertEqual(checkout_result.returncode, 0, checkout_result.stderr)
            checked_out_sha = subprocess.run(
                ["git", "-C", str(stage / "source"), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                env={name: value for name, value in os.environ.items() if not name.startswith("GIT_")},
            ).stdout.strip()
            self.assertEqual(checked_out_sha, candidate_sha)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "must remain untouched\n")
            candidate_checkout = self.workflow.split("      - name: Checkout trusted qualification controls", 1)[0]
            self.assertNotIn("actions/checkout@", candidate_checkout)

            reused_result = self._run_workflow_script(
                "Create run-isolated qualification staging",
                cwd=stale_workspace,
                env=env,
            )
            self.assertNotEqual(reused_result.returncode, 0)
            self.assertIn("Refusing reused qualification staging directory", reused_result.stderr)

    def test_pre_checkout_failure_writes_cleanup_evidence_only_under_run_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runner_temp = root / "runner-temp"
            runner_temp.mkdir()
            run_id = "30179386741"
            run_attempt = "3"
            stage = runner_temp / "desktop-beta-qualification" / f"{run_id}-{run_attempt}"
            env = {
                **os.environ,
                "RUNNER_TEMP": str(runner_temp),
                "TMPDIR": str(runner_temp),
                "GITHUB_RUN_ID": run_id,
                "GITHUB_RUN_ATTEMPT": run_attempt,
                "QUALIFICATION_STAGE": str(stage),
                "OMI_QUALIFICATION_MINIMUM_FREE_KIB": "1",
                "OMI_QUALIFICATION_MINIMUM_FREE_INODES": "1",
            }
            stage_result = self._run_workflow_script(
                "Create run-isolated qualification staging",
                cwd=runner_temp,
                env=env,
            )
            self.assertEqual(stage_result.returncode, 0, stage_result.stderr)
            self.assertFalse((stage / "source").exists(), "test seam must stop before checkout")

            finalize_result = self._run_workflow_script(
                "Finalize only this authenticated qualification lease",
                cwd=runner_temp,
                env=env,
            )
            self.assertEqual(finalize_result.returncode, 0, finalize_result.stderr)
            cleanup = stage / "cleanup-evidence.json"
            self.assertEqual(json.loads(cleanup.read_text(encoding="utf-8")), {"cleanup_status": "no-lease-acquired"})

            unsafe_stage = root / "outside-run-stage"
            unsafe_env = {**env, "QUALIFICATION_STAGE": str(unsafe_stage)}
            unsafe_result = self._run_workflow_script(
                "Finalize only this authenticated qualification lease",
                cwd=runner_temp,
                env=unsafe_env,
            )
            self.assertNotEqual(unsafe_result.returncode, 0)
            self.assertFalse((unsafe_stage / "cleanup-evidence.json").exists())

    def test_low_runner_capacity_fails_before_checkout_with_durable_cleanup_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            server, _candidate_sha = self._create_candidate_remote(root)
            runner_temp = root / "runner-temp"
            runner_temp.mkdir()
            run_id = "30185755794"
            run_attempt = "1"
            stage = runner_temp / "desktop-beta-qualification" / f"{run_id}-{run_attempt}"
            env = {
                **os.environ,
                "RUNNER_TEMP": str(runner_temp),
                "TMPDIR": str(runner_temp),
                "GITHUB_RUN_ID": run_id,
                "GITHUB_RUN_ATTEMPT": run_attempt,
                "QUALIFICATION_STAGE": str(stage),
                "GITHUB_SERVER_URL": server.as_uri(),
                "GITHUB_REPOSITORY": "BasedHardware/omi",
                "RELEASE_TAG": RELEASE_TAG,
                "ref": RELEASE_TAG,
                "OMI_QUALIFICATION_MINIMUM_FREE_KIB": str(2**63 - 1),
                "OMI_QUALIFICATION_MINIMUM_FREE_INODES": "1",
                "OMI_QUALIFICATION_SWIFT_CACHE_ROOT": str(root / "qualification-swiftpm-v2"),
                "OMI_QUALIFICATION_LEASE_ROOT": str(root / "omi-desktop-qualification"),
            }

            stage_result = self._run_workflow_script(
                "Create run-isolated qualification staging",
                cwd=runner_temp,
                env=env,
            )
            self.assertEqual(stage_result.returncode, 0, stage_result.stderr)
            authority_result = self._run_workflow_script(
                "Checkout cache reclaim authority from exact candidate",
                cwd=runner_temp,
                env=env,
            )
            self.assertEqual(authority_result.returncode, 0, authority_result.stderr)
            capacity_result = self._run_workflow_script(
                "Reclaim idle qualification cache and enforce runner capacity",
                cwd=runner_temp,
                env=env,
            )
            self.assertNotEqual(capacity_result.returncode, 0)
            self.assertIn("qualification runner self-clean failed", capacity_result.stdout)
            self.assertFalse(
                (stage / "source/candidate.txt").exists(),
                "capacity failure must precede expansion of the candidate checkout",
            )
            hygiene = json.loads((stage / "runner-hygiene.json").read_text(encoding="utf-8"))
            self.assertEqual(hygiene["status"], "failed")
            self.assertEqual(hygiene["guard"], "qualification-runner-self-clean")
            self.assertNotIn("failure_class", hygiene)
            self.assertIn("insufficient-free-kib", hygiene["capacity"]["failure_reasons"])
            self.assertEqual(hygiene["capacity"]["minimum_free_kib"], 2**63 - 1)

            finalize_result = self._run_workflow_script(
                "Finalize only this authenticated qualification lease",
                cwd=runner_temp,
                env=env,
            )
            self.assertEqual(finalize_result.returncode, 0, finalize_result.stderr)
            cleanup = json.loads((stage / "cleanup-evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(cleanup, {"cleanup_status": "no-lease-acquired"})

    def test_normal_codemagic_candidate_build_still_dispatches_m1_workflow(self) -> None:
        self.assertIn("omi-desktop-swift-release:", self.codemagic)
        self.assertIn("Dispatch trusted macOS beta qualification", self.codemagic)
        self.assertIn("gh workflow run desktop_qualify_beta.yml", self.codemagic)


if __name__ == "__main__":
    unittest.main()
