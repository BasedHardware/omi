#!/usr/bin/env python3
"""Unit tests for guardrail baseline health pulse (#9454)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import guardrail_pulse


class GuardrailPulseTests(unittest.TestCase):
    def test_format_text_parses_counts(self) -> None:
        text = guardrail_pulse.format_text(
            [
                guardrail_pulse.Metric("union_return_isinstance", 0, 0),
                guardrail_pulse.Metric("lifecycle_unlabeled_scripts", 14, 19),
            ]
        )
        self.assertIn("union_return_isinstance", text)
        self.assertIn("0", text)
        self.assertIn("(baseline 0)", text)
        self.assertIn("lifecycle_unlabeled_scripts", text)
        self.assertIn("(baseline 19)", text)

    def test_staleness_triggers_on_31_day_unchanged_nonzero(self) -> None:
        as_of = date(2026, 7, 23)
        old = (as_of - timedelta(days=31)).isoformat()
        mid = (as_of - timedelta(days=15)).isoformat()
        history = [
            {
                "date": old,
                "metrics": {"lifecycle_unlabeled_scripts": {"count": 14, "baseline": 19}},
            },
            {
                "date": mid,
                "metrics": {"lifecycle_unlabeled_scripts": {"count": 14, "baseline": 19}},
            },
            {
                "date": as_of.isoformat(),
                "metrics": {"lifecycle_unlabeled_scripts": {"count": 14, "baseline": 19}},
            },
        ]
        self.assertEqual(
            guardrail_pulse.find_stale_metrics(history, as_of=as_of, window_days=30),
            ["lifecycle_unlabeled_scripts"],
        )

    def test_staleness_skips_decreasing_metric(self) -> None:
        as_of = date(2026, 7, 23)
        old = (as_of - timedelta(days=31)).isoformat()
        recent = (as_of - timedelta(days=7)).isoformat()
        history = [
            {
                "date": old,
                "metrics": {"mapless_packages": {"count": 7, "baseline": 7}},
            },
            {
                "date": recent,
                "metrics": {"mapless_packages": {"count": 6, "baseline": 7}},
            },
            {
                "date": as_of.isoformat(),
                "metrics": {"mapless_packages": {"count": 6, "baseline": 7}},
            },
        ]
        self.assertEqual(guardrail_pulse.find_stale_metrics(history, as_of=as_of, window_days=30), [])

    def test_staleness_skips_zero_counts(self) -> None:
        as_of = date(2026, 7, 23)
        old = (as_of - timedelta(days=40)).isoformat()
        history = [
            {"date": old, "metrics": {"union_return_isinstance": {"count": 0, "baseline": 0}}},
            {
                "date": as_of.isoformat(),
                "metrics": {"union_return_isinstance": {"count": 0, "baseline": 0}},
            },
        ]
        self.assertEqual(guardrail_pulse.find_stale_metrics(history, as_of=as_of), [])

    def test_record_appends_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.jsonl"
            payload = guardrail_pulse.metrics_payload(
                [guardrail_pulse.Metric("union_return_isinstance", 0, 0)],
                recorded_at="2026-07-23",
            )
            guardrail_pulse.append_history(history, payload)
            guardrail_pulse.append_history(history, payload)
            rows = guardrail_pulse.load_history(history)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["date"], "2026-07-23")
            self.assertEqual(rows[0]["metrics"]["union_return_isinstance"]["count"], 0)

    def test_json_round_trip_shape(self) -> None:
        payload = guardrail_pulse.metrics_payload(
            [guardrail_pulse.Metric("brand_ui_purple", 3, 3)],
            recorded_at="2026-01-01",
        )
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["metrics"]["brand_ui_purple"]["baseline"], 3)


if __name__ == "__main__":
    unittest.main()
