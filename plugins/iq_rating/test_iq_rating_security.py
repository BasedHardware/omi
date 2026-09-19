"""Hermetic tests: IQ Rating page must prevent script-context breakouts and escape errors.

Vulnerabilities tested:
1. Script breakout in `const uid = {uid_json};`: quotes and closing script tags in `uid`.
2. Script breakout in `let peopleData = {people_data_json};`: closing script tags in names/bios.
3. Reflected exception message escaping in error HTML.
"""

import asyncio
import html
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Set dummy credentials so startup hook passes if invoked
os.environ["OMI_APP_ID"] = "test-app-id"
os.environ["OMI_APP_SECRET"] = "test-app-secret"

APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))

import main as iq_main


def _run(coro):
    return asyncio.run(coro)


class IqRatingSecurityTest(unittest.TestCase):
    def test_uid_quote_breakout_prevented(self) -> None:
        malicious_uid = "'; alert('xss'); //"
        with patch.object(iq_main, "get_people_for_user", return_value=[{"name": "Alice", "iq": 120}]):
            resp = _run(iq_main.iq_rating_page(uid=malicious_uid))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            self.assertIn(f"const uid = {json.dumps(malicious_uid)};", body)
            self.assertNotIn(f"const uid = '{malicious_uid}';", body)

    def test_uid_script_tag_breakout_sanitized(self) -> None:
        malicious_uid = "</script><script>alert(1)</script>"
        with patch.object(iq_main, "get_people_for_user", return_value=[{"name": "Alice", "iq": 120}]):
            resp = _run(iq_main.iq_rating_page(uid=malicious_uid))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            # Any closing script tag within the string must be escaped
            self.assertNotIn("const uid = \"</script>", body)
            self.assertIn("<\\/script>", body)

    def test_people_data_script_tag_breakout_sanitized(self) -> None:
        malicious_people = [
            {"name": "</script><script>alert('pwned')</script>", "iq": 140}
        ]
        with patch.object(iq_main, "get_people_for_user", return_value=malicious_people):
            resp = _run(iq_main.iq_rating_page(uid="valid_user"))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            self.assertNotIn("</script><script>alert('pwned')", body)
            self.assertIn("<\\/script>", body)

    def test_exception_reflection_is_escaped(self) -> None:
        with patch.object(iq_main, "get_people_for_user", side_effect=RuntimeError("<script>alert('error')</script>")):
            resp = _run(iq_main.iq_rating_page(uid="valid_user"))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            self.assertNotIn("<script>alert('error')</script>", body)
            self.assertIn(html.escape("<script>alert('error')</script>"), body)


if __name__ == "__main__":
    unittest.main()
