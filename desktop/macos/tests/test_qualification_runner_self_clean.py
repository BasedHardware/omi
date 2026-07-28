#!/usr/bin/env python3
"""Deterministic contracts for ownership-scoped M1 runner self-clean."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qualification-runner-self-clean.py"
SPEC = importlib.util.spec_from_file_location("qualification_runner_self_clean", SCRIPT)
assert SPEC and SPEC.loader
self_clean = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = self_clean
SPEC.loader.exec_module(self_clean)


class QualificationRunnerSelfCleanTests(unittest.TestCase):
    def _fault_record(
        self,
        root: Path,
        *,
        bundle: str = "omi-fault-owned-contract",
        token: str = "owned-contract-token-123456789",
        pid: int = 42424,
    ) -> tuple[Path, self_clean.ProcessRecord]:
        executable = f"/Applications/{bundle}.app/Contents/MacOS/Omi Computer"
        command = f"{executable!r} --omi-launch-token={token}"
        started = "Mon Jul 27 20:00:00 2026"
        path = root / "fault-app.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "run_token": token,
                    "bundle": bundle,
                    "bundle_id": f"com.omi.{bundle}",
                    "app_path": f"/Applications/{bundle}.app",
                    "executable_path": executable,
                    "automation_port": 47791,
                    "launch_transport": "open",
                    "launch_pid": pid,
                    "process_start": started,
                    "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path, self_clean.ProcessRecord(pid, pid, started, command)

    def test_fault_classifier_accepts_only_exact_token_bound_disposable_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record, process = self._fault_record(Path(directory))
            target, observed = self_clean._validate_fault_app_target(record, {process.pid: process})

            self.assertEqual(target.pid, process.pid)
            self.assertEqual(target.bundle, "omi-fault-owned-contract")
            self.assertEqual(observed, process)

            replaced = self_clean.ProcessRecord(
                process.pid,
                process.process_group,
                process.process_start,
                process.command.replace("owned-contract-token", "foreign-token"),
            )
            with self.assertRaisesRegex(self_clean.HygieneError, "no longer matches"):
                self_clean._validate_fault_app_target(record, {process.pid: replaced})

    def test_fault_classifier_rejects_production_bundle_even_with_self_consistent_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record, process = self._fault_record(Path(directory), bundle="Omi")

            with self.assertRaisesRegex(self_clean.HygieneError, "disposable bundle"):
                self_clean._validate_fault_app_target(record, {process.pid: process})

    def test_stage_cleanup_removes_only_noncurrent_numeric_owned_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stage_root = Path(directory) / "desktop-beta-qualification"
            stage_root.mkdir()
            old = stage_root / "100-1"
            current = stage_root / "200-2"
            unrelated = stage_root / "manual-not-a-run"
            for path in (old, current, unrelated):
                path.mkdir(mode=0o700)
                (path / "sentinel").write_text(path.name, encoding="utf-8")

            results = self_clean.clean_stages(
                stage_root,
                current_run_id=current.name,
                processes=[],
                dry_run=False,
            )

            self.assertFalse(old.exists())
            self.assertTrue(current.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(
                results,
                [
                    {"run_id": "100-1", "action": "removed"},
                    {"run_id": "200-2", "action": "preserved-current"},
                ],
            )

    def test_stage_cleanup_refuses_a_live_exact_path_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stage_root = Path(directory) / "desktop-beta-qualification"
            stage_root.mkdir()
            active = stage_root / "300-1"
            active.mkdir(mode=0o700)
            process = self_clean.ProcessRecord(
                51515,
                51515,
                "Mon Jul 27 20:00:00 2026",
                f"python3 {active}/source/desktop/macos/scripts/qualify-desktop-beta.sh",
            )

            with self.assertRaisesRegex(self_clean.HygieneError, "live process reference"):
                self_clean.clean_stages(
                    stage_root,
                    current_run_id="400-1",
                    processes=[process],
                    dry_run=False,
                )

            self.assertTrue(active.exists())

    def test_dry_run_report_declares_production_bundles_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = type(
                "Args",
                (),
                {
                    "repo_root": Path(__file__).resolve().parents[3],
                    "cache_root": root / "cache",
                    "qualification_lease_root": root / "lease",
                    "stage_root": root / "desktop-beta-qualification",
                    "fault_temp_root": root,
                    "capacity_path": root,
                    "current_run_id": "500-1",
                    "minimum_free_kib": 1,
                    "minimum_free_inodes": 1,
                    "minimum_age_seconds": 3600,
                    "max_entries": 16,
                    "max_reclaim_kib": 128 * 1024 * 1024,
                    "dry_run": True,
                },
            )()

            report = self_clean.run(args)

            self.assertEqual(report["status"], "passed")
            self.assertTrue(report["mode"] == "dry-run")
            self.assertFalse(report["production_bundles_touched"])
            self.assertEqual(
                report["before"]["known_disposable_process_count"], report["after"]["known_disposable_process_count"]
            )


if __name__ == "__main__":
    unittest.main()
