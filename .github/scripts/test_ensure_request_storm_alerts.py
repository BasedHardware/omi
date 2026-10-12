from __future__ import annotations

import copy
import datetime as dt
import json
import subprocess
import unittest
from pathlib import Path

from replay_request_storm_alerts import STEP, first_fire, timestamp
from ensure_request_storm_alerts import CONFIG_DIR, POLICIES, ensure_alerts

CHANNEL = "projects/based-hardware/notificationChannels/1"


class FakeMonitoring:
    def __init__(self):
        self.policies = {}
        self.writes = []
        self.fail = False
        self.duplicate = False

    def __call__(self, args, **kwargs):
        operation = args[3]
        if self.fail:
            return subprocess.CompletedProcess(args, 1, "", "permission denied")
        if operation == "list":
            display = next(x for x in args if x.startswith("--filter=")).split('"')[1]
            names = [k for k, v in self.policies.items() if v["displayName"] == display]
            if self.duplicate:
                names = ["one", "two"]
            result = "\n".join(names)
        elif operation == "describe":
            result = json.dumps(self.policies[args[4]])
        else:
            body = json.loads(next(x for x in args if x.startswith("--policy="))[9:])
            self.writes.append((operation, copy.deepcopy(body)))
            name = args[4] if operation == "update" else f"projects/based-hardware/alertPolicies/{len(self.policies) + 1}"
            body["name"] = name
            body["conditions"][0].setdefault("name", name + "/conditions/123")
            # Output defaults must not cause repeated writes.
            body["conditions"][0]["conditionThreshold"].setdefault("forecastOptions", {})
            body["creationRecord"] = {"mutatedBy": "deployer"}
            self.policies[name] = body
            result = name
        return subprocess.CompletedProcess(args, 0, result, "")


class StormAlertsTest(unittest.TestCase):
    def test_create_then_noop_and_channel_drift_preserves_condition(self):
        fake = FakeMonitoring()
        names = ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        self.assertEqual(len(names), 2)
        self.assertEqual([x[0] for x in fake.writes], ["create", "create"])
        ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        self.assertEqual(len(fake.writes), 2)
        old_condition = fake.policies[names[1]]["conditions"][0]["name"]
        ensure_alerts(project="based-hardware", notification_channels=CHANNEL + "2", runner=fake)
        self.assertEqual([x[0] for x in fake.writes[2:]], ["update", "update"])
        self.assertEqual(fake.policies[names[1]]["conditions"][0]["name"], old_condition)
        self.assertEqual(fake.policies[names[1]]["notificationChannels"], [CHANNEL + "2"])

    def test_threshold_ratio_and_documentation_drift_are_repaired(self):
        fake = FakeMonitoring()
        names = ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        fake.policies[names[0]]["conditions"][0]["conditionThreshold"]["thresholdValue"] = 1
        fake.policies[names[0]]["conditions"][0]["conditionThreshold"]["denominatorFilter"] = "stale ratio"
        fake.policies[names[1]]["conditions"][0]["conditionThreshold"]["denominatorFilter"] = "wrong"
        fake.policies[names[1]]["documentation"]["content"] = "stale"
        ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        self.assertEqual(len(fake.writes), 4)
        self.assertNotIn("denominatorFilter", fake.policies[names[0]]["conditions"][0]["conditionThreshold"])
        self.assertIn("request_count", fake.policies[names[1]]["conditions"][0]["conditionThreshold"]["denominatorFilter"])

    def test_duplicates_permissions_invalid_channels_and_project_fail_without_writes(self):
        for fault in ("duplicate", "fail"):
            fake = FakeMonitoring()
            setattr(fake, fault, True)
            with self.assertRaises(RuntimeError):
                ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
            self.assertEqual(fake.writes, [])
        for project, channels in [("based-hardware-dev", CHANNEL), ("based-hardware", "")]:
            fake = FakeMonitoring()
            with self.assertRaises(ValueError):
                ensure_alerts(project=project, notification_channels=channels, runner=fake)
            self.assertEqual(fake.writes, [])

    def test_malformed_existing_condition_fails_closed(self):
        fake = FakeMonitoring()
        names = ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        fake.policies[names[0]]["conditions"] = []
        with self.assertRaises(RuntimeError):
            ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        self.assertEqual(len(fake.writes), 2)

    def test_filters_and_ratio_alignment_are_scoped_and_matching(self):
        a, b = [json.loads((CONFIG_DIR / name).read_text()) for name in POLICIES]
        edge = a["conditions"][0]["conditionThreshold"]
        self.assertEqual(edge["duration"], "1800s")
        self.assertAlmostEqual(edge["thresholdValue"] * 60, 1000)
        self.assertIn('response_code="429"', edge["filter"])
        self.assertEqual(edge["filter"].count('resource.labels.backend_target_name='), 3)
        self.assertIn('project_id="based-hardware"', edge["filter"])
        self.assertEqual(edge["aggregations"][0]["groupByFields"], ["resource.label.backend_target_name"])
        ratio = b["conditions"][0]["conditionThreshold"]
        self.assertEqual(ratio["duration"], "3600s")
        self.assertEqual(ratio["thresholdValue"], .1)
        self.assertEqual(ratio["filter"], ratio["denominatorFilter"] + ' AND metric.labels.response_code="409"')
        self.assertEqual(ratio["aggregations"], ratio["denominatorAggregations"])
        self.assertEqual(ratio["aggregations"][0]["perSeriesAligner"], "ALIGN_SUM")
        self.assertIn("backend-sync-49a4-be", ratio["denominatorFilter"])

    def test_replay_requires_full_dwell_and_resets_on_gap_or_recovery(self):
        start = timestamp("2026-10-07T12:00:00Z")
        end = start + dt.timedelta(hours=2)
        points = {start + STEP * i: 1001 for i in range(7)}
        self.assertEqual(first_fire(points, 1000, dt.timedelta(minutes=30), start, end), "2026-10-07T12:30:00Z")
        points[start + STEP * 3] = 1000
        self.assertEqual(first_fire(points, 1000, dt.timedelta(minutes=30), start, end), "none")
        del points[start + STEP * 3]
        self.assertEqual(first_fire(points, 1000, dt.timedelta(minutes=30), start, end), "none")

    def test_workflow_uses_workflow_owned_scripts_and_same_prod_channel_step(self):
        workflow = (Path(__file__).resolve().parent.parent / "workflows/gcp_backend.yml").read_text()
        step = workflow.split("id: backend-route-alert", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("github.event.inputs.environment == 'prod'", step)
        self.assertIn("vars.SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS", step)
        self.assertIn('$DEPLOY_WORKFLOW_ROOT/.github/scripts/ensure_request_storm_alerts.py', step)
        self.assertIn('--notification-channels "$ALERT_CHANNELS"', step)


if __name__ == "__main__":
    unittest.main()
