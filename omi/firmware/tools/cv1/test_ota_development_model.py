"""Proposed contract simulations, not MCUboot/TrustZone/device proof."""
import json
import unittest
from dataclasses import replace
from pathlib import Path
from ota_development_model import State, step, check_regions, Rejected


class OtaDesignTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).parent / "ota-development-plan.json").read_text())
        self.owner = step(State(), "enroll", physical=True, authorized=True)

    def upload(self, state=None, **changes):
        args = dict(authorized=True, signature=True, board=True, abi=True, size=248516, digest="candidate")
        args.update(changes)
        return step(state or self.owner, "upload", **args)

    def trial(self):
        return step(step(self.upload(), "activate"), "copy_complete")

    def test_exact_flash_budgets(self):
        for option in self.plan["options"].values():
            check_regions(option["internal"], 0, 1048576)
            check_regions(option["external"], 0, 2097152)

    def test_exact_normal_ram_budget_and_observed_headroom(self):
        check_regions(self.plan["normal_ram"], 0x20000000, 0x20080000, 8192)
        app = self.plan["normal_ram"][2]
        self.assertEqual(app[2] - app[1] - self.plan["observed_stock_allocated_ram_extent_bytes"], 48936)

    def test_overlap_or_boolean_address_rejected(self):
        for value in [4095, True]:
            with self.assertRaises(Rejected): check_regions([["a", 0, 4096], ["b", value, 8192]], 0, 8192)

    def test_zero_alignment_and_unaligned_budget_rejected(self):
        with self.assertRaises(Rejected): check_regions([["a", 0, 4096]], 0, 4096, alignment=0)
        with self.assertRaises(Rejected): check_regions([["a", 0, 8192]], 0, 8192, alignment=True)
        with self.assertRaises(Rejected): check_regions([], 4097, 4097, alignment=4096)

    def test_existing_data_addresses_preserved(self):
        for option in self.plan["options"].values():
            regions = {r[0]: r[1:] for r in option["internal"]}
            self.assertEqual(regions["littlefs_existing"], [0xF6000, 0xFC000])
            self.assertEqual(regions["settings_existing"], [0xFC000, 0xFE000])

    def test_option_a_does_not_alias_legacy_staging(self):
        external = self.plan["options"]["A"]["external"]
        self.assertEqual(external[0][1:], [0, 0xF0000])
        self.assertEqual(external[1][1:], [0xF0000, 0x130000])
        self.assertEqual(external[2][1], 0x130000)

    def test_signed_supervisor_has_fast_copy_guard(self):
        a = self.plan["options"]["A"]
        self.assertEqual(0x40000 - a["supervisor_signed_cap"], 4096)

    def test_revised_banks_are_conservatively_layout_aligned(self):
        page = self.plan["review_constraints"]["baseline_nor_layout_page_bytes"]
        check_regions(self.plan["options"]["A"]["external"], 0, 2097152, page)
        self.assertTrue(self.plan["review_constraints"]["original_overlap_is_conditional_caller_rounding_not_spi_nor_driver"])
        # Retained driver accepts4KiB requests; only a caller that rounds this
        # historical endpoint to64KiB would cross the next old-sketch bank.
        candidate_end = 0x194000
        self.assertEqual(((candidate_end + page - 1) // page) * page - candidate_end, 49152)

    def test_current_image_fits_proposed_caps_not_new_link_proof(self):
        for option in self.plan["options"].values():
            self.assertLess(self.plan["observed_stock_signed_bytes"], option["personal_container_cap"] - self.plan["image_overhead_allowance"])

    def test_pairing_alone_cannot_enroll(self):
        with self.assertRaises(Rejected): step(State(), "enroll", authorized=True)

    def test_truthy_values_cannot_replace_boolean_assumptions_or_generation(self):
        with self.assertRaises(Rejected): step(State(), "enroll", authorized="paired", physical=True)
        with self.assertRaises(Rejected): step(self.trial(), "owner_confirm", authorized=True, supervisor_health=True, digest="candidate", generation=True)

    def test_wrong_signature_board_or_abi_rejected(self):
        for field in ("signature", "board", "abi"):
            with self.assertRaises(Rejected): self.upload(**{field: False})

    def test_network_or_oversize_candidate_rejected(self):
        for changes in [dict(role="network"), dict(size=393217), dict(size=True)]:
            with self.assertRaises(Rejected): self.upload(**changes)

    def test_non_string_digest_rejected(self):
        for value in [5, True, ["candidate"]]:
            with self.assertRaises(Rejected): self.upload(digest=value)

    def test_candidate_cannot_self_confirm(self):
        state = self.trial()
        self.assertEqual(step(state, "candidate_self_confirm"), state)

    def test_confirmation_bound_to_digest_and_generation(self):
        for changes in [dict(digest="other", generation=1), dict(digest="candidate", generation=0)]:
            with self.assertRaises(Rejected): step(self.trial(), "owner_confirm", authorized=True, supervisor_health=True, **changes)

    def test_owner_confirmation_also_requires_supervisor_health(self):
        with self.assertRaises(Rejected): step(self.trial(), "owner_confirm", authorized=True, digest="candidate", generation=1)
        self.assertEqual(step(self.trial(), "owner_confirm", authorized=True, supervisor_health=True, digest="candidate", generation=1).phase, "personal")

    def test_power_cut_at_each_copy_stage_never_boots_partial_candidate(self):
        for phase in ["copy_candidate", "copy_previous"]:
            before = replace(self.owner, phase=phase)
            state = before
            for _ in range(8): state = step(state, "power_cut")
            self.assertEqual(state, before)

    def test_trial_reset_and_watchdog_revert(self):
        for event in ["power_cut", "watchdog", "trial_timeout"]:
            restored = step(step(self.trial(), event), "copy_complete")
            self.assertEqual((restored.phase, restored.active), ("stock", "stock"))

    def test_physical_recovery_survives_confirmed_bad_app(self):
        state = step(self.trial(), "owner_confirm", authorized=True, supervisor_health=True, digest="candidate", generation=1)
        self.assertEqual(step(state, "gesture", physical=True).phase, "recovery")

    def test_lost_phone_reset_revokes_enrollment(self):
        state = step(step(self.owner, "gesture", physical=True), "owner_reset", physical=True)
        self.assertFalse(state.owner)
        with self.assertRaises(Rejected): self.upload(state)

    def test_broken_recovery_blocks_activation(self):
        with self.assertRaises(Rejected): step(replace(self.upload(), recovery_intact=False), "activate")

    def test_stock_restore_after_lost_phone_without_old_owner_key(self):
        state = step(step(self.owner, "gesture", physical=True), "owner_reset", physical=True)
        state = step(state, "stock_restore_verified", maintainer_signature=True, board=True, abi=True, size=248516)
        state = step(step(state, "power_cut"), "copy_complete")
        self.assertEqual((state.phase, state.active, state.owner), ("stock", "stock", False))

    def test_stock_restore_is_bounded_app_role_and_size(self):
        state = step(self.owner, "gesture", physical=True)
        args = dict(maintainer_signature=True, board=True, abi=True, size=248516)
        with self.assertRaises(Rejected): step(state, "stock_restore_verified", **dict(args, size=393217))
        with self.assertRaises(Rejected): step(state, "stock_restore_verified", **dict(args, size=0))
        with self.assertRaises(Rejected): step(state, "stock_restore_verified", **dict(args, size=True))
        with self.assertRaises(Rejected): step(state, "stock_restore_verified", **dict(args, role="network"))
        self.assertEqual(step(state, "stock_restore_verified", **args).phase, "copy_stock")

    def test_owner_signature_cannot_authorize_stock_recovery_role(self):
        state = step(self.owner, "gesture", physical=True)
        with self.assertRaises(Rejected): step(state, "stock_restore_verified", signature=True, board=True, abi=True)

    def test_protected_write_denials_are_only_assumptions(self):
        for event in ["write_supervisor", "write_owner_journal", "write_uicr", "stop_secure_watchdog"]:
            with self.assertRaisesRegex(Rejected, "not hardware-proven"): step(self.owner, event)

    def test_simulation_never_grants_hardware_or_crypto_authority(self):
        state = self.trial()
        self.assertFalse(state.hardware_authorized)
        self.assertFalse(state.cryptographic_verification_performed)


if __name__ == "__main__": unittest.main()
