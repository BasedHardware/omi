from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('check_web_llm_gateway_only.py')
SPEC = importlib.util.spec_from_file_location('check_web_llm_gateway_only', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class WebLlmGatewayOnlyTest(unittest.TestCase):
    def test_gateway_client_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'web' / 'site' / 'src' / 'gateway.ts'
            source.parent.mkdir(parents=True)
            source.write_text(
                "fetch(`${process.env.OMI_LLM_GATEWAY_URL}/v1/chat/completions`)\n",
                encoding='utf-8',
            )
            (root / 'web' / 'site' / 'package.json').write_text(
                json.dumps({'dependencies': {'next': '1.0.0'}}),
                encoding='utf-8',
            )

            self.assertEqual(CHECKER.find_violations(root), [])

    def test_provider_url_credential_and_dependency_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'web' / 'site' / 'src' / 'route.ts'
            source.parent.mkdir(parents=True)
            source.write_text(
                "fetch('https://api.anthropic.com/v1/messages', "
                "{headers: {'x-api-key': process.env.ANTHROPIC_API_KEY}})\n",
                encoding='utf-8',
            )
            (root / 'web' / 'site' / 'package.json').write_text(
                json.dumps({'dependencies': {'@anthropic-ai/sdk': '1.0.0'}}),
                encoding='utf-8',
            )

            violations = CHECKER.find_violations(root)

            self.assertTrue(any('direct provider URL' in item for item in violations))
            self.assertTrue(any('direct provider credential' in item for item in violations))
            self.assertTrue(any('direct provider dependency' in item for item in violations))

    def test_org_admin_reporting_endpoints_are_not_inference_traffic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'web' / 'admin' / 'lib' / 'services' / 'provider-costs.ts'
            source.parent.mkdir(parents=True)
            source.write_text(
                "new URL('https://api.anthropic.com/v1/organizations/cost_report')\n"
                "new URL('https://api.openai.com/v1/organization/costs')\n",
                encoding='utf-8',
            )

            self.assertEqual(CHECKER.find_violations(root), [])

    def test_inference_urls_still_fail_outside_the_org_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'web' / 'admin' / 'lib' / 'services' / 'provider-costs.ts'
            source.parent.mkdir(parents=True)
            source.write_text(
                "fetch('https://api.anthropic.com/v1/messages')\n",
                encoding='utf-8',
            )

            violations = CHECKER.find_violations(root)

            self.assertTrue(any('direct provider URL' in item for item in violations))

    def test_test_fixtures_may_name_forbidden_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_file = root / 'web' / 'site' / 'src' / '__tests__' / 'guard.test.ts'
            test_file.parent.mkdir(parents=True)
            test_file.write_text("expect(source).not.toContain('OPENAI_API_KEY')\n", encoding='utf-8')

            self.assertEqual(CHECKER.find_violations(root), [])


if __name__ == '__main__':
    unittest.main()
