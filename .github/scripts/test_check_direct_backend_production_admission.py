#!/usr/bin/env python3
"""Static inventory for direct production backend workflow source admission."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/scripts/check-direct-backend-production-admission.py"
SPEC = importlib.util.spec_from_file_location("check_direct_backend_production_admission", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class DirectBackendProductionAdmissionTests(unittest.TestCase):
    def test_inventory_is_admitted_and_uses_checked_out_source_identity(self) -> None:
        self.assertEqual(CHECKER.validate(ROOT), [])

    def test_each_direct_writer_rejects_each_source_admission_mutation_in_a_fresh_fixture(self) -> None:
        mutations = {
            "caller_ref": (CHECKER.CHECKOUT, "ref: ${{ github.event.inputs.branch }}"),
            "fresh_origin": (CHECKER.ORIGIN_MAIN_FETCH, "git fetch --no-tags origin main"),
            "ancestry": (CHECKER.ANCESTRY_GUARD, "git merge-base --is-ancestor HEAD origin/main"),
            "head_identity": (CHECKER.HEAD_IDENTITY, "CHECKED_OUT_SHA=${GITHUB_SHA}"),
            "image_identity": (CHECKER.IMAGE_IDENTITY, "IMAGE_TAG=${GITHUB_SHA::7}"),
            "diagnostic": (CHECKER.DIAGNOSTIC, "ERROR: source admission failed"),
            "second_checkout": ("\n", "\n      - uses: actions/checkout@v7\n"),
            "late_image_override": ("\n", "\n      - name: late image override\n        run: IMAGE_TAG=latest\n"),
            "late_persistent_image_override": (
                "\n",
                "\n      - name: late persistent image override\n"
                "        run: echo \"IMAGE_TAG=latest\" >> \"$GITHUB_ENV\"\n",
            ),
        }
        for relative in CHECKER.WORKFLOWS:
            for name, (expected, replacement) in mutations.items():
                with self.subTest(workflow=relative, mutation=name), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for fixture_relative in CHECKER.WORKFLOWS:
                        source = ROOT / fixture_relative
                        target = root / fixture_relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                    target = root / relative
                    text = target.read_text(encoding="utf-8")
                    self.assertIn(expected, text)
                    target.write_text(text.replace(expected, replacement, 1), encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))

    def test_rejects_multiple_image_tag_authorities_and_late_checkouts(self) -> None:
        mutations = (
            "      - name: second image authority\n        run: IMAGE_TAG=deadbee\n",
            "      - uses: actions/checkout@v7\n        with:\n          ref: main\n",
        )
        for relative in CHECKER.WORKFLOWS:
            for mutation in mutations:
                with self.subTest(workflow=relative, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for fixture_relative in CHECKER.WORKFLOWS:
                        source = ROOT / fixture_relative
                        target = root / fixture_relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                    target = root / relative
                    target.write_text(target.read_text(encoding="utf-8") + "\n" + mutation, encoding="utf-8")
                    self.assertTrue(CHECKER.validate(root))

    def test_gateway_rejects_release_sha_admission_bypasses(self) -> None:
        mutations = (
            (
                CHECKER.GATEWAY_RELEASE_SHA_INPUT,
                "",
                "gateway deploy must expose a production-only release_sha input",
            ),
            (
                '[[ ! "$DEPLOY_SHA" =~ $sha_pattern || "$DEPLOY_SHA" == "0000000000000000000000000000000000000000" ]]',
                '[[ -z "$DEPLOY_SHA" ]]',
                "gateway production admission must reject malformed or missing release_sha",
            ),
            (
                'git merge-base --is-ancestor "$DEPLOY_SHA" "$main_sha"',
                'git merge-base --is-ancestor HEAD "$main_sha"',
                "gateway production admission must require release_sha to be merged into fresh main",
            ),
            (
                ".github/scripts/verify_backend_release_admission.py",
                "true # proof bypass",
                "gateway production admission must verify the Release Eligibility proof",
            ),
            (
                "--require-first-attempt",
                "",
                "gateway production admission must reject Release Eligibility reruns",
            ),
            (
                'git checkout --detach "$DEPLOY_SHA"',
                'git checkout --detach main',
                "gateway production admission must check out the admitted SHA",
            ),
        )
        for old, new, expected in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    source = ROOT / relative
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                target = root / CHECKER.GATEWAY_WORKFLOW
                text = target.read_text(encoding="utf-8")
                self.assertIn(old, text)
                target.write_text(text.replace(old, new, 1), encoding="utf-8")
                self.assertIn(expected, CHECKER.validate(root))

    def test_gateway_rejects_break_glass_hatch_removals(self) -> None:
        mutations = (
            (
                "        description: 'Break-glass: deploy without a Release Eligibility proof (still requires a merged main SHA)'",
                "        description: 'removed'",
                "gateway deploy must expose a skip_eligibility_proof break-glass input",
            ),
            (
                '!= "deploy-without-proof"',
                '!= "nothing"',
                "gateway break-glass must require an explicit confirm string",
            ),
            (
                "requires a non-empty break_glass_reason",
                "requires nothing",
                "gateway break-glass must require a non-empty reason",
            ),
            (
                "  record_break_glass:",
                "  removed_break_glass:",
                "gateway break-glass use must be recorded by a dedicated job",
            ),
            (
                "--label release-gate-failure",
                "--label removed",
                "gateway break-glass tracking issue must carry the release-gate-failure label",
            ),
        )
        for old, new, expected in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    source = ROOT / relative
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                target = root / CHECKER.GATEWAY_WORKFLOW
                text = target.read_text(encoding="utf-8")
                self.assertIn(old, text)
                target.write_text(text.replace(old, new, 1), encoding="utf-8")
                self.assertIn(expected, CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()
