#!/usr/bin/env python3
"""Gateway admission accepts newline-delimited runtime config without bypasses."""

import sys
import unittest

import test_check_public_build_contract as fixtures


class RuntimeEnvInputTests(unittest.TestCase):
    def test_gateway_binding_must_belong_to_the_action_input(self):
        fixture = fixtures.PublicBuildContractFixture()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        contract = fixtures.fixture_contract()
        contract["targets"]["fake"]["gateway_required"] = True
        fixture.write_json("config/public-build-contract.json", contract)
        path = fixture.root / ".github/workflows/gcp_fake.yml"
        prefix = path.read_text()
        binding = "OMI_LLM_GATEWAY_URL=${{ vars.OMI_LLM_GATEWAY_URL }}"
        for suffix, expected in (
            ("          runtime_env_vars: " + binding + "\n", True),
            (
                "          runtime_env_vars: |\n            ADMIN_STATS_READER_SAS=reader\n            "
                + binding
                + "\n",
                True,
            ),
            ("          runtime_env_vars: |-\n            " + binding + "\n", True),
            ("          # runtime_env_vars: " + binding + "\n", False),
            (
                "          runtime_env_vars: |\n            OTHER=value\n          unrelated: |\n            "
                + binding
                + "\n",
                False,
            ),
            ("          runtime_env_vars: |\n            OMI_LLM_GATEWAY_URL=${{ secrets.GATEWAY }}\n", False),
        ):
            with self.subTest(suffix=suffix):
                path.write_text(prefix + suffix + "          require_gateway_url: true\n")
                errors = fixtures.STATIC.validate_target(fixture.root, fixture.target(), {"FAKE_PUBLIC_INPUT"})
                self.assertEqual(not errors, expected, errors)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(fixtures)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeEnvInputTests))
    result = unittest.TextTestRunner().run(suite)
    sys.exit(not result.wasSuccessful())
