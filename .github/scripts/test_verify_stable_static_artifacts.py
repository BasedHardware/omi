#!/usr/bin/env python3
"""Regression tests for retained-manifest stable static publication verification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / ".github/scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFIER = _load("verify_stable_static_artifacts.py")
REPAIR = _load("desktop_repair_installer.py")


def manifest() -> dict[str, object]:
    return {
        "release_id": "v0.12.72+12072-macos",
        "platform": "macos",
        "version": "0.12.72",
        "build_number": 12072,
        "source_sha": "a" * 40,
        "dmg_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.72%2B12072-macos/omi.dmg",
        "dmg_sha256": "b" * 64,
        "published_at": "2026-07-21T00:00:00Z",
    }


class StableStaticArtifactVerifierTests(unittest.TestCase):
    def test_accepts_exact_json_and_html_rendered_from_the_retained_manifest(self) -> None:
        bundle = REPAIR.build_repair_bundle(manifest(), "gs://updates-bucket")
        VERIFIER.verify(bundle["latest"], bundle["landing_page"], manifest(), "gs://updates-bucket")

    def test_rejects_stale_or_altered_identity_in_either_published_artifact(self) -> None:
        bundle = REPAIR.build_repair_bundle(manifest(), "gs://updates-bucket")
        mutations = (
            ({**bundle["latest"], "release_id": "v0.12.71+12071-macos"}, bundle["landing_page"]),
            ({**bundle["latest"], "installer_sha256": "c" * 64}, bundle["landing_page"]),
            (bundle["latest"], bundle["landing_page"].replace("omi.dmg", "latest.dmg")),
        )
        for latest, index in mutations:
            with self.subTest(mutation=latest != bundle["latest"]):
                with self.assertRaises(ValueError):
                    VERIFIER.verify(latest, index, manifest(), "gs://updates-bucket")

    def test_cli_reads_the_exact_downloaded_static_files(self) -> None:
        bundle = REPAIR.build_repair_bundle(manifest(), "gs://updates-bucket")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            manifest_path = path / "manifest.json"
            latest_path = path / "latest.json"
            index_path = path / "index.html"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            latest_path.write_text(json.dumps(bundle["latest"]), encoding="utf-8")
            index_path.write_text(bundle["landing_page"], encoding="utf-8")
            self.assertEqual(
                VERIFIER.main([
                    "--manifest", str(manifest_path), "--latest", str(latest_path), "--index", str(index_path),
                    "--bucket", "gs://updates-bucket",
                ]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
