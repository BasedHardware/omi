#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("extract_single_cloud_run_traffic_revision.py")
SPEC = importlib.util.spec_from_file_location("cloud_run_traffic_revision", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExtractSingleCloudRunTrafficRevisionTests(unittest.TestCase):
    def test_returns_the_unique_serving_revision_despite_zero_traffic_tags(self) -> None:
        service = {
            "status": {
                "traffic": [
                    {"percent": 0, "revisionName": "candidate", "tag": "candidate"},
                    {"percent": 100, "revisionName": "stable"},
                ]
            }
        }

        self.assertEqual(MODULE.extract_single_serving_revision(service), "stable")

    def test_rejects_missing_or_ambiguous_serving_revision(self) -> None:
        for traffic in ([], [{"percent": 50, "revisionName": "one"}, {"percent": 50, "revisionName": "two"}]):
            with self.subTest(traffic=traffic):
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    MODULE.extract_single_serving_revision({"status": {"traffic": traffic}})
