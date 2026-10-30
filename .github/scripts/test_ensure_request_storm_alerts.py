from __future__ import annotations

import copy
import contextlib
import io
import datetime as dt
import json
import subprocess
import unittest
from pathlib import Path

from replay_request_storm_alerts import STEP, first_fire, replay, timestamp
from ensure_monitoring_metric_alert_policy import ensure_json_policy
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
            for index, condition in enumerate(body["conditions"]):
                condition.setdefault("name", name + f"/conditions/{123 + index}")
                # Output defaults must not cause repeated writes.
                condition["conditionThreshold"].setdefault("forecastOptions", {})
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
        self.assertAlmostEqual(edge["thresholdValue"] * 60, 2000)
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
        self.assertEqual(ratio["aggregations"][0]["alignmentPeriod"], "300s")
        self.assertEqual(b["combiner"], "AND")
        self.assertEqual(len(b["conditions"]), 2)
        volume = b["conditions"][1]["conditionThreshold"]
        self.assertEqual(volume["filter"], ratio["denominatorFilter"])
        self.assertEqual(volume["aggregations"], ratio["denominatorAggregations"])
        self.assertEqual(volume["duration"], ratio["duration"])
        self.assertEqual(volume["thresholdValue"], 100)
        self.assertNotIn("denominatorFilter", volume)

    def test_replay_requires_full_dwell_and_resets_on_gap_or_recovery(self):
        start = timestamp("2026-10-07T12:00:00Z")
        end = start + dt.timedelta(hours=2)
        points = {start + STEP * i: 1001 for i in range(7)}
        self.assertEqual(first_fire(points, 1000, dt.timedelta(minutes=30), start, end), "2026-10-07T12:30:00Z")
        points[start + STEP * 3] = 1000
        self.assertEqual(first_fire(points, 1000, dt.timedelta(minutes=30), start, end), "none")
        del points[start + STEP * 3]
        self.assertEqual(first_fire(points, 1000, dt.timedelta(minutes=30), start, end), "none")

    def test_two_condition_reconciliation_preserves_both_names_despite_reordering(self):
        fake = FakeMonitoring()
        names = ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        policy = fake.policies[names[1]]
        before = {c["displayName"]: c["name"] for c in policy["conditions"]}
        policy["conditions"].reverse()
        ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        self.assertEqual(len(fake.writes), 2)
        policy["conditions"][0]["conditionThreshold"]["thresholdValue"] = 1
        ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        after = {c["displayName"]: c["name"] for c in fake.policies[names[1]]["conditions"]}
        self.assertEqual(after, before)
        self.assertEqual(len(fake.writes), 3)

    def test_add_volume_floor_preserves_legacy_ratio_condition_identity(self):
        fake = FakeMonitoring()
        names = ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        policy = fake.policies[names[1]]
        old_name = policy["conditions"][0]["name"]
        policy["conditions"] = policy["conditions"][:1]
        policy["combiner"] = "OR"
        policy["conditions"][0]["conditionThreshold"]["aggregations"][0]["alignmentPeriod"] = "3600s"
        policy["conditions"][0]["conditionThreshold"]["denominatorAggregations"][0]["alignmentPeriod"] = "3600s"
        ensure_alerts(project="based-hardware", notification_channels=CHANNEL, runner=fake)
        updated = fake.policies[names[1]]
        self.assertEqual(updated["combiner"], "AND")
        self.assertEqual(updated["conditions"][0]["name"], old_name)
        self.assertEqual(len({c["name"] for c in updated["conditions"]}), 2)

    def test_multi_condition_guard_refuses_or_shape(self):
        body = json.loads((CONFIG_DIR / POLICIES[1]).read_text())
        body["combiner"] = "OR"
        fake = FakeMonitoring()
        with self.assertRaises(ValueError):
            ensure_json_policy(project="based-hardware", body=body, runner=fake)
        self.assertEqual(fake.writes, [])

    def replay_sync(self, totals, duplicates):
        start = timestamp("2026-10-07T12:00:00Z")
        def series(code, values):
            return {
                "metric": {"labels": {"response_code": code}},
                "points": [
                    {"interval": {"endTime": (start + STEP * i).isoformat()},
                     "value": {"int64Value": str(value)}}
                    for i, value in enumerate(values)
                ],
            }
        data = [series("409", duplicates), series("202", [t - d for t, d in zip(totals, duplicates)])]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            replay([], data, [("synthetic", start.isoformat(), (start + dt.timedelta(hours=2)).isoformat())])
        return output.getvalue()

    def test_volume_floor_blocks_low_denominator_and_equal_boundary(self):
        for total in (2, 100):
            output = self.replay_sync([total] * 13, [total] * 13)
            self.assertIn("| none |", output)
        output = self.replay_sync([101] * 13, [20] * 13)
        self.assertIn("2026-10-07T13:00:00Z", output)

    def test_ratio_replay_uses_each_five_minute_sum_not_a_rolling_hour(self):
        output = self.replay_sync([10000] + [200] * 24, [5000] + [1] * 24)
        self.assertIn("50.00%", output)
        self.assertIn("| none |", output)
        output = self.replay_sync([200] * 13, [40] * 13)
        self.assertIn("2026-10-07T13:00:00Z", output)

    def test_workflow_uses_workflow_owned_scripts_and_same_prod_channel_step(self):
        workflow = (Path(__file__).resolve().parent.parent / "workflows/gcp_backend.yml").read_text()
        step = workflow.split("id: backend-route-alert", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("github.event.inputs.environment == 'prod'", step)
        self.assertIn("vars.SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS", step)
        self.assertIn('$DEPLOY_WORKFLOW_ROOT/.github/scripts/ensure_request_storm_alerts.py', step)
        self.assertIn('--notification-channels "$ALERT_CHANNELS"', step)


if __name__ == "__main__":
    unittest.main()
