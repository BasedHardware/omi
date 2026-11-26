#!/usr/bin/env python3
"""Check workflow sequencing against the guarded rehearsal API fake."""

import copy
import unittest
from unittest.mock import patch

import pusher_image_only as control
import pusher_image_rehearsal as helper
import test_pusher_image_rehearsal as fixture


class ProtectedServer(fixture.Server, control.ProtectedCluster):
    pass


class ImageOnlyTest(unittest.TestCase):
    def setUp(self):
        model = fixture.RehearsalTest()
        model.setUp()
        self.live = ProtectedServer("live")
        self.isolated = model.isolated
        for server in (self.live, self.isolated):
            server.target["spec"]["template"]["spec"]["containers"][1]["image"] = control.BASELINE
            server.target["metadata"]["generation"] = 1

        self.proof = model.proof | {"prior_image": control.BASELINE}
        self.rehearsal = helper.Rehearsal(self.live, self.isolated, self.proof)
        receipt = self.result("rehearse")
        self.rehearsal.rehearse(receipt)
        receipt["status"] = "PASS"
        self.packet = {"rehearsal_receipt": receipt, "reviewed_inverse_rehearsal": "approved-inverse"}
        self.live.requests.clear()
        self.baseline = copy.deepcopy(self.live.target)
        self.config = copy.deepcopy(self.live.config)
        self.command = self.enterContext(patch.object(control, "run", return_value=""))
        self.enterContext(patch.object(control, "check_provenance", return_value={"qualified": True}))
        self.ready = self.enterContext(
            patch.object(
                control,
                "verify_ready",
                return_value={"deployment_uid": "target-live", "generation": 1, "ready_replicas": 1},
            )
        )
        self.canary = self.enterContext(
            patch.object(control, "check_canary", side_effect=lambda *args: args[-1].update(canary_run_id=12))
        )
        self.preview = self.enterContext(patch.object(control, "check_reviewed_preview"))
        self.enterContext(patch.object(control, "verify_canary_cleanup"))
        self.enterContext(patch.object(control, "check_capacity"))

    def result(self, mode):
        return {"mode": mode, "workflow_sha": "a" * 40, **helper.proof_receipt_fields(self.proof)}

    def test_preview_is_read_only_and_requires_both_fixes(self):
        result = self.result("preview")
        control.execute("preview", self.packet, self.rehearsal, result)
        admitted_fix_calls = [call.args[0][3] for call in self.command.call_args_list]
        self.assertEqual(admitted_fix_calls, list(control.REQUIRED_FIXES))
        self.assertEqual(result["forward_server_dry_run"], "PASS")
        self.assertEqual(self.live.target, self.baseline)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_missing_fix_or_canary_blocks_before_any_patch(self):
        self.command.side_effect = helper.Refused("required_gcs_fix_missing")
        with self.assertRaisesRegex(helper.Refused, "required_gcs_fix_missing"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.command.side_effect = None
        self.canary.side_effect = helper.Refused("preserved_canary_review_missing")
        with self.assertRaisesRegex(helper.Refused, "preserved_canary_review_missing"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.assertEqual(self.live.requests, [])

    def test_failed_review_prevents_persistent_patch(self):
        self.preview.side_effect = helper.Refused("reviewed_forward_preview_missing")
        with self.assertRaisesRegex(helper.Refused, "reviewed_forward_preview_missing"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.assertEqual(self.live.target, self.baseline)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_canary_checks_preserved_deployment_and_uses_dry_run_only(self):
        self.canary.side_effect = None
        self.canary.return_value = {"receipt": "canary"}
        with patch.object(control, "verify_canary_live") as verify:
            control.execute("canary", self.packet, self.rehearsal, self.result("canary"))
        _, admitted, receipt = verify.call_args.args
        self.assertEqual(helper.current_image(admitted), fixture.CANDIDATE)
        self.assertEqual(receipt, {"receipt": "canary"})
        self.assertEqual(self.live.target, self.baseline)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_promote_verifies_exact_live_inverse_then_rollback_restores_baseline(self):
        forward = self.result("promote")
        control.execute("promote", self.packet, self.rehearsal, forward)
        self.assertEqual(forward["live_inverse_server_dry_run"], "PASS")
        self.assertEqual(forward["serving_image"], fixture.CANDIDATE)
        self.assertEqual(self.live.config, self.config)

        self.ready.reset_mock()
        self.command.return_value = control.BASELINE.split("@")[1]
        reverse = self.result("rollback")
        control.execute("rollback", self.packet, self.rehearsal, reverse)
        self.assertEqual(reverse["live_inverse_server_dry_run"], "PASS")
        self.assertEqual(reverse["serving_image"], control.BASELINE)
        self.assertEqual(helper.comparable(self.live.target), helper.comparable(self.baseline))
        self.assertEqual(self.live.config, self.config)
        self.ready.assert_called_once()
        self.assertEqual(self.ready.call_args.args[2], control.BASELINE)
        patches = [ops for dry, ops in self.live.requests if not dry]
        self.assertEqual([ops[-1]["value"] for ops in patches], [fixture.CANDIDATE, control.BASELINE])
        self.assertTrue(all([op["op"] for op in ops] == ["test"] * 4 + ["replace"] for ops in patches))

    def test_failed_post_patch_inverse_keeps_candidate_for_reconciliation(self):
        def reject_inverse(old, proposed, dry):
            if dry and helper.current_image(old) == fixture.CANDIDATE:
                proposed["spec"]["template"]["spec"]["containers"][1]["env"] = []

        self.live.admit = reject_inverse
        result = self.result("promote")
        with self.assertRaisesRegex(helper.Refused, "admission_changed_more_than_image"):
            control.execute("promote", self.packet, self.rehearsal, result)
        self.assertEqual(helper.current_image(self.live.target), fixture.CANDIDATE)
        self.assertIn("patch_observed", result)
        self.assertNotIn("serving_image", result)
        self.assertEqual(sum(not dry for dry, _ in self.live.requests), 1)


if __name__ == "__main__":
    unittest.main()
