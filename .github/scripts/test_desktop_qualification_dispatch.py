#!/usr/bin/env python3
"""Static contract for immutable candidate qualification dispatch and checkout."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CODEMAGIC = ROOT / "codemagic.yaml"
QUALIFIER = ROOT / ".github/workflows/desktop_qualify_beta.yml"


def validate(root: Path) -> list[str]:
    codemagic = (root / "codemagic.yaml").read_text(encoding="utf-8")
    qualifier = (root / ".github/workflows/desktop_qualify_beta.yml").read_text(encoding="utf-8")
    errors: list[str] = []
    dispatch = codemagic.split("gh workflow run desktop_qualify_beta.yml", 1)[1].split("then", 1)[0]
    if '--ref "$CM_TAG"' not in dispatch:
        errors.append("Codemagic must dispatch qualification at the immutable candidate tag ref")
    if "ref: ${{ github.sha }}" not in qualifier:
        errors.append("qualification must check out the immutable event SHA, never mutable main")
    if "ref: main" in qualifier:
        errors.append("qualification must not check out mutable main")
    if "CHECKOUT_SHA=$(git rev-parse HEAD)" not in qualifier or "EVENT_SHA: ${{ github.sha }}" not in qualifier:
        errors.append("candidate validation must compare the fetched candidate tag against the checked-out event SHA")
    return errors


class DesktopQualificationDispatchTests(unittest.TestCase):
    def test_current_configuration_uses_the_candidate_tag_and_event_sha(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_mutations_drop_tag_ref_or_reintroduce_mutable_checkout(self) -> None:
        codemagic = CODEMAGIC.read_text(encoding="utf-8")
        qualifier = QUALIFIER.read_text(encoding="utf-8")
        mutations = (
            (codemagic.replace('--ref "$CM_TAG" \\\n              ', "", 1), qualifier),
            (codemagic, qualifier.replace("ref: ${{ github.sha }}", "ref: main", 1)),
            (codemagic, qualifier.replace("CHECKOUT_SHA=$(git rev-parse HEAD)", "CHECKOUT_SHA=$(git rev-parse \"$RELEASE_TAG\")", 1)),
        )
        for changed_codemagic, changed_qualifier in mutations:
            with self.subTest(mutation=changed_codemagic != codemagic), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".github/workflows").mkdir(parents=True)
                (root / "codemagic.yaml").write_text(changed_codemagic, encoding="utf-8")
                (root / ".github/workflows/desktop_qualify_beta.yml").write_text(changed_qualifier, encoding="utf-8")
                self.assertTrue(validate(root))


if __name__ == "__main__":
    unittest.main()
