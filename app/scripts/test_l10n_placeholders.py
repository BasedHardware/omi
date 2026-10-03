#!/usr/bin/env python3
"""Hermetic fixtures for the l10n placeholder guards in l10n.py."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("l10n", Path(__file__).with_name("l10n.py"))
assert _SPEC and _SPEC.loader
l10n = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(l10n)


class RequirePlaceholdersKeptTest(unittest.TestCase):
    def test_translation_keeping_every_placeholder_passes(self) -> None:
        l10n.require_placeholders_kept("ETA: {time}", "Estimeret tid: {time}", "da", "etaLabel")

    def test_reordered_placeholders_pass(self) -> None:
        l10n.require_placeholders_kept("{count} of {total}", "{total}中 {count}", "zh", "progress")

    def test_dropped_placeholder_is_rejected(self) -> None:
        with self.assertRaises(l10n.L10nError) as raised:
            l10n.require_placeholders_kept("ETA: {time}", "Estimeret tid", "da", "etaLabel")
        self.assertIn("'etaLabel' drops placeholders ['time']", str(raised.exception))

    def test_plural_and_select_messages_are_exempt(self) -> None:
        l10n.require_placeholders_kept(
            "{count, plural, =1{1 item} other{{count} items}}",
            "{count, plural, other{Elemente}}",
            "de",
            "items",
        )
        l10n.require_placeholders_kept(
            "{gender, select, male{He} other{They}}", "{gender, select, other{Sie}}", "de", "pronoun"
        )

    def test_quoted_plural_literal_does_not_exempt_with_escaping(self) -> None:
        english = "'{count, plural, other{item}}' ETA: {time}"
        with self.assertRaises(l10n.L10nError):
            l10n.require_placeholders_kept(english, "'{count, plural, other{x}}' ETA", "da", "eta", use_escaping=True)
        l10n.require_placeholders_kept(english, "'{count, plural, other{x}}' ETA: {time}", "da", "eta", use_escaping=True)


class CheckCommandTest(unittest.TestCase):
    def _run_check(self, translated: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            arb_dir = Path(tmp)
            english = {"@@locale": "en", "eta": "ETA: {time}", "@eta": {"placeholders": {"time": {}}}}
            (arb_dir / "app_en.arb").write_text(json.dumps(english), encoding="utf-8")
            (arb_dir / "app_da.arb").write_text(
                json.dumps({"@@locale": "da", "eta": translated}), encoding="utf-8"
            )
            return l10n.main(["--arb-dir", str(arb_dir), "--app-dir", str(arb_dir), "check"])

    def test_check_accepts_complete_translation(self) -> None:
        self.assertEqual(self._run_check("Estimeret tid: {time}"), 0)

    def test_check_rejects_dropped_placeholder(self) -> None:
        self.assertNotEqual(self._run_check("Estimeret tid"), 0)


if __name__ == "__main__":
    unittest.main()
