#!/usr/bin/env python3
"""Regression contract for production-family Codemagic backend routing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/check-mobile-production-routing.py"
SPEC = importlib.util.spec_from_file_location("check_mobile_production_routing", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class MobileProductionRoutingContractTests(unittest.TestCase):
    def test_current_config_is_pinned(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_rejects_production_family_mutation_to_development_or_arbitrary_url(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        for bad in ("https://api.omi.dev/", "https://staging.example.test/"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "codemagic.yaml").write_text(
                    original.replace('API_BASE_URL=https://api.omi.me/', f'API_BASE_URL={bad}', 1), encoding="utf-8"
                )
                self.assertTrue(CHECKER.validate(root))

    def test_each_production_workflow_rejects_missing_wrong_or_conflicting_assignment(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        for workflow in CHECKER.WORKFLOWS:
            block = CHECKER._workflow_block(original, workflow)
            self.assertIsNotNone(block)
            assert block is not None
            for mutation in ("missing", "wrong", "conflicting"):
                with self.subTest(workflow=workflow, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    if mutation == "missing":
                        changed = block.replace("echo API_BASE_URL=https://api.omi.me/ >> .env\n", "", 1)
                    elif mutation == "wrong":
                        changed = block.replace(
                            "echo API_BASE_URL=https://api.omi.me/",
                            "echo API_BASE_URL=https://api.omi.dev/",
                            1,
                        )
                    else:
                        changed = block.replace(
                            "echo API_BASE_URL=https://api.omi.me/ >> .env",
                            "echo API_BASE_URL=https://api.omi.me/ >> .env\n          echo API_BASE_URL=https://staging.example.test/ >> .env",
                            1,
                        )
                    (root / "codemagic.yaml").write_text(original.replace(block, changed, 1), encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))

    def test_desktop_release_rejects_staging_or_duplicate_late_python_api_assignment(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        block = CHECKER._workflow_block(original, CHECKER.DESKTOP_WORKFLOW)
        self.assertIsNotNone(block)
        assert block is not None
        for mutation in ("staging", "duplicate_late"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if mutation == "staging":
                    changed = block.replace(
                        'OMI_PYTHON_API_URL: "https://api.omi.me"',
                        'OMI_PYTHON_API_URL: "https://staging.example.test"',
                        1,
                    )
                else:
                    changed = block.replace(
                        'OMI_PYTHON_API_URL: "https://api.omi.me"',
                        'OMI_PYTHON_API_URL: "https://api.omi.me"\n'
                        '        OMI_PYTHON_API_URL: "https://staging.example.test"',
                        1,
                    )
                (root / "codemagic.yaml").write_text(original.replace(block, changed, 1), encoding="utf-8")
                self.assertTrue(CHECKER.validate(root))

    def test_desktop_release_rejects_staging_or_duplicate_rust_api_assignment(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        block = CHECKER._workflow_block(original, CHECKER.DESKTOP_WORKFLOW)
        self.assertIsNotNone(block)
        assert block is not None
        for mutation in ("staging", "duplicate_late"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if mutation == "staging":
                    changed = block.replace(
                        'OMI_DESKTOP_API_URL: "https://desktop-backend-hhibjajaja-uc.a.run.app/"',
                        'OMI_DESKTOP_API_URL: "https://staging.example.test"',
                        1,
                    )
                else:
                    changed = block.replace(
                        'OMI_DESKTOP_API_URL: "https://desktop-backend-hhibjajaja-uc.a.run.app/"',
                        'OMI_DESKTOP_API_URL: "https://desktop-backend-hhibjajaja-uc.a.run.app/"\n'
                        '        OMI_DESKTOP_API_URL: "https://staging.example.test"',
                        1,
                    )
                (root / "codemagic.yaml").write_text(original.replace(block, changed, 1), encoding="utf-8")
                self.assertTrue(CHECKER.validate(root))

    def test_desktop_release_rejects_missing_wrong_or_duplicate_bundle_identity(self) -> None:
        original = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")
        block = CHECKER._workflow_block(original, CHECKER.DESKTOP_WORKFLOW)
        self.assertIsNotNone(block)
        assert block is not None
        canonical_assignment = 'BUNDLE_ID: "com.omi.computer-macos"'
        for mutation in ("missing", "wrong", "duplicate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative_path in (*CHECKER.LEGACY_BETA_ROUTING_PATHS, *CHECKER.REQUIRED_PRODUCTION_FRAGMENTS):
                    target = root / relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    text = (ROOT / relative_path).read_text(encoding="utf-8")
                    if relative_path == "codemagic.yaml":
                        if mutation == "missing":
                            changed = block.replace(canonical_assignment + "\n", "", 1)
                        elif mutation == "wrong":
                            changed = block.replace(
                                canonical_assignment,
                                'BUNDLE_ID: "com.omi.computer-macos.beta"',
                                1,
                            )
                        else:
                            changed = block.replace(
                                canonical_assignment,
                                canonical_assignment + '\n        BUNDLE_ID: "com.omi.computer-macos.beta"',
                                1,
                            )
                        text = original.replace(block, changed, 1)
                    target.write_text(text, encoding="utf-8")

                errors = CHECKER.validate(root)
                self.assertTrue(any("BUNDLE_ID" in error for error in errors), errors)

    def test_rejects_any_reintroduction_of_legacy_beta_or_staging_routing(self) -> None:
        for source_path in CHECKER.LEGACY_BETA_ROUTING_PATHS:
            for token in CHECKER.FORBIDDEN_ROUTING_TOKENS:
                with self.subTest(source_path=source_path, token=token), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for relative_path in CHECKER.LEGACY_BETA_ROUTING_PATHS:
                        target = root / relative_path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        text = (ROOT / relative_path).read_text(encoding="utf-8")
                        if relative_path == source_path:
                            text += f"\n// {token}\n"
                        target.write_text(text, encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))

    def test_rejects_mutated_desktop_production_identity_or_firestore_project(self) -> None:
        for source_path, fragments in CHECKER.REQUIRED_PRODUCTION_FRAGMENTS.items():
            for fragment in fragments:
                with self.subTest(source_path=source_path, fragment=fragment), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for relative_path in (*CHECKER.LEGACY_BETA_ROUTING_PATHS, *CHECKER.REQUIRED_PRODUCTION_FRAGMENTS):
                        target = root / relative_path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        text = (ROOT / relative_path).read_text(encoding="utf-8")
                        if relative_path == source_path:
                            text = text.replace(fragment, "MUTATED_PRODUCTION_IDENTITY")
                        target.write_text(text, encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))

    def test_rejects_separate_beta_or_divergent_production_family_identity(self) -> None:
        # INV-BETA-1: com.omi.computer-macos.beta is the single sanctioned second
        # production identity (side-by-side Omi Beta); only OTHER divergent
        # identities remain rejected.
        original = (ROOT / "desktop/macos/Desktop/Sources/AppBuild.swift").read_text(encoding="utf-8")
        mutations = {
            "divergent production-family identity": (
                '  static let betaProductionBundleIdentifier = "com.omi.computer-macos.beta"\n'
                '  static let productionFamilyBundleIdentifiers = [\n'
                '    productionBundleIdentifier, "com.omi.computer-macos.canary",\n'
                '  ]',
                "com.omi.computer-macos.canary",
            ),
        }

        for mutation, (declaration, rejected_identity) in mutations.items():
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative_path in (*CHECKER.LEGACY_BETA_ROUTING_PATHS, *CHECKER.REQUIRED_PRODUCTION_FRAGMENTS):
                    target = root / relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    text = (ROOT / relative_path).read_text(encoding="utf-8")
                    if relative_path == "desktop/macos/Desktop/Sources/AppBuild.swift":
                        text = original.replace(
                            'static let productionBundleIdentifier = "com.omi.computer-macos"',
                            'static let productionBundleIdentifier = "com.omi.computer-macos"\n' + declaration,
                            1,
                        )
                    target.write_text(text, encoding="utf-8")

                errors = CHECKER.validate(root)
                self.assertTrue(any(rejected_identity in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
