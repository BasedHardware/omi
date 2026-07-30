#!/usr/bin/env python3
"""Unit tests for the Windows update-feed production probe."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).with_name("probe_windows_update_feed.py")
SPEC = importlib.util.spec_from_file_location("probe_windows_update_feed", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)


def ok_payload(
    *,
    requested: str = "beta",
    served: str = "beta",
    version: str = "1.0.33",
    feed_url: str = "https://github.com/BasedHardware/omi/releases/download/v1.0.33-windows/",
) -> dict[str, str]:
    return {
        "requested_channel": requested,
        "served_channel": served,
        "version": version,
        "feed_url": feed_url,
    }


class ProbeWindowsUpdateFeedTests(unittest.TestCase):
    def test_validate_accepts_trusted_windows_feed(self) -> None:
        result = PROBE.validate_feed_response(ok_payload(), requested_channel="beta")
        self.assertEqual(result["version"], "1.0.33")
        self.assertTrue(result["feed_url"].endswith("/v1.0.33-windows/"))

    def test_validate_allows_beta_to_stable_fallback(self) -> None:
        payload = ok_payload(
            requested="beta",
            served="stable",
            version="1.0.1",
            feed_url="https://github.com/BasedHardware/omi/releases/download/v1.0.1-windows/",
        )
        result = PROBE.validate_feed_response(payload, requested_channel="beta")
        self.assertEqual(result["served_channel"], "stable")

    def test_validate_rejects_stable_fallthrough_to_beta(self) -> None:
        payload = ok_payload(requested="stable", served="beta")
        with self.assertRaisesRegex(PROBE.ProbeError, "never fall through"):
            PROBE.validate_feed_response(payload, requested_channel="stable")

    def test_validate_rejects_untrusted_feed_url(self) -> None:
        cases = (
            "http://github.com/BasedHardware/omi/releases/download/v1.0.33-windows/",
            "https://evil.example/BasedHardware/omi/releases/download/v1.0.33-windows/",
            "https://github.com/BasedHardware/omi/releases/download/v1.0.33-macos/",
            "https://github.com/BasedHardware/omi/releases/download/v1.0.33-windows/?x=1",
            "https://github.com/BasedHardware/omi/releases/download/v1.0.33-windows/#frag",
            "https://user:pass@github.com/BasedHardware/omi/releases/download/v1.0.33-windows/",
        )
        for feed_url in cases:
            with self.subTest(feed_url=feed_url):
                payload = ok_payload(feed_url=feed_url)
                with self.assertRaisesRegex(PROBE.ProbeError, "untrusted feed_url"):
                    PROBE.validate_feed_response(payload, requested_channel="beta")

    def test_classify_missing_route_vs_empty_channel(self) -> None:
        self.assertIn(
            "missing /v2/desktop/update-feed/windows",
            PROBE.classify_http_failure(404, {"detail": "Not Found"}),
        )
        self.assertIn(
            "No Windows update feed found",
            PROBE.classify_http_failure(
                404, {"detail": "No Windows update feed found for channel: beta"}
            ),
        )

    def test_probe_channel_success_and_failure(self) -> None:
        def fetch_ok(url: str) -> tuple[int, object]:
            self.assertIn("channel=beta", url)
            return 200, ok_payload()

        result = PROBE.probe_channel("https://api.omi.me", "beta", fetch=fetch_ok)
        self.assertEqual(result["version"], "1.0.33")

        def fetch_missing(_url: str) -> tuple[int, object]:
            return 404, {"detail": "Not Found"}

        with self.assertRaisesRegex(PROBE.ProbeError, "missing /v2/desktop/update-feed/windows"):
            PROBE.probe_channel("https://api.omi.me", "beta", fetch=fetch_missing)

    def test_main_exits_nonzero_when_route_missing(self) -> None:
        with mock.patch.object(
            PROBE,
            "probe",
            side_effect=PROBE.ProbeError(
                "production is missing /v2/desktop/update-feed/windows"
            ),
        ):
            self.assertEqual(PROBE.main([]), 1)

    def test_main_prints_ok_on_success(self) -> None:
        with mock.patch.object(PROBE, "probe", return_value=[ok_payload()]):
            with mock.patch("builtins.print") as printer:
                self.assertEqual(PROBE.main([]), 0)
        messages = [call.args[0] for call in printer.call_args_list]
        self.assertTrue(any("probe OK" in message for message in messages), messages)


if __name__ == "__main__":
    unittest.main()
