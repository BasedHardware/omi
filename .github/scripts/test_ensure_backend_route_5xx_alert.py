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
POLICY = "projects/based-hardware/alertPolicies/456"
PROPAGATION_ERROR = (
    f'Cannot find metric(s) that match type = "{METRIC_TYPE}". '
    "If a metric was created recently, it could take up to 10 minutes to become available."
)
HOST = "https://api.omi.example"


def metric_config() -> dict[str, object]:
    return _load_json(METRIC_CONFIG)


def policy_body() -> dict[str, object]:
    return _load_json(POLICY_CONFIG)


def described_policy(*, mutate=None) -> str:
    body = {"name": POLICY, **policy_body(), "notificationChannels": [CHANNELS]}
    body["conditions"][0]["name"] = f"{POLICY}/conditions/1"
    body["creationRecord"] = {"mutatedBy": "deployer"}
    body["mutationRecords"] = []
    if mutate:
        mutate(body)
    return json.dumps(body)


def extractor(field: str, key: str, config: dict[str, object] | None = None) -> str:
    extractors = (config or metric_config())["labelExtractors"]
    expression = extractors[key]
    match = re.fullmatch(r'REGEXP_EXTRACT\(([\w.]+), "(.*)"\)', expression)
    assert match, expression
    assert match.group(1) == field, (key, match.group(1))
    extracted = re.match(match.group(2), field_value(field))
    return extracted.group(1) if extracted else ""


FIELD_VALUES: dict[str, str] = {}


def field_value(field: str) -> str:
    return FIELD_VALUES[field]


def labels_for(url: str, method: str, status: int) -> dict[str, str]:
    FIELD_VALUES.update(
        {
            "httpRequest.requestUrl": url,
            "httpRequest.requestMethod": method,
            "httpRequest.status": str(status),
        }
    )
    return {
        "method": extractor("httpRequest.requestMethod", "method"),
        "route": extractor("httpRequest.requestUrl", "route"),
        "route_resource": extractor("httpRequest.requestUrl", "route_resource"),
        "route_action": extractor("httpRequest.requestUrl", "route_action"),
        "status_class": extractor("httpRequest.status", "status_class"),
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

    def test_descriptor_and_extractors_declare_the_same_label_set(self) -> None:
        config = metric_config()
        descriptor = config["metricDescriptor"]
        self.assertEqual(descriptor["metricKind"], "DELTA")
        self.assertEqual(descriptor["valueType"], "INT64")
        declared = {label["key"]: label["valueType"] for label in descriptor["labels"]}
        self.assertEqual(
            declared,
            {
                "method": "STRING",
                "route": "STRING",
                "route_resource": "STRING",
                "route_action": "STRING",
                "status_class": "STRING",
            },
        )
        self.assertEqual(set(config["labelExtractors"]), set(declared))
        for key, expression in config["labelExtractors"].items():
            self.assertTrue(expression.startswith("REGEXP_EXTRACT("), key)

    def test_static_incident_and_chronic_routes_extract_route_label(self) -> None:
        cases = {
            "GET /v1/users/people": ("GET", "/v1/users/people"),
            "GET /v1/dev/user/memories": ("GET", "/v1/dev/user/memories"),
            "GET /v1/dev/user/goals": ("GET", "/v1/dev/user/goals"),
            "POST /v3/memories": ("POST", "/v3/memories"),
            "GET /v3/memories": ("GET", "/v3/memories"),
            "POST /v1/conversations/from-segments": ("POST", "/v1/conversations/from-segments"),
            "POST /v2/voice-message/transcribe": ("POST", "/v2/voice-message/transcribe"),
        }
        for name, (method, path) in cases.items():
            with self.subTest(route=name):
                labels = labels_for(f"{HOST}{path}", method, 504)
                self.assertEqual(labels["route"], path)
                self.assertEqual(labels["route_resource"], "")
                self.assertEqual(labels["route_action"], "")
                self.assertEqual(labels["method"], method)
                self.assertEqual(labels["status_class"], "5")

    def test_static_routes_tolerate_trailing_slash_and_query(self) -> None:
        for url in (
            f"{HOST}/v3/memories?limit=50",
            f"{HOST}/v1/users/people/?include_stats=true&x=1",
            f"{HOST}/v1/dev/user/goals?limit=100&include_inactive=true",
            f"{HOST}/v1/conversations/from-segments/",
            f"{HOST}/v2/voice-message/transcribe?upload=1#frag",
        ):
            with self.subTest(url=url):
                self.assertNotEqual(labels_for(url, "GET", 500)["route"], "")

    def test_reprocess_route_extracts_resource_and_action_with_any_id(self) -> None:
        ids = (
            "abc123",
            "987654321",
            "9b3d0f4e-8c1a-4f2b-9d7e-1a2b3c4d5e6f",
            "a%20b%2Fc%23d",
            "opaque%3A%3B%40",
        )
        for conversation_id in ids:
            for url in (
                f"{HOST}/v1/conversations/{conversation_id}/reprocess",
                f"{HOST}/v1/conversations/{conversation_id}/reprocess/",
                f"{HOST}/v1/conversations/{conversation_id}/reprocess?force=true",
            ):
                with self.subTest(url=url):
                    labels = labels_for(url, "POST", 500)
                    self.assertEqual(labels["route"], "")
                    self.assertEqual(labels["route_resource"], "/v1/conversations")
                    self.assertEqual(labels["route_action"], "reprocess")

    def test_unknown_paths_extract_empty_route_labels(self) -> None:
        for url in (
            f"{HOST}/v9/unknown",
            f"{HOST}/v1/users/people/extra",
            f"{HOST}/v3/memories/123",
            f"{HOST}/v1/conversations",
            f"{HOST}/v1/conversations/abc123",
            f"{HOST}/v1/conversations/abc123/reprocess/extra",
            f"{HOST}/v1/conversations/reprocess",
            f"{HOST}/",
            f"{HOST}",
        ):
            with self.subTest(url=url):
                labels = labels_for(url, "GET", 503)
                self.assertEqual(labels["route"], "")
                self.assertEqual(labels["route_resource"], "")
                self.assertEqual(labels["route_action"], "")

    def test_host_and_query_never_become_labels(self) -> None:
        labels = labels_for(f"{HOST}/v1/users/people?next=/v3/memories&callback={HOST}/v1/dev/user/goals", "GET", 500)
        self.assertEqual(labels["route"], "/v1/users/people")
        self.assertNotIn(HOST, labels.values())
        self.assertNotIn("/v3/memories", (labels["route_resource"], labels["route_action"]))

    def test_http_scheme_variants_and_method_bounds(self) -> None:
        self.assertEqual(labels_for("http://lb.internal/v3/memories", "GET", 500)["route"], "/v3/memories")
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            self.assertEqual(labels_for(f"{HOST}/v3/memories", method, 500)["method"], method)
        for method in ("get", "CONNECT", "PURGE", ""):
            self.assertEqual(labels_for(f"{HOST}/v3/memories", method, 500)["method"], "")

    def test_status_class_only_matches_5xx(self) -> None:
        for status, expected in ((500, "5"), (503, "5"), (599, "5"), (404, ""), (499, ""), (600, ""), (50, "")):
            with self.subTest(status=status):
                self.assertEqual(labels_for(f"{HOST}/v3/memories", "GET", status)["status_class"], expected)


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
        self.assertIn(f'metric.type="{METRIC_TYPE}"', threshold["filter"])
        self.assertIn('resource.type="cloud_run_revision"', threshold["filter"])
        self.assertIn('resource.labels.service_name="backend"', threshold["filter"])
        self.assertIn('metric.labels.method != ""', threshold["filter"])
        self.assertIn('metric.labels.route != ""', threshold["filter"])
        self.assertIn('metric.labels.route_resource != ""', threshold["filter"])
        self.assertEqual(threshold["comparison"], "COMPARISON_GT")
        self.assertEqual(threshold["thresholdValue"], 15)
        self.assertEqual(threshold["duration"], "600s")
        self.assertEqual(threshold["trigger"], {"count": 1})
        (aggregation,) = threshold["aggregations"]
        self.assertEqual(aggregation["alignmentPeriod"], "900s")
        self.assertEqual(aggregation["perSeriesAligner"], "ALIGN_SUM")
        self.assertEqual(aggregation["crossSeriesReducer"], "REDUCE_SUM")
        self.assertEqual(list(aggregation["groupByFields"]), list(GROUP_BY_FIELDS))
        for grouped in aggregation["groupByFields"]:
            self.assertNotIn("status", grouped)
            self.assertNotIn("resource.label", grouped)

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
        def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["logging", "metrics"] and ("create" in args or "update" in args):
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, behaviour.get("listed", POLICY + "\n"), "")
            if args[1:3] == ["monitoring", "policies"] and "create" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                errors = behaviour.get("update_errors") or []
                if errors:
                    return subprocess.CompletedProcess(args, 1, "", errors.pop(0))
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, behaviour.get("described", described_policy()), "")
            raise AssertionError(f"unexpected gcloud command: {args}")

        return run

    def test_existing_metric_and_policy_update_and_verify(self) -> None:
        calls: list[list[str]] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT, notification_channels=CHANNELS, runner=self.runner(calls), sleep=lambda _: None
            ),
            POLICY,
        )
        self.assertEqual(sum("create" in call for call in calls), 0)
        metric_update = [call for call in calls if call[1:3] == ["logging", "metrics"] and "update" in call]
        self.assertEqual(len(metric_update), 1)
        self.assertIn(f"--config-from-file={METRIC_CONFIG}", metric_update[0])
        policy_update = next(call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call)
        body = json.loads(next(v.removeprefix("--policy=") for v in policy_update if v.startswith("--policy=")))
        self.assertEqual(body["notificationChannels"], [CHANNELS])
        self.assertEqual(body["displayName"], "Backend single-route 5xx regression")
        (aggregation,) = body["conditions"][0]["conditionThreshold"]["aggregations"]
        self.assertEqual(list(aggregation["groupByFields"]), list(GROUP_BY_FIELDS))
        self.assertEqual(sum("describe" in call for call in calls), 2)

    def test_missing_metric_and_policy_are_created_with_frozen_shape(self) -> None:
        calls: list[list[str]] = []
        create_attempts = {"n": 0}

        def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                return subprocess.CompletedProcess(args, 1, "", "NOT_FOUND: metric not found")
            if args[1:3] == ["logging", "metrics"] and "create" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "create" in args:
                create_attempts["n"] += 1
                if create_attempts["n"] == 1:
                    return subprocess.CompletedProcess(args, 1, "", PROPAGATION_ERROR)
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, described_policy(), "")
            raise AssertionError(f"unexpected gcloud command: {args}")

        sleeps: list[float] = []
        self.assertEqual(
            ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=run, sleep=sleeps.append),
            POLICY,
        )
        self.assertEqual(create_attempts["n"], 2)
        self.assertEqual(sleeps, [30])
        create_call = next(call for call in calls if call[1:3] == ["monitoring", "policies"] and "create" in call)
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

    def test_update_retries_only_metric_propagation(self) -> None:
        calls: list[list[str]] = []
        sleeps: list[float] = []
        self.assertEqual(
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, update_errors=[PROPAGATION_ERROR]),
                sleep=sleeps.append,
            ),
            POLICY,
        )
        self.assertEqual(sleeps, [30])
        self.assertEqual(sum(call[1:3] == ["monitoring", "policies"] and "update" in call for call in calls), 2)

    def test_update_does_not_retry_permanent_errors(self) -> None:
        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "PERMISSION_DENIED"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, update_errors=["PERMISSION_DENIED: monitoring.alertPolicies.update"]),
                sleep=lambda _: self.fail("permanent errors must not sleep"),
            )
        self.assertEqual(sum(call[1:3] == ["monitoring", "policies"] and "update" in call for call in calls), 1)

    def test_duplicate_policies_fail(self) -> None:
        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, listed=f"{POLICY}\n{POLICY}9\n"),
                sleep=lambda _: None,
            )
        self.assertEqual(
            sum(call[1:3] == ["monitoring", "policies"] and ("create" in call or "update" in call) for call in calls),
            0,
        )

    def test_describe_drift_fails_visibly(self) -> None:
        def mutate(body: dict) -> None:
            body["conditions"][0]["conditionThreshold"]["thresholdValue"] = 30
            body["conditions"][0]["conditionThreshold"]["aggregations"][0]["groupByFields"] = ["metric.label.route"]
            body["enabled"] = False

        calls: list[list[str]] = []
        with self.assertRaisesRegex(RuntimeError, "drift"):
            ensure_alert(
                project=PROJECT,
                notification_channels=CHANNELS,
                runner=self.runner(calls, described=described_policy(mutate=mutate)),
                sleep=lambda _: None,
            )

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
