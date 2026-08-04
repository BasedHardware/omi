#!/usr/bin/env python3
"""Contract tests for the failure-class retirement author.

Hermetic: every case supplies its own event feed, so no case touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("failure_class_retirement.py")
SPEC = importlib.util.spec_from_file_location("failure_class_retirement", MODULE_PATH)
assert SPEC and SPEC.loader
retirement = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = retirement
SPEC.loader.exec_module(retirement)

NOW = "2026-08-20T00:00:00Z"


def definition(class_id: str, status: str = "open", dormant_since: str | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": 1,
        "id": class_id,
        "violated_contract": "A contract that failed once.",
        "canonical_prevention": "Converge the owner.",
        "evidence_prs": [1234],
        "status": status,
    }
    if dormant_since:
        data["dormant_since"] = dormant_since
    return data


class FeedCoverageTests(unittest.TestCase):
    """The assertion that keeps a green run from meaning nothing."""

    def test_truncated_feed_is_refused(self) -> None:
        cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc)
        feed = {"schema_version": 1, "events": [{"number": i, "body": "", "merged_at": NOW} for i in range(retirement.FETCH_LIMIT)]}
        with self.assertRaises(retirement.RetirementError) as caught:
            retirement.assert_feed_spans_window(feed, cutoff)
        self.assertIn("fetch limit", str(caught.exception))

    def test_empty_feed_is_refused(self) -> None:
        cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc)
        with self.assertRaises(retirement.RetirementError) as caught:
            retirement.assert_feed_spans_window({"schema_version": 1, "events": []}, cutoff)
        self.assertIn("empty", str(caught.exception))

    def test_feed_below_the_limit_is_accepted(self) -> None:
        cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc)
        feed = {"schema_version": 1, "events": [{"number": 1, "body": "", "merged_at": NOW}]}
        retirement.assert_feed_spans_window(feed, cutoff)


class ParsingTests(unittest.TestCase):
    def test_duration_forms(self) -> None:
        self.assertEqual(retirement.parse_duration("14d"), timedelta(days=14))
        self.assertEqual(retirement.parse_duration("24h"), timedelta(hours=24))

    def test_invalid_duration_is_rejected(self) -> None:
        with self.assertRaises(retirement.RetirementError):
            retirement.parse_duration("2 weeks")


class RetirementDiffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.definitions = self.tmp / ".github/failure-classes"
        self.definitions.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_apply_sets_exactly_the_two_lifecycle_fields(self) -> None:
        path = self.definitions / "FC-example.json"
        path.write_text(json.dumps(definition("FC-example"), indent=2) + "\n", encoding="utf-8")

        retirement.apply_retirement(path, retirement.parse_timestamp(NOW))

        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["status"], "dormant")
        self.assertEqual(written["dormant_since"], NOW)
        # Nothing else may drift: the diff must stay reviewable at a glance.
        self.assertEqual(written["violated_contract"], "A contract that failed once.")
        self.assertEqual(written["evidence_prs"], [1234])

    def test_apply_touches_only_the_status_line(self) -> None:
        """A json round trip reflows hand-maintained inline arrays; the diff must not."""
        path = self.definitions / "FC-shaped.json"
        original = (
            "{\n"
            '  "schema_version": 1,\n'
            '  "id": "FC-shaped",\n'
            '  "violated_contract": "A contract that failed once.",\n'
            '  "canonical_prevention": "Converge the owner.",\n'
            '  "evidence_prs": [9365, 9597],\n'
            '  "scope_hints": ["desktop/macos/**", "backend/**"],\n'
            '  "status": "open"\n'
            "}\n"
        )
        path.write_text(original, encoding="utf-8")

        retirement.apply_retirement(path, retirement.parse_timestamp(NOW))

        updated = path.read_text(encoding="utf-8")
        removed = [line for line in original.splitlines() if line not in updated.splitlines()]
        added = [line for line in updated.splitlines() if line not in original.splitlines()]
        self.assertEqual(removed, ['  "status": "open"'])
        self.assertEqual(added, ['  "status": "dormant",', f'  "dormant_since": "{NOW}"'])
        # The inline arrays survive verbatim.
        self.assertIn('  "evidence_prs": [9365, 9597],', updated)
        self.assertIn('  "scope_hints": ["desktop/macos/**", "backend/**"],', updated)

    def test_apply_refuses_a_definition_that_is_not_open(self) -> None:
        path = self.definitions / "FC-already.json"
        path.write_text(
            json.dumps(definition("FC-already", status="dormant", dormant_since=NOW), indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaises(retirement.RetirementError):
            retirement.apply_retirement(path, retirement.parse_timestamp(NOW))

    def test_evidence_names_each_retired_class_and_its_instance(self) -> None:
        report = {"as_of": NOW, "since": "14d", "events_considered": 700}
        eligible = [{"id": "FC-example", "last_reported_instance": {"number": 9001, "merged_at": "2026-08-01T00:00:00Z"}}]

        text = retirement.render_evidence(report, eligible, [])

        self.assertIn("FC-example", text)
        self.assertIn("#9001", text)
        self.assertIn("700", text)

    def test_evidence_reports_no_retirements_without_inventing_any(self) -> None:
        text = retirement.render_evidence({"as_of": NOW, "since": "14d", "events_considered": 5}, [], [])
        self.assertIn("None.", text)

    def test_evidence_separates_reopen_from_retirement(self) -> None:
        text = retirement.render_evidence(
            {"as_of": NOW, "since": "14d", "events_considered": 5}, [], [{"id": "FC-recurred"}]
        )
        self.assertIn("Reopen required", text)
        self.assertIn("FC-recurred", text)


class EndToEndTests(unittest.TestCase):
    """Drive main() against a real failure-class definition tree and feed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.definitions = self.tmp / ".github/failure-classes"
        self.definitions.mkdir(parents=True)
        self.feed = self.tmp / "events.json"
        self.evidence = self.tmp / "evidence.md"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_feed(self, events: list[dict[str, object]]) -> None:
        self.feed.write_text(json.dumps({"schema_version": 1, "events": events}) + "\n", encoding="utf-8")

    def test_stale_class_is_retired_and_fresh_class_is_left_alone(self) -> None:
        stale = self.definitions / "FC-stale.json"
        fresh = self.definitions / "FC-fresh.json"
        stale.write_text(json.dumps(definition("FC-stale"), indent=2) + "\n", encoding="utf-8")
        fresh.write_text(json.dumps(definition("FC-fresh"), indent=2) + "\n", encoding="utf-8")
        self._write_feed(
            [
                # Outside the 14d quiet period -> eligible for retirement.
                {"number": 1, "body": "Failure-Class: FC-stale\n", "merged_at": "2026-07-01T00:00:00Z"},
                # Inside the quiet period -> must stay open.
                {"number": 2, "body": "Failure-Class: FC-fresh\n", "merged_at": "2026-08-19T00:00:00Z"},
            ]
        )

        exit_code = retirement.main(
            [
                "--since",
                "14d",
                "--now",
                NOW,
                "--events-file",
                str(self.feed),
                "--evidence-file",
                str(self.evidence),
                "--apply",
                "--root",
                str(self.tmp),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stale.read_text(encoding="utf-8"))["status"], "dormant")
        self.assertEqual(json.loads(fresh.read_text(encoding="utf-8"))["status"], "open")
        self.assertNotIn("dormant_since", json.loads(fresh.read_text(encoding="utf-8")))
        self.assertIn("FC-stale", self.evidence.read_text(encoding="utf-8"))

    def test_without_apply_nothing_is_written(self) -> None:
        stale = self.definitions / "FC-stale.json"
        stale.write_text(json.dumps(definition("FC-stale"), indent=2) + "\n", encoding="utf-8")
        self._write_feed([{"number": 1, "body": "Failure-Class: FC-stale\n", "merged_at": "2026-07-01T00:00:00Z"}])

        exit_code = retirement.main(
            ["--since", "14d", "--now", NOW, "--events-file", str(self.feed), "--root", str(self.tmp)]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stale.read_text(encoding="utf-8"))["status"], "open")

    def test_recurrence_after_retirement_fails_the_run(self) -> None:
        recurred = self.definitions / "FC-recurred.json"
        recurred.write_text(
            json.dumps(definition("FC-recurred", status="dormant", dormant_since="2026-08-01T00:00:00Z"), indent=2) + "\n",
            encoding="utf-8",
        )
        self._write_feed(
            [{"number": 7, "body": "Failure-Class: FC-recurred\n", "merged_at": "2026-08-15T00:00:00Z"}]
        )

        exit_code = retirement.main(
            [
                "--since",
                "14d",
                "--now",
                NOW,
                "--events-file",
                str(self.feed),
                "--evidence-file",
                str(self.evidence),
                "--root",
                str(self.tmp),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Reopen required", self.evidence.read_text(encoding="utf-8"))

    def test_empty_feed_fails_before_any_edit(self) -> None:
        stale = self.definitions / "FC-stale.json"
        stale.write_text(json.dumps(definition("FC-stale"), indent=2) + "\n", encoding="utf-8")
        self._write_feed([])

        exit_code = retirement.main(
            ["--since", "14d", "--now", NOW, "--events-file", str(self.feed), "--apply", "--root", str(self.tmp)]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stale.read_text(encoding="utf-8"))["status"], "open")


if __name__ == "__main__":
    unittest.main()
