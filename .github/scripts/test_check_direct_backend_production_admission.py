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

    def test_listen_exporter_job_checks_out_exact_admitted_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in CHECKER.WORKFLOWS:
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            target = root / CHECKER.LISTEN_WORKFLOW
            text = target.read_text(encoding="utf-8")
            text = text.replace(CHECKER.LISTEN_EXPORTER_CHECKOUT, "ref: main", 1)
            target.write_text(text, encoding="utf-8")

            self.assertIn(
                f"{CHECKER.LISTEN_WORKFLOW} exporter job must check out the exact source admitted by helm-upgrade",
                CHECKER.validate(root),
            )

    def test_evidence_source_cannot_use_mutable_or_candidate_controls(self):
        # Mutate the actual checked-in pin/comment spelling, not an obsolete alias fixture.
        source = (ROOT / CHECKER.LISTEN_WORKFLOW).read_text()
        control = next(
            block
            for block in (
                CHECKER.LISTEN_EVIDENCE_CONTROL,
                CHECKER.LISTEN_EVIDENCE_CONTROL.replace('@v7', '@' + CHECKER.CHECKOUT_PIN),
                CHECKER.LISTEN_EVIDENCE_CONTROL.replace('@v7', '@' + CHECKER.CHECKOUT_PIN + ' # v7'),
            )
            if block in source
        )
        mutations = (
            (
                CHECKER.LISTEN_PINNED_CHECKOUT,
                CHECKER.LISTEN_PINNED_CHECKOUT.replace('inputs.expected_sha', 'inputs.branch'),
            ),
            (control, control.replace('github.workflow_sha', 'inputs.expected_sha')),
            (control, control.replace('.github/listen-evidence-control', '.')),
            (control, control.replace('persist-credentials: false', 'persist-credentials: true')),
        )
        for old, new in mutations:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, target)
                target = root / CHECKER.LISTEN_WORKFLOW
                text = target.read_text()
                self.assertIn(old, text)
                target.write_text(text.replace(old, new, 1))
                self.assertTrue(CHECKER.validate(root))

    def test_exact_pin_and_existing_alias_are_both_admitted(self):
        for spelling in ('v7', CHECKER.CHECKOUT_PIN):
            with self.subTest(spelling=spelling), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    text = (ROOT / relative).read_text().replace('@' + CHECKER.CHECKOUT_PIN + ' # v7', '@v7')
                    text = text.replace('@' + CHECKER.CHECKOUT_PIN, '@v7')
                    target.write_text(text.replace('actions/checkout@v7', 'actions/checkout@' + spelling))
                self.assertEqual(CHECKER.validate(root), [])

    def test_unknown_checkout_and_additional_sources_refuse(self):
        for relative in CHECKER.WORKFLOWS:
            for value in (
                'actions/checkout@' + '0' * 40,
                'actions/checkout@v6',
                'actions/checkout@main',
                'other/checkout@v7',
            ):
                with self.subTest(relative=relative, value=value), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for fixture in CHECKER.WORKFLOWS:
                        target = root / fixture
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(ROOT / fixture, target)
                    target = root / relative
                    target.write_text(target.read_text() + '\n      - uses: ' + value + '\n')
                    self.assertIn(f"{relative} has an unapproved checkout action or version", CHECKER.validate(root))
                    self.assertIn(
                        f"{relative} must not check out a second source after production admission",
                        CHECKER.validate(root),
                    )
            for spelling in ('v7', CHECKER.CHECKOUT_PIN):
                with self.subTest(relative=relative, spelling=spelling), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for fixture in CHECKER.WORKFLOWS:
                        target = root / fixture
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(ROOT / fixture, target)
                    target = root / relative
                    target.write_text(
                        target.read_text()
                        + '\n      - uses: actions/checkout@'
                        + spelling
                        + '\n        with:\n          ref: main\n'
                    )
                    self.assertIn(
                        f"{relative} must not check out a second source after production admission",
                        CHECKER.validate(root),
                    )

    def test_control_shaped_comment_cannot_mask_an_additional_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in CHECKER.WORKFLOWS:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            target = root / CHECKER.LISTEN_WORKFLOW
            text = target.read_text()
            # A valid multiline job name is data, not an isolated checkout step.
            fake = '    name: |\n      # ' + CHECKER.CONTROL_CHECKOUT + '\n'
            text = text.replace('  helm-upgrade:\n', '  helm-upgrade:\n' + fake, 1)
            text += (
                '\n      - uses: actions/checkout@' + CHECKER.CHECKOUT_PIN + '\n        with:\n          ref: main\n'
            )
            target.write_text(text)
            self.assertIn(
                f"{CHECKER.LISTEN_WORKFLOW} must not check out a second source after production admission",
                CHECKER.validate(root),
            )

    def test_scalar_contract_cannot_replace_real_control_checkout(self):
        for style in ('|', '>'):
            with self.subTest(style=style), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, target)
                target = root / CHECKER.LISTEN_WORKFLOW
                text = target.read_text()
                start = text.index('      - name: Checkout trusted overlay evidence controls')
                end = text.index('      - name: Reconstruct evidence runtime', start)
                text = text[:start] + text[end:]
                fake = '    name: ' + style + '\n      ' + CHECKER.LISTEN_EVIDENCE_CONTROL + '\n'
                text = text.replace('  helm-upgrade:\n', '  helm-upgrade:\n' + fake, 1)
                target.write_text(text)
                self.assertIn(
                    f"{CHECKER.LISTEN_WORKFLOW} evidence controls must use immutable workflow source in their isolated path",
                    CHECKER.validate(root),
                )

    def test_evidence_commands_require_real_trusted_steps(self):
        source = (ROOT / CHECKER.LISTEN_WORKFLOW).read_text()
        mutations = (
            ('.github/listen-evidence-control/.github/scripts/listen_runtime.py', '.github/scripts/listen_runtime.py'),
            (
                '.github/listen-evidence-control/.github/scripts/listen_overlay_evidence.py job',
                '.github/scripts/listen_overlay_evidence.py job',
            ),
            (
                '      - name: Reconstruct evidence runtime before credentials',
                '      - working-directory: candidate\n        name: Reconstruct evidence runtime before credentials',
            ),
            (
                '      - name: Reconstruct evidence runtime before credentials',
                '      - env:\n          PYTHONPATH: candidate\n        name: Reconstruct evidence runtime before credentials',
            ),
            (
                '      - name: Produce private-overlay effect receipt without mutation',
                '      - shell: bash -c \"candidate\"\n        name: Produce private-overlay effect receipt without mutation',
            ),
        )
        for old, new in mutations:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, target)
                self.assertIn(old, source)
                (root / CHECKER.LISTEN_WORKFLOW).write_text(source.replace(old, new, 1))
                self.assertIn(
                    f"{CHECKER.LISTEN_WORKFLOW} evidence commands must execute isolated immutable controls in order",
                    CHECKER.validate(root),
                )

    def test_required_evidence_steps_cannot_continue_after_failure(self):
        source = (ROOT / CHECKER.LISTEN_WORKFLOW).read_text()
        for name in (
            'Reconstruct evidence runtime before credentials',
            'Produce private-overlay effect receipt without mutation',
        ):
            for value in ('true', 'false', '${{ always() }}'):
                with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for relative in CHECKER.WORKFLOWS:
                        target = root / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(ROOT / relative, target)
                    old = '      - name: ' + name + '\n'
                    self.assertEqual(source.count(old), 1)
                    text = source.replace(old, old + '        continue-on-error: ' + value + '\n', 1)
                    (root / CHECKER.LISTEN_WORKFLOW).write_text(text)
                    self.assertIn(
                        f"{CHECKER.LISTEN_WORKFLOW} evidence commands must execute isolated immutable controls in order",
                        CHECKER.validate(root),
                    )

    def test_controls_must_precede_real_bootstrap_and_duplicate_keys_refuse(self):
        source = (ROOT / CHECKER.LISTEN_WORKFLOW).read_text()
        start = source.index('      - name: Checkout trusted overlay evidence controls')
        middle = source.index('      - name: Reconstruct evidence runtime', start)
        end = source.index('      - name: Install Helm', middle)
        reordered = source[:start] + source[middle:end] + source[start:middle] + source[end:]
        duplicate = source.replace(
            '          path: .github/listen-evidence-control',
            '          path: candidate\n          path: .github/listen-evidence-control',
            1,
        )
        for text in (reordered, duplicate):
            with self.subTest(text=text[start : start + 80]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, target)
                (root / CHECKER.LISTEN_WORKFLOW).write_text(text)
                self.assertIn(
                    f"{CHECKER.LISTEN_WORKFLOW} evidence commands must execute isolated immutable controls in order",
                    CHECKER.validate(root),
                )

    def test_wrong_pin_and_firestore_control_contracts_refuse(self):
        for replacement in ('actions/checkout@' + 'f' * 40, 'actions/checkout@v7x'):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, target)
                target = root / CHECKER.LISTEN_WORKFLOW
                text = target.read_text()
                self.assertIn('actions/checkout@' + CHECKER.CHECKOUT_PIN, text)
                target.write_text(text.replace('actions/checkout@' + CHECKER.CHECKOUT_PIN, replacement, 1))
                self.assertIn(
                    f"{CHECKER.LISTEN_WORKFLOW} has an unapproved checkout action or version", CHECKER.validate(root)
                )
        for old, new in (
            ('github.workflow_sha', 'inputs.expected_sha'),
            ('.github/firestore-workflow', '.'),
            ('persist-credentials: false', 'persist-credentials: true'),
        ):
            with self.subTest(new=new), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in CHECKER.WORKFLOWS:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, target)
                target = root / CHECKER.LISTEN_WORKFLOW
                text = target.read_text()
                self.assertIn(CHECKER.CONTROL_CHECKOUT, text)
                target.write_text(text.replace(CHECKER.CONTROL_CHECKOUT, CHECKER.CONTROL_CHECKOUT.replace(old, new), 1))
                self.assertTrue(CHECKER.validate(root))

    def test_listen_rejects_missing_or_weakened_exact_control_guard(self) -> None:
        text = (ROOT / CHECKER.LISTEN_WORKFLOW).read_text(encoding="utf-8")
        pin = CHECKER.LISTEN_PINNED_CHECKOUT
        step = CHECKER.LISTEN_EXACT_CONTROL_STEP
        mutations = (
            (pin, pin.replace("github.sha", "inputs.control_sha")),
            (pin, pin.replace("github.sha", "'main'")),
            (step, "name: Bypass control verification\n        run: true"),
            (step, step.replace("        shell: bash", "        continue-on-error: true\n        shell: bash")),
            (step, step.replace(' || "$CONTROL_SHA" != "$(git rev-parse HEAD)"', "")),
            (step, step.replace('"$CONTROL_SHA" != "$GITHUB_SHA" || ', "")),
            (step, "name: Authenticate before guard\n        run: true\n      - " + step),
        )
        for old, new in mutations:
            with self.subTest(replacement=new):
                self.assertIn(old, text)
                self.assertNotEqual(old, new)
                self.assertIn(
                    f"{CHECKER.LISTEN_WORKFLOW} must pin the dispatch checkout and verify exact control before deployment",
                    CHECKER.validate_listen_control_admission(text.replace(old, new, 1)),
                )

    def test_listen_preserves_legacy_checkout_and_containment(self) -> None:
        text = (ROOT / CHECKER.LISTEN_WORKFLOW).read_text(encoding="utf-8")
        for old, new, diagnostic in (
            ("      control_sha:\n", "      renamed_control_sha:\n", "must expose the optional control_sha string input"),
            (CHECKER.LISTEN_PINNED_CHECKOUT, CHECKER.LISTEN_PINNED_CHECKOUT.replace("'main'", "github.sha"),
             "must pin the dispatch checkout and verify exact control before deployment"),
            (CHECKER.LISTEN_LEGACY_ANCESTRY, 'if [[ "$EXPECTED_SHA" != "$CHECKED_OUT_SHA" ]]; then',
             "must retain expected_sha containment for legacy admission"),
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertIn(old, text)
                self.assertIn(
                    f"{CHECKER.LISTEN_WORKFLOW} {diagnostic}",
                    CHECKER.validate_listen_control_admission(text.replace(old, new, 1)),
                )

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
        replace_all = {"fresh_origin"}
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
                    if name == "caller_ref" and relative == CHECKER.PUSHER_WORKFLOW:
                        expected = CHECKER.PUSHER_CHECKOUT
                    if name == "caller_ref" and relative == CHECKER.LISTEN_WORKFLOW:
                        expected = CHECKER.LISTEN_PINNED_CHECKOUT
                    self.assertIn(expected, text)
                    if name in replace_all:
                        target.write_text(text.replace(expected, replacement), encoding="utf-8")
                    else:
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
