#!/usr/bin/env python3
"""Behavioral contracts for ownership-safe qualification cache reclaim."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qualification-cache-reclaim.py"
SPEC = importlib.util.spec_from_file_location("qualification_cache_reclaim", SCRIPT)
assert SPEC and SPEC.loader
reclaim = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reclaim
SPEC.loader.exec_module(reclaim)


class QualificationCacheReclaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.cache_root = self.root / "qualification-swiftpm-v2"
        self.cache_root.mkdir(mode=0o700)
        self.lease_root = self.root / "omi-desktop-qualification"
        self.capacity_path = self.root
        self.now = 2_000_000_000

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, repository: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
            env={name: value for name, value in os.environ.items() if not name.startswith("GIT_")},
        ).stdout.strip()

    def _entry(self, name: str, *, age_seconds: int, size_bytes: int = 4096) -> tuple[str, Path]:
        staging = self.root / f"repo-{name}"
        package = staging / "desktop/macos/Desktop"
        package.mkdir(parents=True)
        (package / "Package.swift").write_text(f"// {name}\n", encoding="utf-8")
        (package / "Package.resolved").write_text('{"pins":[]}\n', encoding="utf-8")
        self._git(staging, "init", "--quiet")
        self._git(staging, "config", "user.name", "Qualification Cache Test")
        self._git(staging, "config", "user.email", "qualification-cache@omi.invalid")
        self._git(staging, "add", ".")
        self._git(staging, "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", name)
        source_sha = self._git(staging, "rev-parse", "HEAD")
        entry = self.cache_root / source_sha
        source = entry / "source"
        entry.mkdir(mode=0o700)
        source.mkdir(mode=0o700)
        for child in staging.iterdir():
            target = source / child.name
            if child.is_dir():
                subprocess.run(["cp", "-R", str(child), str(target)], check=True)
            else:
                target.write_bytes(child.read_bytes())
        build = source / "desktop/macos/Desktop/.build"
        build.mkdir(mode=0o700)
        (build / "payload.bin").write_bytes(b"x" * size_bytes)
        (entry / "manifest.json").write_text(
            json.dumps({"cache_format": 2, "source_sha": source_sha}) + "\n",
            encoding="utf-8",
        )
        (entry / "complete").write_text("complete\n", encoding="utf-8")
        timestamp = self.now - age_seconds
        for path in (entry / "manifest.json", entry / "complete", entry):
            os.utime(path, (timestamp, timestamp))
        return source_sha, entry

    def _capacity_probe(self, initial_entries: set[str], *, base_kib: int = 10) -> object:
        def probe(_path: Path) -> reclaim.Capacity:
            deleted = len([source_sha for source_sha in initial_entries if not (self.cache_root / source_sha).exists()])
            return reclaim.Capacity(available_kib=base_kib + deleted * 100, available_inodes=1_000_000)

        return probe

    def _run(
        self,
        *,
        minimum_free_kib: int,
        capacity_probe: object,
        max_entries: int = 8,
        process_probe: object = lambda: [],
    ) -> dict[str, object]:
        return reclaim.reclaim(
            self.cache_root,
            qualification_lease_root=self.lease_root,
            capacity_path=self.capacity_path,
            minimum_free_kib=minimum_free_kib,
            minimum_free_inodes=1,
            minimum_age_seconds=6 * 60 * 60,
            max_entries=max_entries,
            max_reclaim_kib=64 * 1024 * 1024,
            now=self.now,
            capacity_probe=capacity_probe,
            process_probe=process_probe,
        )

    def _harness_lease(self, source_sha: str, source: Path) -> None:
        lease_id = "qualification-active"
        state = self.lease_root / "state" / lease_id
        state.mkdir(parents=True)
        sentinel = {
            "schema_version": 1,
            "owner": "omi-local-dev-harness",
            "instance": lease_id,
            "repo_root": str(source),
        }
        (state / reclaim.HARNESS_SENTINEL).write_text(json.dumps(sentinel), encoding="utf-8")
        self.lease_root.joinpath("qualification-lease.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "owner": "omi-desktop-qualification",
                    "lease_id": lease_id,
                    "owner_pid": os.getpid(),
                    "repo_root": str(source),
                    "state_root": str(state),
                    "token": "t" * 32,
                }
            ),
            encoding="utf-8",
        )

    def test_deletes_oldest_idle_entries_until_capacity_passes_and_preserves_harness_worktree(self) -> None:
        oldest_sha, oldest = self._entry("oldest", age_seconds=30 * 60 * 60)
        next_sha, next_entry = self._entry("next", age_seconds=20 * 60 * 60)
        active_sha, active = self._entry("active", age_seconds=40 * 60 * 60)
        self._harness_lease(active_sha, active / "source")
        initial = {oldest_sha, next_sha, active_sha}

        report = self._run(minimum_free_kib=210, capacity_probe=self._capacity_probe(initial))

        self.assertEqual(report["status"], "passed")
        self.assertFalse(oldest.exists())
        self.assertFalse(next_entry.exists())
        self.assertTrue(active.exists())
        deleted = report["reclaim"]["deleted_entries"]
        self.assertEqual([item["source_sha"] for item in deleted], [oldest_sha, next_sha])

    def test_live_cache_lease_preserves_entry_until_authenticated_release(self) -> None:
        source_sha, entry = self._entry("leased", age_seconds=24 * 60 * 60)
        lease = reclaim.acquire_cache_lease(
            self.cache_root,
            source_sha=source_sha,
            lease_id="cache-live",
            owner_pid=os.getpid(),
            now=self.now,
        )

        report = self._run(
            minimum_free_kib=100,
            capacity_probe=self._capacity_probe({source_sha}),
        )
        self.assertEqual(report["status"], "failed")
        self.assertTrue(entry.exists())

        with self.assertRaises(reclaim.CacheSafetyError):
            reclaim.release_cache_lease(
                self.cache_root,
                source_sha=source_sha,
                lease_id="cache-live",
                owner_pid=os.getpid(),
                token="wrong-token",
            )
        reclaim.release_cache_lease(
            self.cache_root,
            source_sha=source_sha,
            lease_id="cache-live",
            owner_pid=os.getpid(),
            token=str(lease["token"]),
        )
        # The qualifier's cleanup gate and the workflow always() finalizer may
        # both observe the same authenticated context.
        reclaim.release_cache_lease(
            self.cache_root,
            source_sha=source_sha,
            lease_id="cache-live",
            owner_pid=os.getpid(),
            token=str(lease["token"]),
        )
        os.utime(entry, (self.now - 24 * 60 * 60, self.now - 24 * 60 * 60))
        report = self._run(
            minimum_free_kib=100,
            capacity_probe=self._capacity_probe({source_sha}),
        )
        self.assertEqual(report["status"], "passed")
        self.assertFalse(entry.exists())

    def test_malformed_provenance_refuses_before_deleting_any_valid_entry(self) -> None:
        valid_sha, valid = self._entry("valid", age_seconds=24 * 60 * 60)
        bad_sha, bad = self._entry("bad", age_seconds=48 * 60 * 60)
        (bad / "manifest.json").write_text(
            json.dumps({"cache_format": 2, "source_sha": valid_sha}) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(reclaim.CacheSafetyError, "cache provenance mismatch"):
            self._run(
                minimum_free_kib=1000,
                capacity_probe=self._capacity_probe({valid_sha, bad_sha}),
            )
        self.assertTrue(valid.exists())
        self.assertTrue(bad.exists())

    def test_source_identity_ignores_calling_git_repository_environment(self) -> None:
        source_sha, entry = self._entry("isolated-git", age_seconds=24 * 60 * 60)
        caller_git_dir = self._git(Path.cwd(), "rev-parse", "--absolute-git-dir")

        original_git_dir = os.environ.get("GIT_DIR")
        try:
            os.environ["GIT_DIR"] = caller_git_dir
            self.assertEqual(reclaim._git_head(entry / "source"), source_sha)
        finally:
            if original_git_dir is None:
                os.environ.pop("GIT_DIR", None)
            else:
                os.environ["GIT_DIR"] = original_git_dir

    def test_unrepresented_live_qualifier_refuses_before_deletion(self) -> None:
        source_sha, entry = self._entry("old", age_seconds=24 * 60 * 60)

        with self.assertRaisesRegex(reclaim.CacheSafetyError, "no authoritative cache or harness lease"):
            self._run(
                minimum_free_kib=1000,
                capacity_probe=self._capacity_probe({source_sha}),
                process_probe=lambda: [reclaim.ProcessRecord(424242, "/bin/bash qualify-desktop-beta.sh")],
            )
        self.assertTrue(entry.exists())

    def test_active_prepare_lock_refuses_before_deletion(self) -> None:
        source_sha, entry = self._entry("old", age_seconds=24 * 60 * 60)
        (self.cache_root / f".{source_sha}.lock").mkdir()

        with self.assertRaisesRegex(reclaim.CacheSafetyError, "cache operation lock is active"):
            self._run(
                minimum_free_kib=1000,
                capacity_probe=self._capacity_probe({source_sha}),
            )
        self.assertTrue(entry.exists())

    def test_policy_is_bounded_and_never_touches_run_evidence(self) -> None:
        first_sha, first = self._entry("first", age_seconds=30 * 60 * 60)
        second_sha, second = self._entry("second", age_seconds=20 * 60 * 60)
        third_sha, third = self._entry("third", age_seconds=10 * 60 * 60)
        evidence = self.root / "desktop-beta-qualification/run/qualification-evidence.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text('{"immutable":true}\n', encoding="utf-8")
        initial = {first_sha, second_sha, third_sha}

        report = self._run(
            minimum_free_kib=1000,
            capacity_probe=self._capacity_probe(initial),
            max_entries=2,
        )

        self.assertEqual(report["status"], "failed")
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertTrue(third.exists())
        self.assertEqual(evidence.read_text(encoding="utf-8"), '{"immutable":true}\n')
        self.assertEqual(len(report["reclaim"]["deleted_entries"]), 2)

    def test_young_entry_and_symlinked_entry_are_never_reclaimed(self) -> None:
        young_sha, young = self._entry("young", age_seconds=60)
        target = self.root / "foreign-target"
        target.mkdir()
        symlink_sha = "f" * 40
        (self.cache_root / symlink_sha).symlink_to(target, target_is_directory=True)

        with self.assertRaisesRegex(reclaim.CacheSafetyError, "not an owned directory"):
            self._run(
                minimum_free_kib=1000,
                capacity_probe=self._capacity_probe({young_sha, symlink_sha}),
            )
        self.assertTrue(young.exists())
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
