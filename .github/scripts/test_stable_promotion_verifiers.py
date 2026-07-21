from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / ".github/scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


APPCAST = _load("verify_stable_appcast.py")
POINTER = _load("check_stable_pointer_precondition.py")
CONFIRMATION = _load("require_stable_promotion_confirmation.py")
POLICY = _load("check-desktop-prod-promotion-policy.py")


def _fields(release_id: str, generation: int) -> dict:
    return {"release_id": {"stringValue": release_id}, "generation": {"integerValue": str(generation)}}


class StablePromotionVerifierTests(unittest.TestCase):
    def test_confirmation_rejects_wrong_or_missing_token_for_every_stable_mutation(self):
        for operation in ("promote", "repoint"):
            for confirm in ("", "promote-beta"):
                with self.subTest(operation=operation, confirm=confirm or "missing"):
                    with self.assertRaisesRegex(ValueError, "confirm must be exactly"):
                        CONFIRMATION.validate(operation=operation, confirm=confirm)
            CONFIRMATION.validate(operation=operation, confirm="promote-stable")

    def test_policy_requires_confirmation_before_authentication_or_mutation(self):
        original = (ROOT / POLICY.WORKFLOW).read_text(encoding="utf-8")
        mutations = (
            original.replace("      - name: Require explicit Stable confirmation\n", "      - name: Confirmation moved too late\n", 1),
            original.replace("--operation \"$OPERATION\" --confirm \"$CONFIRM\"", "--operation \"$OPERATION\" --confirm promote-beta", 1),
        )
        for changed in mutations:
            with self.subTest(mutation=changed != original), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workflow = root / POLICY.WORKFLOW
                workflow.parent.mkdir(parents=True)
                workflow.write_text(changed, encoding="utf-8")
                self.assertTrue(POLICY.validate(workflow.read_text(encoding="utf-8")))

    def test_lost_response_retry_accepts_only_the_expected_next_generation(self):
        POINTER.verify(
            beta=_fields("target", 4),
            stable=_fields("target", 8),
            release_id="target",
            expected_release_id="previous",
            expected_generation=7,
            operation="promote",
        )
        with self.assertRaisesRegex(ValueError, "unrelated generation drift"):
            POINTER.verify(
                beta=_fields("target", 4),
                stable=_fields("target", 9),
                release_id="target",
                expected_release_id="previous",
                expected_generation=7,
                operation="promote",
            )

    def test_stable_appcast_ignores_beta_item_but_rejects_two_default_items(self):
        manifest = {
            "build_number": 9,
            "version": "1.0",
            "zip_url": "https://example.test/Omi.zip",
            "ed_signature": "sig",
        }
        xml = '''<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel>
<item><enclosure url="https://example.test/Omi.zip" sparkle:edSignature="sig"/><sparkle:version>9</sparkle:version><sparkle:shortVersionString>1.0</sparkle:shortVersionString></item>
<item><enclosure url="https://example.test/Omi.zip" sparkle:edSignature="sig"/><sparkle:version>9</sparkle:version><sparkle:shortVersionString>1.0</sparkle:shortVersionString><sparkle:channel>beta</sparkle:channel></item></channel></rss>'''
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "feed.xml"
            feed.write_text(xml, encoding="utf-8")
            APPCAST.verify(manifest, feed)
            feed.write_text(xml.replace("<sparkle:channel>beta</sparkle:channel>", ""), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "default/non-beta"):
                APPCAST.verify(manifest, feed)


if __name__ == "__main__":
    unittest.main()
