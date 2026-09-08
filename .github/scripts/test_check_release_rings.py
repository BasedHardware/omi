from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check_release_rings.py")
SPEC = importlib.util.spec_from_file_location("check_release_rings", MODULE_PATH)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class ReleaseRingGuardTests(unittest.TestCase):
    """Guard the one-action production backend release contract.

    Written against stdlib ``unittest`` so the manifest command
    ``python3 .github/scripts/test_check_release_rings.py`` executes the cases.
    A pytest-only module exits 0 here without running anything, which is
    indistinguishable from a passing guard.
    """

    def setUp(self) -> None:
        self._real_root = checker.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        checker.ROOT = self._real_root
        self._tmp.cleanup()

    def _stage_release_sources(self) -> None:
        """Copy every checked-in backend release source into the sandbox root."""
        for relative in checker.BACKEND_RELEASE_SOURCES:
            destination = self.tmp_path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._real_root / relative, destination)
        composite_action = self._real_root / checker.DEPLOY_BACKEND_STACK_ACTION
        if composite_action.exists():
            destination = self.tmp_path / checker.DEPLOY_BACKEND_STACK_ACTION
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(composite_action, destination)
        checker.ROOT = self.tmp_path

    def _deploy_workflow(self) -> Path:
        return self.tmp_path / ".github/workflows/gcp_backend.yml"

    def test_checked_in_production_release_vector_is_guarded(self) -> None:
        self.assertEqual(checker.check(), [])

    def test_canonical_backend_workflow_is_the_only_production_release_authority(self) -> None:
        """The normal production path must not depend on a record/ring control plane."""
        workflow = self._deploy_workflow()
        workflow.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._real_root / ".github/workflows/gcp_backend.yml", workflow)
        composite_action = self._real_root / checker.DEPLOY_BACKEND_STACK_ACTION
        if composite_action.exists():
            destination = self.tmp_path / checker.DEPLOY_BACKEND_STACK_ACTION
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(composite_action, destination)
        checker.ROOT = self.tmp_path

        self.assertEqual(checker.check(), [])

    def test_beta_backend_dispatch_is_rejected(self) -> None:
        self._stage_release_sources()
        deploy_path = self._deploy_workflow()
        deploy_path.write_text(
            deploy_path.read_text(encoding="utf-8") + "\n# release-ring deployment control plane\n",
            encoding="utf-8",
        )

        self.assertTrue(
            any("backend release-ring deployment control plane is forbidden" in error for error in checker.check())
        )

    def test_dispatch_release_id_cannot_be_interpolated_into_shell(self) -> None:
        self._stage_release_sources()
        deploy_path = self._deploy_workflow()
        deploy_path.write_text(
            deploy_path.read_text(encoding="utf-8").replace(
                "name: Deploy Backend to Cloud RUN", "name: Deploy Backend to Cloud RUN\n# RELEASE_RECORDS_BUCKET"
            ),
            encoding="utf-8",
        )

        self.assertTrue(any("obsolete release binding" in error for error in checker.check()))

    def _composite_action_path(self) -> Path:
        return self.tmp_path / checker.DEPLOY_BACKEND_STACK_ACTION

    def test_serving_release_vector_must_follow_traffic_promotion(self) -> None:
        self._stage_release_sources()
        target = self._composite_action_path()
        self.assertTrue(target.exists(), 'release-vector canary requires the staged deploy composite action')
        target.write_text(
            target.read_text(encoding="utf-8").replace(
                "- name: Verify serving backend release vector",
                "- name: Verify release vector before traffic promotion",
            ),
            encoding="utf-8",
        )

        self.assertTrue(
            any("serving release-vector verification must follow traffic promotion" in error for error in checker.check())
        )

    def test_staged_workflow_control_verifier_remains_required(self) -> None:
        self._stage_release_sources()
        target = self._composite_action_path()
        self.assertTrue(target.exists(), 'release-vector canary requires the staged deploy composite action')
        target.write_text(
            target.read_text(encoding="utf-8").replace(
                "$DEPLOY_CONTROL_SCRIPTS/verify_backend_release_vector.py",
                "$DEPLOY_CONTROL_SCRIPTS/not-the-release-vector-verifier.py",
            ),
            encoding="utf-8",
        )

        self.assertTrue(any("canonical release-vector verifier" in error for error in checker.check()))

    def test_commented_composite_reference_does_not_expand_contract(self) -> None:
        self._stage_release_sources()
        deploy_path = self._deploy_workflow()
        deploy_path.write_text(
            deploy_path.read_text(encoding="utf-8").replace(
                "        uses: ./.github/actions/deploy-backend-stack",
                "        # uses: ./.github/actions/deploy-backend-stack",
            ),
            encoding="utf-8",
        )
        self._composite_action_path().write_text(
            self._composite_action_path().read_text(encoding="utf-8").replace(
                "Verify serving backend release vector",
                "Verify release vector before traffic promotion",
            ),
            encoding="utf-8",
        )

        self.assertTrue(
            any("serving release-vector verification must follow traffic promotion" in error for error in checker.check())
        )

    def test_shell_text_that_mentions_a_composite_is_not_an_action_reference(self) -> None:
        self._stage_release_sources()
        deploy_path = self._deploy_workflow()
        deploy_path.write_text(
            deploy_path.read_text(encoding="utf-8").replace(
                "        uses: ./.github/actions/deploy-backend-stack",
                "        run: \"echo 'uses: ./.github/actions/deploy-backend-stack'\"",
            ),
            encoding="utf-8",
        )

        self.assertTrue(checker.check())


if __name__ == "__main__":
    unittest.main()
