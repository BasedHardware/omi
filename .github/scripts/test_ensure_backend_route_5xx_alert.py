from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ensure_backend_route_5xx_alert import (
    GROUP_BY_FIELDS,
    METRIC_CONFIG,
    METRIC_TYPE,
    POLICY_CONFIG,
    _aggregation,
    _condition,
    _comparison,
    _load_json,
    ensure_alert,
    main,
)

PROJECT = "based-hardware"
CHANNELS = "projects/based-hardware/notificationChannels/123"
CHANNELS_2 = "projects/based-hardware/notificationChannels/789"
POLICY = "projects/based-hardware/alertPolicies/456"
CONDITION_NAME = f"{POLICY}/conditions/1"
PROPAGATION_ERROR = (
    f'Cannot find metric(s) that match type = "{METRIC_TYPE}". '
    "If a metric was created recently, it could take up to 10 minutes to become available."
)
HOST = "https://api.omi.example"


def metric_config() -> dict[str, object]:
    return _load_json(METRIC_CONFIG)


def policy_body() -> dict[str, object]:
    return _load_json(POLICY_CONFIG)


def described_metric(*, mutate=None) -> dict[str, object]:
    body = {
        "name": f"projects/{PROJECT}/metrics/backend_route_5xx",
        "description": metric_config()["description"],
        "filter": metric_config()["filter"],
        "metricDescriptor": {
            "name": f"projects/{PROJECT}/metricDescriptors/{METRIC_TYPE}",
            "type": METRIC_TYPE,
            "displayName": "backend_route_5xx",
            **metric_config()["metricDescriptor"],
        },
        "labelExtractors": dict(metric_config()["labelExtractors"]),
        "createTime": "2026-10-01T00:00:00Z",
        "updateTime": "2026-10-02T00:00:00Z",
    }
    if mutate:
        mutate(body)
    return body


def described_policy(*, mutate=None) -> dict[str, object]:
    body = {
        "name": POLICY,
        **policy_body(),
        "notificationChannels": [CHANNELS],
        "creationRecord": {"mutatedBy": "deployer"},
        "mutationRecords": [],
    }
    body["conditions"][0]["name"] = CONDITION_NAME
    if mutate:
        mutate(body)
    return body


def extractor(field: str, key: str) -> str:
    expression = metric_config()["labelExtractors"][key]
    match = re.fullmatch(r'REGEXP_EXTRACT\(([\w.]+), "(.*)"\)', expression)
    assert match, expression
    assert match.group(1) == field, (key, match.group(1))
    extracted = re.match(match.group(2), FIELD_VALUES[field])
    return extracted.group(1) if extracted else ""


FIELD_VALUES: dict[str, str] = {}


def labels_for(url: str, method: str) -> dict[str, str]:
    FIELD_VALUES.update(
        {
            "httpRequest.requestUrl": url,
            "httpRequest.requestMethod": method,
        }
    )
    return {
        "method": extractor("httpRequest.requestMethod", "method"),
        "route": extractor("httpRequest.requestUrl", "route"),
    }


class MetricConfigTests(unittest.TestCase):
    def test_filter_is_scoped_to_prod_backend_request_log_5xx(self) -> None:
        config = metric_config()
        self.assertIn('resource.type="cloud_run_revision"', config["filter"])
        self.assertIn('resource.labels.project_id="based-hardware"', config["filter"])
        self.assertIn('resource.labels.service_name="backend"', config["filter"])
        self.assertIn("logName=\"projects/based-hardware/logs/run.googleapis.com%2Frequests\"", config["filter"])
        self.assertIn("httpRequest.status >= 500", config["filter"])
        self.assertIn("httpRequest.status < 600", config["filter"])
        self.assertNotIn("severity", config["filter"])

    def test_descriptor_and_extractors_declare_exactly_method_and_route(self) -> None:
        config = metric_config()
        descriptor = config["metricDescriptor"]
        self.assertEqual(descriptor["metricKind"], "DELTA")
        self.assertEqual(descriptor["valueType"], "INT64")
        self.assertEqual(descriptor["unit"], "1")
        declared = {label["key"]: label["valueType"] for label in descriptor["labels"]}
        self.assertEqual(declared, {"method": "STRING", "route": "STRING"})
        self.assertEqual(set(config["labelExtractors"]), {"method", "route"})
        for key, expression in config["labelExtractors"].items():
            self.assertTrue(expression.startswith("REGEXP_EXTRACT("), key)

    def test_known_and_unknown_families_extract_route_label(self) -> None:
        cases = {
            "/v1/users/people": "/v1/users/people",
            "/v1/dev/user/memories": "/v1/dev/user/memories",
            "/v1/dev/user/goals": "/v1/dev/user/goals",
            "/v3/memories": "/v3/memories",
            "/v1/conversations/from-segments": "/v1/conversations/from-segments",
            "/v2/voice-message/transcribe": "/v2/voice-message/transcribe",
            "/v9/new-feature/sub_path": "/v9/new-feature/sub_path",
            "/memory/search": "/memory/search",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                labels = labels_for(f"{HOST}{path}", "GET")
                self.assertEqual(labels["route"], expected)
                self.assertEqual(labels["method"], "GET")

    def test_capture_stops_before_first_invalid_segment(self) -> None:
        cases = {
            "/v1/conversations/abc123/reprocess": "/v1/conversations",
            "/v1/conversations/9b3d0f4e-8c1a-4f2b-9d7e-1a2b3c4d5e6f/reprocess": "/v1/conversations",
            "/v1/conversations/aBcDeFgH1234/reprocess": "/v1/conversations",
            "/v1/conversations/a%20b%2Fc%23d/reprocess": "/v1/conversations",
            "/v1/conversations/opaque%3A%3B%40/reprocess": "/v1/conversations",
            "/v3/memories/123": "/v3/memories",
            "/v1/a/b/c/d": "/v1/a/b/c",
            "/v1/dev/user/memories/extra/depth": "/v1/dev/user/memories",
        }
        for path, expected in cases.items():
            for suffix in ("", "/", "?force=true"):
                with self.subTest(path=path + suffix):
                    self.assertEqual(labels_for(f"{HOST}{path}{suffix}", "POST")["route"], expected)

    def test_invalid_first_segment_yields_no_partial_or_skipped_capture(self) -> None:
        for path in (
            "/abc123/foo",
            "/v1/abc123/foo",
            "/v1/abc123",
            "/v1/aBCdef/segment",
            "/UPPER/v1/users",
            "/123/users",
        ):
            with self.subTest(path=path):
                self.assertEqual(labels_for(f"{HOST}{path}", "GET")["route"], "")

    def test_query_fragment_trailing_slash_and_scheme(self) -> None:
        cases = {
            f"{HOST}/v3/memories?limit=50": "/v3/memories",
            f"{HOST}/v1/users/people/?include_stats=true&x=1": "/v1/users/people",
            f"{HOST}/v1/dev/user/goals?limit=100&include_inactive=true": "/v1/dev/user/goals",
            f"{HOST}/v1/conversations/from-segments/": "/v1/conversations/from-segments",
            f"{HOST}/v2/voice-message/transcribe?upload=1#frag": "/v2/voice-message/transcribe",
            "http://lb.internal/v3/memories": "/v3/memories",
            f"{HOST}/v1/users/people?next=/v3/memories&callback={HOST}/v1/dev/user/goals": "/v1/users/people",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(labels_for(url, "GET")["route"], expected)

    def test_root_and_unmatched_paths_extract_empty_route(self) -> None:
        for url in (HOST, f"{HOST}/", f"{HOST}/v1", f"{HOST}/?x=1", f"{HOST}/#frag"):
            with self.subTest(url=url):
                self.assertEqual(labels_for(url, "GET")["route"], "")

    def test_lowercase_slugs_and_all_letter_ids_remain_labels(self) -> None:
        cases = {
            "/v1/goals/goal_abcdefabcdef": "/v1/goals/goal_abcdefabcdef",
            "/v2/desktop/previews/feature-branch": "/v2/desktop/previews/feature-branch",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(labels_for(f"{HOST}{path}", "GET")["route"], expected)

    def test_method_whitelist_is_preserved(self) -> None:
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            self.assertEqual(labels_for(f"{HOST}/v3/memories", method)["method"], method)
        for method in ("get", "CONNECT", "PURGE", ""):
            self.assertEqual(labels_for(f"{HOST}/v3/memories", method)["method"], "")


class PolicyConfigTests(unittest.TestCase):
    def test_policy_body_matches_frozen_threshold_and_grouping(self) -> None:
        body = policy_body()
        self.assertEqual(body["displayName"], "Backend single-route 5xx regression")
        self.assertEqual(body["combiner"], "OR")
        self.assertIs(body["enabled"], True)
        self.assertEqual(body["notificationChannels"], [])
        condition = _condition(body)
        self.assertEqual(condition["displayName"], "One route exceeds 15 5xx in 15 minutes for 10 minutes")
        threshold = condition["conditionThreshold"]
        self.assertEqual(
            threshold["filter"],
            f'metric.type="{METRIC_TYPE}" AND resource.type="cloud_run_revision"'
            ' AND resource.labels.service_name="backend" AND metric.labels.method != ""'
            ' AND metric.labels.route != ""',
        )
        for retired in ("route_resource", "route_action", "status_class"):
            self.assertNotIn(retired, threshold["filter"])
        self.assertEqual(threshold["comparison"], "COMPARISON_GT")
        self.assertEqual(threshold["thresholdValue"], 15)
        self.assertEqual(threshold["duration"], "600s")
        self.assertEqual(threshold["trigger"], {"count": 1})
        (aggregation,) = threshold["aggregations"]
        self.assertEqual(aggregation["alignmentPeriod"], "900s")
        self.assertEqual(aggregation["perSeriesAligner"], "ALIGN_SUM")
        self.assertEqual(aggregation["crossSeriesReducer"], "REDUCE_SUM")
        self.assertEqual(list(aggregation["groupByFields"]), ["metric.label.method", "metric.label.route"])
        self.assertEqual(list(aggregation["groupByFields"]), list(GROUP_BY_FIELDS))
        for grouped in aggregation["groupByFields"]:
            self.assertNotIn("status", grouped)
            self.assertNotIn("resource.label", grouped)
            self.assertNotIn("route_resource", grouped)
            self.assertNotIn("route_action", grouped)

    def test_create_arguments_come_from_the_frozen_body(self) -> None:
        threshold = _condition(policy_body())["conditionThreshold"]
        self.assertEqual(_comparison(threshold), "> 15")
        aggregation = json.loads(_aggregation(threshold))
        self.assertEqual(aggregation["alignmentPeriod"], "900s")
        self.assertEqual(aggregation["perSeriesAligner"], "ALIGN_SUM")
        self.assertEqual(aggregation["crossSeriesReducer"], "REDUCE_SUM")
        self.assertEqual(list(aggregation["groupByFields"]), list(GROUP_BY_FIELDS))


class EnsureAlertTests(unittest.TestCase):
    def runner(self, calls: list[list[str]], **behaviour) -> object:
        state = {
            "metric": behaviour["metric"] if "metric" in behaviour else described_metric(),
            "policy": behaviour["policy"] if "policy" in behaviour else described_policy(),
            "listed": behaviour["listed"] if "listed" in behaviour else [POLICY],
            "created_policy": behaviour.get("created_policy"),
        }
        metric_describe_raw = behaviour.get("metric_describe_raw")
        policy_describe_raw = behaviour.get("policy_describe_raw")
        metric_write_errors = behaviour.get("metric_write_errors") or []
        policy_create_errors = behaviour.get("policy_create_errors") or []
        policy_update_errors = behaviour.get("policy_update_errors") or []
        rename_on_update = behaviour.get("rename_on_update")

        def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:3] == ["logging", "metrics"]:
                if "describe" in args:
                    if metric_describe_raw is not None:
                        return subprocess.CompletedProcess(args, 0, metric_describe_raw, "")
                    if state["metric"] is None:
                        return subprocess.CompletedProcess(args, 1, "", "NOT_FOUND: metric not found")
                    return subprocess.CompletedProcess(args, 0, json.dumps(state["metric"]), "")
                if "create" in args or "update" in args:
                    if metric_write_errors:
                        return subprocess.CompletedProcess(args, 1, "", metric_write_errors.pop(0))
                    state["metric"] = described_metric()
                    return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"]:
                if "list" in args:
                    listed = "".join(f"{policy}\n" for policy in state["listed"])
                    return subprocess.CompletedProcess(args, 0, listed, "")
                if "create" in args:
                    if policy_create_errors:
                        return subprocess.CompletedProcess(args, 1, "", policy_create_errors.pop(0))
                    state["listed"] = [POLICY]
                    state["policy"] = state["created_policy"] or described_policy()
                    return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
                if "update" in args:
                    if policy_update_errors:
                        return subprocess.CompletedProcess(args, 1, "", policy_update_errors.pop(0))
                    sent = json.loads(next(v.removeprefix("--policy=") for v in args if v.startswith("--policy=")))
                    sent["name"] = POLICY
                    if rename_on_update:
                        sent["conditions"][0]["name"] = f"{POLICY}/conditions/99"
                    state["policy"] = sent
                    return subprocess.CompletedProcess(args, 0, "", "")
                if "describe" in args:
                    if policy_describe_raw is not None:
                        return subprocess.CompletedProcess(args, 0, policy_describe_raw, "")
                    if state["policy"] is None:
                        return subprocess.CompletedProcess(args, 1, "", "NOT_FOUND: policy not found")
                    return subprocess.CompletedProcess(args, 0, json.dumps(state["policy"]), "")
            raise AssertionError(f"unexpected gcloud command: {args}")

        return run

    def writes(self, calls: list[list[str]], *groups: str) -> list[list[str]]:
        return [
            call
            for call in calls
            if tuple(call[1:3]) in groups and ("create" in call or "update" in call or "delete" in call)
        ]

    def test_unchanged_metric_and_policy_make_no_writes(self) -> None:
        calls: list[list[str]] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT, notification_channels=CHANNELS, runner=self.runner(calls), sleep=lambda _: None
            ),
            POLICY,
        )
        self.assertEqual(self.writes(calls, ("logging", "metrics"), ("monitoring", "policies")), [])
        metric_describe = next(call for call in calls if call[1:3] == ["logging", "metrics"] and "describe" in call)
        self.assertIn("--format=json", metric_describe)
        policy_describes = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "describe" in call]
        self.assertEqual(len(policy_describes), 1)

    def test_reordered_fields_and_server_metadata_make_no_writes(self) -> None:
        def mutate(body: dict) -> None:
            body["notificationChannels"] = [CHANNELS_2, CHANNELS]
            body["conditions"][0]["conditionThreshold"]["aggregations"][0]["groupByFields"] = [
                "metric.label.route",
                "metric.label.method",
            ]
            body["mutationRecords"] = [{"mutatedBy": "someone-else"}]

        calls: list[list[str]] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT,
                notification_channels=f"{CHANNELS},{CHANNELS_2}",
                runner=self.runner(calls, policy=described_policy(mutate=mutate)),
                sleep=lambda _: None,
            ),
            POLICY,
        )
        self.assertEqual(self.writes(calls, ("logging", "metrics"), ("monitoring", "policies")), [])

    def test_policy_drift_updates_once_and_preserves_condition_name(self) -> None:
        def mutate(body: dict) -> None:
            threshold = body["conditions"][0]["conditionThreshold"]
            threshold["thresholdValue"] = 30
            threshold["filter"] = threshold["filter"].replace('metric.labels.route != ""', 'metric.labels.route != "x"')
            body["conditions"][0]["displayName"] = "retired condition title"
            body["documentation"]["content"] = "stale documentation"
            body["notificationChannels"] = ["projects/based-hardware/notificationChannels/999"]

        calls: list[list[str]] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, policy=described_policy(mutate=mutate)),
                sleep=lambda _: None,
            ),
            POLICY,
        )
        updates = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call]
        self.assertEqual(len(updates), 1)
        sent = json.loads(next(v.removeprefix("--policy=") for v in updates[0] if v.startswith("--policy=")))
        self.assertEqual(sent["conditions"][0]["name"], CONDITION_NAME)
        self.assertEqual(sent["conditions"][0]["displayName"], "One route exceeds 15 5xx in 15 minutes for 10 minutes")
        self.assertEqual(sent["conditions"][0]["conditionThreshold"]["thresholdValue"], 15)
        self.assertEqual(sent["notificationChannels"], [CHANNELS])
        describes = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "describe" in call]
        self.assertEqual(len(describes), 2)
        self.assertEqual(sum("create" in call for call in calls), 0)

    def test_isolated_drift_fields_update_once_preserving_name(self) -> None:
        def threshold(key: str, value: object):
            return lambda body: body["conditions"][0]["conditionThreshold"].__setitem__(key, value)

        def aggregation(key: str, value: object):
            return lambda body: body["conditions"][0]["conditionThreshold"]["aggregations"][0].__setitem__(key, value)

        cases = {
            "condition filter": threshold("filter", 'metric.type="logging.googleapis.com/user/other"'),
            "threshold value": threshold("thresholdValue", 30),
            "duration": threshold("duration", "300s"),
            "trigger count": lambda body: body["conditions"][0]["conditionThreshold"]["trigger"].__setitem__(
                "count", 2
            ),
            "condition title": lambda body: body["conditions"][0].__setitem__("displayName", "retired title"),
            "alignment period": aggregation("alignmentPeriod", "600s"),
            "aligner": aggregation("perSeriesAligner", "ALIGN_MEAN"),
            "reducer": aggregation("crossSeriesReducer", "REDUCE_MAX"),
            "group-by fields": aggregation("groupByFields", ["metric.label.route"]),
            "notification channels": lambda body: body.__setitem__("notificationChannels", [CHANNELS_2]),
        }
        for name, mutate in cases.items():
            with self.subTest(drift=name):
                calls: list[list[str]] = []
                self.assertEqual(
                    ensure_alert(
                        project=PROJECT,
                        notification_channels=CHANNELS,
                        runner=self.runner(calls, policy=described_policy(mutate=mutate)),
                        sleep=lambda _: None,
                    ),
                    POLICY,
                )
                updates = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call]
                self.assertEqual(len(updates), 1)
                sent = json.loads(next(v.removeprefix("--policy=") for v in updates[0] if v.startswith("--policy=")))
                self.assertEqual(sent["conditions"][0]["name"], CONDITION_NAME)
                self.assertEqual(
                    sent["conditions"][0]["conditionThreshold"],
                    policy_body()["conditions"][0]["conditionThreshold"],
                )
                self.assertEqual(self.writes(calls, ("logging", "metrics")), [])
                self.assertEqual(sum("create" in call for call in calls), 0)

    def test_documentation_and_enabled_drift_update(self) -> None:
        cases = {
            "content suffix": lambda body: body["documentation"].__setitem__(
                "content", body["documentation"]["content"] + " Extra sentence."
            ),
            "MIME type": lambda body: body["documentation"].__setitem__("mimeType", "text/plain"),
            "enabled": lambda body: body.__setitem__("enabled", False),
        }
        for name, mutate in cases.items():
            with self.subTest(drift=name):
                calls: list[list[str]] = []
                ensure_alert(
                    project=PROJECT,
                    notification_channels=CHANNELS,
                    runner=self.runner(calls, policy=described_policy(mutate=mutate)),
                    sleep=lambda _: None,
                )
                updates = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call]
                self.assertEqual(len(updates), 1)

    def test_metric_filter_or_extractor_drift_updates_in_place(self) -> None:
        cases = {
            "filter": lambda body: body.__setitem__("filter", body["filter"].replace("< 600", "<= 600")),
            "extractor": lambda body: body["labelExtractors"].__setitem__(
                "route", 'REGEXP_EXTRACT(httpRequest.requestUrl, "^https?://[^/?#]+(/old)$")'
            ),
            "stale extractor keys": lambda body: body.__setitem__(
                "labelExtractors",
                {**body["labelExtractors"], "route_action": "REGEXP_EXTRACT(httpRequest.requestUrl, \"x\")"},
            ),
            "missing extractors": lambda body: body.pop("labelExtractors"),
        }
        for name, mutate in cases.items():
            with self.subTest(drift=name):
                calls: list[list[str]] = []
                ensure_alert(
                    project=PROJECT,
                    notification_channels=CHANNELS,
                    runner=self.runner(calls, metric=described_metric(mutate=mutate)),
                    sleep=lambda _: None,
                )
                metric_updates = [call for call in calls if call[1:3] == ["logging", "metrics"] and "update" in call]
                self.assertEqual(len(metric_updates), 1)
                self.assertIn("backend_route_5xx", metric_updates[0])
                self.assertIn(f"--config-from-file={METRIC_CONFIG}", metric_updates[0])
                self.assertEqual(self.writes(calls, ("monitoring", "policies")), [])
                self.assertEqual(
                    [
                        call
                        for call in calls
                        if call[1:3] == ["logging", "metrics"] and ("create" in call or "delete" in call)
                    ],
                    [],
                )

    def test_metric_metadata_differences_make_no_writes(self) -> None:
        def mutate(body: dict) -> None:
            body["name"] = f"projects/{PROJECT}/metrics/other_name"
            body["description"] = "server-side description differs"
            body["metricDescriptor"]["displayName"] = "different"
            body["metricDescriptor"]["launchStage"] = "GA"

        calls: list[list[str]] = []
        ensure_alert(
            project=PROJECT,
            notification_channels=CHANNELS,
            runner=self.runner(calls, metric=described_metric(mutate=mutate)),
            sleep=lambda _: None,
        )
        self.assertEqual(self.writes(calls, ("logging", "metrics")), [])

    def test_missing_metric_and_policy_are_created_with_frozen_shape(self) -> None:
        calls: list[list[str]] = []
        sleeps: list[float] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(
                    calls,
                    metric=None,
                    policy=None,
                    listed=[],
                    policy_create_errors=[PROPAGATION_ERROR],
                ),
                sleep=sleeps.append,
            ),
            POLICY,
        )
        self.assertEqual(sleeps, [30])
        metric_creates = [call for call in calls if call[1:3] == ["logging", "metrics"] and "create" in call]
        self.assertEqual(len(metric_creates), 1)
        self.assertIn(f"--config-from-file={METRIC_CONFIG}", metric_creates[0])
        self.assertEqual([call for call in calls if call[1:3] == ["logging", "metrics"] and "update" in call], [])
        creates = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "create" in call]
        self.assertEqual(len(creates), 2)
        create_call = creates[-1]
        self.assertIn("--duration=600s", create_call)
        self.assertIn("--if=> 15", create_call)
        self.assertIn("--trigger-count=1", create_call)
        self.assertIn(f"--notification-channels={CHANNELS}", create_call)
        aggregation = json.loads(
            next(v.removeprefix("--aggregation=") for v in create_call if v.startswith("--aggregation="))
        )
        self.assertEqual(aggregation["alignmentPeriod"], "900s")
        self.assertEqual(aggregation["perSeriesAligner"], "ALIGN_SUM")
        self.assertEqual(aggregation["crossSeriesReducer"], "REDUCE_SUM")
        self.assertEqual(list(aggregation["groupByFields"]), list(GROUP_BY_FIELDS))
        self.assertEqual([call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call], [])

    def test_created_policy_drift_updates_preserving_fresh_condition_name(self) -> None:
        def mutate(body: dict) -> None:
            body["documentation"]["mimeType"] = ""
            body["notificationChannels"] = []

        calls: list[list[str]] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(
                    calls,
                    policy=None,
                    listed=[],
                    created_policy=described_policy(mutate=mutate),
                ),
                sleep=lambda _: None,
            ),
            POLICY,
        )
        updates = [call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call]
        self.assertEqual(len(updates), 1)
        sent = json.loads(next(v.removeprefix("--policy=") for v in updates[0] if v.startswith("--policy=")))
        self.assertEqual(sent["conditions"][0]["name"], CONDITION_NAME)

    def test_update_retries_only_metric_propagation(self) -> None:
        drifted = described_policy(
            mutate=lambda body: body["conditions"][0]["conditionThreshold"].__setitem__("thresholdValue", 30)
        )
        calls: list[list[str]] = []
        sleeps: list[float] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, policy=drifted, policy_update_errors=[PROPAGATION_ERROR]),
                sleep=sleeps.append,
            ),
            POLICY,
        )
        self.assertEqual(sleeps, [30])
        self.assertEqual(sum(call[1:3] == ["monitoring", "policies"] and "update" in call for call in calls), 2)

    def test_update_does_not_retry_permanent_errors(self) -> None:
        drifted = described_policy(
            mutate=lambda body: body["conditions"][0]["conditionThreshold"].__setitem__("thresholdValue", 30)
        )
        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "PERMISSION_DENIED"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(
                    calls, policy=drifted, policy_update_errors=["PERMISSION_DENIED: monitoring.alertPolicies.update"]
                ),
                sleep=lambda _: self.fail("permanent errors must not sleep"),
            )
        self.assertEqual(sum(call[1:3] == ["monitoring", "policies"] and "update" in call for call in calls), 1)

    def test_duplicate_policies_fail(self) -> None:
        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, listed=[POLICY, f"{POLICY}9"]),
                sleep=lambda _: None,
            )
        self.assertEqual(
            sum(call[1:3] == ["monitoring", "policies"] and ("create" in call or "update" in call) for call in calls),
            0,
        )

    def test_post_update_drift_fails_visibly(self) -> None:
        drifted = described_policy(
            mutate=lambda body: body["conditions"][0]["conditionThreshold"].__setitem__("thresholdValue", 30)
        )
        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "drift"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, policy=drifted, policy_describe_raw=json.dumps(drifted)),
                sleep=lambda _: None,
            )
        self.assertEqual(sum(call[1:3] == ["monitoring", "policies"] and "update" in call for call in calls), 1)

    def test_condition_name_change_across_update_fails(self) -> None:
        drifted = described_policy(
            mutate=lambda body: body["conditions"][0]["conditionThreshold"].__setitem__("thresholdValue", 30)
        )
        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "condition resource name changed"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, policy=drifted, rename_on_update=True),
                sleep=lambda _: None,
            )
        self.assertEqual(sum(call[1:3] == ["monitoring", "policies"] and "update" in call for call in calls), 1)

    def test_second_run_makes_no_additional_writes(self) -> None:
        drifted_metric = described_metric(
            mutate=lambda body: body["labelExtractors"].__setitem__(
                "route", 'REGEXP_EXTRACT(httpRequest.requestUrl, "^https?://[^/?#]+(/old)$")'
            )
        )
        drifted_policy = described_policy(
            mutate=lambda body: body["conditions"][0]["conditionThreshold"].__setitem__("thresholdValue", 30)
        )
        calls: list[list[str]] = []
        run = self.runner(calls, metric=drifted_metric, policy=drifted_policy)
        ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=run, sleep=lambda _: None)
        first_writes = self.writes(calls, ("logging", "metrics"), ("monitoring", "policies"))
        self.assertEqual(len(first_writes), 2)
        calls.clear()
        self.assertEqual(
            ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=run, sleep=lambda _: None),
            POLICY,
        )
        self.assertEqual(self.writes(calls, ("logging", "metrics"), ("monitoring", "policies")), [])
        self.assertTrue(any("describe" in call for call in calls))

    def test_missing_or_ambiguous_condition_identity_refuses_update(self) -> None:
        def drift(body: dict) -> None:
            body["conditions"][0]["conditionThreshold"]["thresholdValue"] = 30

        cases = {
            "unnamed condition": lambda body: (drift(body), body["conditions"][0].pop("name")),
            "empty name": lambda body: (drift(body), body["conditions"][0].__setitem__("name", "")),
            "no conditions": lambda body: body.__setitem__("conditions", []),
            "two conditions": lambda body: (
                drift(body),
                body["conditions"].append({**body["conditions"][0], "name": f"{POLICY}/conditions/2"}),
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(shape=name):
                calls: list[list[str]] = []
                with self.assertRaisesRegex(RuntimeError, "condition"):
                    ensure_alert(
                        project=PROJECT,
                        notification_channels=CHANNELS,
                        runner=self.runner(calls, policy=described_policy(mutate=mutate)),
                        sleep=lambda _: None,
                    )
                self.assertEqual(
                    [
                        call
                        for call in calls
                        if call[1:3] == ["monitoring", "policies"] and ("create" in call or "update" in call)
                    ],
                    [],
                )

    def test_metric_describe_invalid_json_fails(self) -> None:
        for raw, message in (("not json", "invalid JSON"), ("[]", "non-object")):
            with self.subTest(raw=raw):
                calls: list[list[str]] = []
                with self.assertRaisesRegex(RuntimeError, message):
                    ensure_alert(
                        project=PROJECT,
                        notification_channels=CHANNELS,
                        runner=self.runner(calls, metric_describe_raw=raw),
                        sleep=lambda _: None,
                    )
                self.assertEqual(self.writes(calls, ("logging", "metrics")), [])

    def test_policy_describe_invalid_json_fails(self) -> None:
        for raw, message in (("not json", "invalid JSON"), ("[1,2]", "non-object")):
            with self.subTest(raw=raw):
                calls: list[list[str]] = []
                with self.assertRaisesRegex(RuntimeError, message):
                    ensure_alert(
                        project=PROJECT,
                        notification_channels=CHANNELS,
                        runner=self.runner(calls, policy_describe_raw=raw),
                        sleep=lambda _: None,
                    )
                self.assertEqual(self.writes(calls, ("monitoring", "policies")), [])

    def test_metric_describe_permanent_error_fails(self) -> None:
        def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                return subprocess.CompletedProcess(args, 1, "", "PERMISSION_DENIED: logging.logMetrics.get")
            self.fail(f"unexpected gcloud command: {args}")
            raise AssertionError("unreachable")

        with self.assertRaisesRegex(RuntimeError, "PERMISSION_DENIED"):
            ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=run, sleep=lambda _: None)

    def test_arguments_reject_empty_or_duplicate_channels(self) -> None:
        def no_gcloud(*args: object, **kwargs: object) -> None:
            self.fail("gcloud called")

        with self.assertRaisesRegex(ValueError, "project must not be empty"):
            ensure_alert(project=" ", notification_channels=CHANNELS, runner=no_gcloud)
        with self.assertRaisesRegex(ValueError, "without empty entries"):
            ensure_alert(project=PROJECT, notification_channels="", runner=no_gcloud)
        with self.assertRaisesRegex(ValueError, "without empty entries"):
            ensure_alert(project=PROJECT, notification_channels=f"{CHANNELS},", runner=no_gcloud)
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            ensure_alert(project=PROJECT, notification_channels=f"{CHANNELS},{CHANNELS}", runner=no_gcloud)
        with self.assertRaises(SystemExit):
            main(["--project", PROJECT])


def step_run_block(workflow: str, step_name: str) -> str:
    start = workflow.index(f"- name: {step_name}")
    run_at = workflow.index("run: |", start)
    block_start = workflow.index("\n", run_at) + 1
    lines: list[str] = []
    for line in workflow[block_start:].splitlines(keepends=True):
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line[10:] if line.strip() else "\n")
    return "".join(lines)


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.workflow = (cls.root / ".github/workflows/gcp_backend.yml").read_text(encoding="utf-8")
        deploy = cls.workflow.index("- name: Deploy backend stack")
        provision = cls.workflow.index("- name: Provision backend route 5xx alert")
        report = cls.workflow.index("- name: Report backend route 5xx alert provisioning failure")
        firestore = cls.workflow.index("- name: Provision Firestore missing-index alert")
        assert deploy < provision < report < firestore, "step order: deploy < provision < report < firestore"
        cls.step = cls.workflow[provision:report]
        cls.report_step = cls.workflow[report:firestore]

    def test_provision_step_is_production_only_and_never_blocks_deploy(self) -> None:
        step = self.step
        self.assertIn("id: backend-route-alert", step)
        self.assertIn("if: github.event.inputs.environment == 'prod'", step)
        self.assertIn("continue-on-error: true", step)
        self.assertIn("timeout-minutes: 15", step)
        self.assertIn("ALERT_CHANNELS: ${{ vars.SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS }}", step)
        self.assertIn("PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}", step)

    def test_provision_step_runs_workflow_owned_script_with_guards(self) -> None:
        step = self.step
        self.assertIn('test -n "${DEPLOY_WORKFLOW_ROOT:-}"', step)
        self.assertIn('test -f "$DEPLOY_WORKFLOW_ROOT/.github/scripts/ensure_backend_route_5xx_alert.py"', step)
        self.assertIn('python3 "$DEPLOY_WORKFLOW_ROOT/.github/scripts/ensure_backend_route_5xx_alert.py"', step)
        self.assertIn('--project "$PROJECT_ID"', step)
        self.assertIn('--notification-channels "$ALERT_CHANNELS"', step)
        self.assertIn("GITHUB_STEP_SUMMARY", step)
        self.assertTrue((self.root / ".github/scripts/ensure_backend_route_5xx_alert.py").is_file())

    def test_reporting_step_warns_without_blocking_deploy(self) -> None:
        step = self.report_step
        self.assertIn("always()", step)
        self.assertIn("github.event.inputs.environment == 'prod'", step)
        self.assertIn("steps.backend-route-alert.outcome == 'failure'", step)
        self.assertIn("continue-on-error: true", step)
        self.assertIn("::warning", step)
        self.assertIn("GITHUB_STEP_SUMMARY", step)
        self.assertIn("backend-route-5xx", step)
        self.assertTrue((self.root / "backend/docs/runbooks/backend-route-5xx.md").is_file())

    @unittest.skipUnless(shutil.which("bash"), "bash is required to execute the reporting step")
    def test_reporting_step_shell_emits_warning_and_summary(self) -> None:
        block = step_run_block(self.workflow, "Report backend route 5xx alert provisioning failure")
        self.assertIn("::warning", block)
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            summary.touch()
            result = subprocess.run(
                ["bash", "-euo", "pipefail"],
                input=block,
                text=True,
                capture_output=True,
                env={"GITHUB_STEP_SUMMARY": str(summary), "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("::warning", result.stdout)
            content = summary.read_text(encoding="utf-8")
            self.assertIn("deployment remains successful", content)
            self.assertIn("backend-route-5xx", content)


if __name__ == "__main__":
    unittest.main()
