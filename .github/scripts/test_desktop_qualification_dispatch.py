#!/usr/bin/env python3
"""Static contract for immutable candidate qualification dispatch and checkout."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CODEMAGIC = ROOT / "codemagic.yaml"
QUALIFIER = ROOT / ".github/workflows/desktop_qualify_beta.yml"
BETA_PROMOTION = ROOT / ".github/workflows/desktop_promote_beta.yml"


def validate(root: Path) -> list[str]:
    codemagic = (root / "codemagic.yaml").read_text(encoding="utf-8")
    qualifier = (root / ".github/workflows/desktop_qualify_beta.yml").read_text(encoding="utf-8")
    beta_promotion = (root / ".github/workflows/desktop_promote_beta.yml").read_text(encoding="utf-8")
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
    if "gh workflow run desktop_promote_beta.yml" in qualifier:
        errors.append("qualification must not dispatch beta promotion before its run has completed")

    for fragment, message in (
        (
            '  workflow_run:\n    workflows: ["Qualify Desktop Beta Candidate"]\n    types: [completed]',
            "automatic beta promotion must be triggered only by completed qualification runs",
        ),
        (
            "github.event.workflow_run.conclusion == 'success'",
            "automatic beta promotion must require a successful qualification conclusion",
        ),
        (
            "github.event.workflow_run.event == 'workflow_dispatch'",
            "automatic beta promotion must require the trusted workflow_dispatch qualifier",
        ),
        (
            "github.event.workflow_run.repository.full_name == github.repository",
            "automatic beta promotion must require a same-repository workflow run",
        ),
        (
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "automatic beta promotion must reject fork-sourced qualification",
        ),
        (
            "github.event.workflow_run.path == '.github/workflows/desktop_qualify_beta.yml'",
            "automatic beta promotion must require the desktop qualification workflow path",
        ),
        (
            "RELEASE_TAG: ${{ github.event_name == 'workflow_run' && github.event.workflow_run.head_branch || inputs.release_tag }}",
            "automatic beta promotion must derive its release tag from the completed qualifier",
        ),
        (
            "QUALIFICATION_RUN_ID: ${{ github.event_name == 'workflow_run' && github.event.workflow_run.id || inputs.qualification_run_id }}",
            "automatic beta promotion must use the completed qualifier run ID",
        ),
        (
            'test "$(jq -r .head_branch <<<"$run")" = "$RELEASE_TAG"',
            "automatic beta promotion must bind qualification evidence to the release tag",
        ),
        (
            'test "$(jq -r .head_sha <<<"$run")" = "$TARGET_SHA"',
            "automatic beta promotion must bind qualification evidence to the exact tag SHA",
        ),
        (
            'test "$QUALIFICATION_RUN_ID" = "$QUALIFIER_EVENT_RUN_ID"',
            "automatic beta promotion must use the triggering completed qualification run",
        ),
        (
            'test "$QUALIFIER_EVENT_HEAD_SHA" = "$TARGET_SHA"',
            "automatic beta promotion must bind the triggering qualifier SHA to the release tag",
        ),
    ):
        if fragment not in beta_promotion:
            errors.append(message)
    return errors


class DesktopQualificationDispatchTests(unittest.TestCase):
    def test_current_configuration_uses_the_candidate_tag_and_completed_qualifier(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_mutations_drop_tag_ref_or_reintroduce_mutable_checkout(self) -> None:
        codemagic = CODEMAGIC.read_text(encoding="utf-8")
        qualifier = QUALIFIER.read_text(encoding="utf-8")
        beta_promotion = BETA_PROMOTION.read_text(encoding="utf-8")
        mutations = (
            (codemagic.replace('--ref "$CM_TAG" \\\n              ', "", 1), qualifier, beta_promotion),
            (codemagic, qualifier.replace("ref: ${{ github.sha }}", "ref: main", 1), beta_promotion),
            (
                codemagic,
                qualifier.replace("CHECKOUT_SHA=$(git rev-parse HEAD)", "CHECKOUT_SHA=$(git rev-parse \"$RELEASE_TAG\")", 1),
                beta_promotion,
            ),
            (codemagic, qualifier + '\n          gh workflow run desktop_promote_beta.yml\n', beta_promotion),
            (
                codemagic,
                qualifier,
                beta_promotion.replace("github.event.workflow_run.conclusion == 'success'", "github.event.workflow_run.conclusion == 'failure'", 1),
            ),
            (
                codemagic,
                qualifier,
                beta_promotion.replace(
                    "github.event.workflow_run.head_repository.full_name == github.repository",
                    "github.event.workflow_run.head_repository.full_name == 'attacker/omi'",
                    1,
                ),
            ),
            (
                codemagic,
                qualifier,
                beta_promotion.replace('test "$(jq -r .head_sha <<<"$run")" = "$TARGET_SHA"', 'test "$(jq -r .head_sha <<<"$run")" = main', 1),
            ),
        )
        for changed_codemagic, changed_qualifier, changed_beta_promotion in mutations:
            with self.subTest(mutation=changed_codemagic != codemagic), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".github/workflows").mkdir(parents=True)
                (root / "codemagic.yaml").write_text(changed_codemagic, encoding="utf-8")
                (root / ".github/workflows/desktop_qualify_beta.yml").write_text(changed_qualifier, encoding="utf-8")
                (root / ".github/workflows/desktop_promote_beta.yml").write_text(
                    changed_beta_promotion, encoding="utf-8"
                )
                self.assertTrue(validate(root))


if __name__ == "__main__":
    unittest.main()
