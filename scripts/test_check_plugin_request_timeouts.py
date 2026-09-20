#!/usr/bin/env python3
import unittest

from check_plugin_request_timeouts import METHODS, scan_source


class RequestTimeoutScanTests(unittest.TestCase):
    def _violations(self, source):
        return list(scan_source(source))

    def test_requests_get_without_timeout_is_flagged(self):
        v = self._violations("import requests\nresponse = requests.get(url, headers=headers)\n")
        self.assertEqual(v, [(2, "get")])

    def test_requests_post_without_timeout_is_flagged(self):
        v = self._violations("import requests\nrequests.post(url, json=data)\n")
        self.assertEqual(v, [(2, "post")])

    def test_every_verb_without_timeout_is_flagged(self):
        for verb in sorted(METHODS):
            v = self._violations(f"import requests\nrequests.{verb}(url)\n")
            self.assertEqual(v, [(2, verb)], verb)

    def test_call_with_timeout_is_clean(self):
        v = self._violations(
            "import requests\nrequests.get(url, headers=headers, timeout=(5, 30))\n"
        )
        self.assertEqual(v, [])

    def test_timeout_via_named_constant_is_clean(self):
        v = self._violations(
            "import requests\nrequests.post(url, data=d, timeout=REQUEST_TIMEOUT)\n"
        )
        self.assertEqual(v, [])

    def test_session_method_without_timeout_is_flagged(self):
        v = self._violations("import requests\nrequests.Session().get(url)\n")
        self.assertEqual(v, [(2, "get")])

    def test_session_method_with_timeout_is_clean(self):
        v = self._violations("import requests\nrequests.Session().get(url, timeout=5)\n")
        self.assertEqual(v, [])

    def test_lowercase_session_without_timeout_is_flagged(self):
        v = self._violations("import requests\nrequests.session().post(url, json=d)\n")
        self.assertEqual(v, [(2, "post")])

    def test_non_requests_attribute_call_is_ignored(self):
        v = self._violations("import httpx\nclient.get(url)\nfoo.bar()\n")
        self.assertEqual(v, [])

    def test_httpx_and_other_libraries_are_not_scanned(self):
        v = self._violations("import httpx\nhttpx.get(url)\n")
        self.assertEqual(v, [])

    def test_multiline_call_without_timeout_is_flagged(self):
        source = (
            "import requests\n"
            "response = requests.post(\n"
            "    url,\n"
            "    headers=headers,\n"
            "    json=data,\n"
            ")\n"
        )
        self.assertEqual(self._violations(source), [(2, "post")])

    def test_keyword_only_timeout_positional_is_still_missing(self):
        # requests timeout is keyword-only; a dict spread cannot satisfy it.
        source = "import requests\nrequests.get(url, **{'headers': h})\n"
        self.assertEqual(self._violations(source), [(2, "get")])

    def test_syntax_error_source_yields_no_violations(self):
        self.assertEqual(self._violations("this is not python !!!"), [])


if __name__ == "__main__":
    unittest.main()
