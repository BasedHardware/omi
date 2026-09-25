"""Contracts for the live Grafana finalization-alert release gate."""

from __future__ import annotations

import copy
import io
import json
import runpy
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_live_alert_route.py"


@pytest.fixture(scope="module")
def verifier() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def _inputs(verifier: SimpleNamespace) -> tuple[dict, dict, dict, dict, list[dict]]:
    rules = copy.deepcopy(verifier._committed_rules())
    datasource = {"status": "OK", "message": "Data source is working"}
    up_query = {
        "status": "success",
        "data": {"result": [{"metric": {"job": job}, "value": [1, "1"]} for job in verifier.REQUIRED_JOBS]},
    }
    metric_query = {
        "status": "success",
        "data": {
            "result": [
                {"metric": {"__name__": name, "job": job}, "value": [1, "1"]}
                for name in verifier.REQUIRED_METRICS
                for job in verifier.REQUIRED_JOBS
            ]
        },
    }
    receiver = next(iter(rules.values()))["notification_settings"]["receiver"]
    contact_points = [
        {
            "name": receiver,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]
    return rules, datasource, up_query, metric_query, contact_points


def test_accepts_exact_active_rule_healthy_datasource_and_receiver(verifier: SimpleNamespace) -> None:
    assert verifier.validate_live_route(*_inputs(verifier), phase="postrollout") == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("rule", "does not match"),
        ("paused", "unpaused"),
        ("datasource", "health is not OK"),
        ("pusher", "scrape targets are not both healthy"),
        ("metrics", "telemetry sources are missing"),
        ("receiver", "receiver is missing"),
    ],
)
def test_rejects_unprotected_live_alert_paths(verifier: SimpleNamespace, mutation: str, expected: str) -> None:
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    rule = rules[verifier.RULE_UIDS[0]]
    if mutation == "rule":
        rule["condition"] = "wrong"
    elif mutation == "paused":
        rule["isPaused"] = True
    elif mutation == "datasource":
        datasource["status"] = "ERROR"
    elif mutation == "pusher":
        up_query["data"]["result"] = [
            item for item in up_query["data"]["result"] if item["metric"]["job"] != "pusher-metrics"
        ]
    elif mutation == "metrics":
        metric_query["data"]["result"] = []
    else:
        contact_points = []
    errors = verifier.validate_live_route(
        rules,
        datasource,
        up_query,
        metric_query,
        contact_points,
        phase="postrollout",
    )
    assert any(expected in error for error in errors)
    assert "must-never-be-logged" not in " ".join(errors)


@pytest.mark.parametrize(
    ("code", "reason", "expected"),
    [
        (401, "Unauthorized", "HTTP 401 Unauthorized"),
        (404, "Not Found", "HTTP 404 Not Found"),
        (503, "Service Unavailable", "HTTP 503 Service Unavailable"),
    ],
)
def test_request_failure_names_the_http_status(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, code: int, reason: str, expected: str
) -> None:
    """#12668: 401 and 404 have different owners — a revoked token vs an unprovisioned
    rule — so the failure line has to distinguish them. Collapsing both into `HTTPError`
    turned a one-line diagnosis into a multi-hour one across 13 consecutive red deploys."""

    def _raise(*_args, **_kwargs):
        raise urllib.error.HTTPError(url="https://monitor.example/api", code=code, msg=reason, hdrs=None, fp=None)

    monkeypatch.setattr(verifier.urllib.request, "urlopen", _raise)

    with pytest.raises(verifier.AlertRouteError) as excinfo:
        verifier._request_json("https://monitor.example", "/api/v1/provisioning/alert-rules/x", "token")

    assert expected in str(excinfo.value)


def test_request_failure_names_the_url_error_reason(verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """`URLError` sits between the other two handlers on purpose: it subclasses `OSError`
    and is the superclass of `HTTPError`. Catching `OSError` first would swallow both
    specific cases and report a bare type name, so the ordering needs its own pin."""

    def _raise(*_args, **_kwargs):
        raise urllib.error.URLError("nodename nor servname provided")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", _raise)

    with pytest.raises(verifier.AlertRouteError) as excinfo:
        verifier._request_json("https://monitor.example", "/api/v1/provisioning/alert-rules/x", "token")

    message = str(excinfo.value)
    assert "URLError" in message
    assert "nodename nor servname provided" in message


def test_request_failure_falls_back_to_the_type_name_for_a_plain_os_error(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A socket-level failure that is not a URLError keeps the original behaviour."""

    def _raise(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", _raise)

    with pytest.raises(verifier.AlertRouteError) as excinfo:
        verifier._request_json("https://monitor.example", "/api/v1/provisioning/alert-rules/x", "token")

    assert "TimeoutError" in str(excinfo.value)


def test_request_failure_does_not_leak_the_response_body(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Grafana error bodies can carry detail that must not reach a public CI log."""

    def _raise(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://monitor.example/api",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"must-never-be-logged"}'),
        )

    monkeypatch.setattr(verifier.urllib.request, "urlopen", _raise)

    with pytest.raises(verifier.AlertRouteError) as excinfo:
        verifier._request_json("https://monitor.example", "/api/v1/provisioning/alert-rules/x", "token")

    assert "must-never-be-logged" not in str(excinfo.value)


def test_rejects_world_readable_token_file(verifier: SimpleNamespace, tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("secret", encoding="utf-8")
    token.chmod(0o644)
    with pytest.raises(verifier.AlertRouteError, match="group or others"):
        verifier._token(token)


def test_prepublish_does_not_deadlock_on_a_not_yet_deployed_metric_family(verifier: SimpleNamespace) -> None:
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    metric_query["data"]["result"] = []
    assert (
        verifier.validate_live_route(
            rules,
            datasource,
            up_query,
            metric_query,
            contact_points,
            phase="prepublish",
        )
        == []
    )


def test_live_query_requires_every_scrape_target_in_each_job_to_be_up() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'min(up{job=~"pusher-metrics|backend-listen-metrics"}) by (job)' in source
    assert 'max(up{job=~"pusher-metrics|backend-listen-metrics"}) by (job)' not in source


def test_scrape_target_failure_names_each_jobs_observed_up_state(verifier: SimpleNamespace) -> None:
    """The 2026-09-16 -> 09-17 outage failed this gate for ~26 hours without
    saying which required job was down: dev Pusher crash-looped on a missing
    SONIOX_API_KEY binding, its pusher-metrics target went dark, and every log
    line read the same blame-free sentence. The failure must carry per-job
    observed state so the culprit is named on the first red run."""
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    up_query["data"]["result"] = [
        {"metric": {"job": "backend-listen-metrics"}, "value": [1, "1"]},
        {"metric": {"job": "pusher-metrics"}, "value": [1, "0"]},
    ]
    errors = verifier.validate_live_route(rules, datasource, up_query, metric_query, contact_points, phase="prepublish")
    message = next(error for error in errors if "scrape targets" in error)
    assert "backend-listen-metrics=1" in message
    assert "pusher-metrics=0" in message


def test_scrape_target_failure_marks_a_job_with_no_series_absent(verifier: SimpleNamespace) -> None:
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    up_query["data"]["result"] = [
        {"metric": {"job": "backend-listen-metrics"}, "value": [1, "1"]},
    ]
    errors = verifier.validate_live_route(rules, datasource, up_query, metric_query, contact_points, phase="prepublish")
    message = next(error for error in errors if "scrape targets" in error)
    assert "backend-listen-metrics=1" in message
    assert "pusher-metrics=absent" in message


def _token_file(tmp_path: Path) -> Path:
    token = tmp_path / "token"
    token.write_text("secret", encoding="utf-8")
    token.chmod(0o600)
    return token


def _live_rule(expected: dict[str, Any], **overrides: object) -> dict[str, Any]:
    rule = copy.deepcopy(expected)
    rule.update(overrides)
    return rule


def test_gate_file_contains_every_pusher_finalization_uid(verifier: SimpleNamespace) -> None:
    committed = verifier.load_all_committed_rules()
    gated = verifier.load_gated_uids(committed)
    assert set(verifier.RULE_UIDS) <= set(gated)
    assert set(gated) <= set(committed)


def test_committed_split_exports_are_the_fleet_inventory(verifier: SimpleNamespace) -> None:
    committed = verifier.load_all_committed_rules()
    combined_path = verifier.ROOT / "backend/charts/monitoring/alert-rules.json"
    combined = {rule["uid"] for rule in json.loads(combined_path.read_text(encoding="utf-8"))}
    assert set(committed) == combined
    assert len(committed) >= len(verifier.RULE_UIDS)


def test_grafana_assigned_metadata_does_not_count_as_definition_drift(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    live = _live_rule(expected, id=999, updated="2099-01-01T00:00:00Z", provenance="api")
    assert verifier.mismatched_definition_keys(live, expected) == []
    assert verifier.rule_definition_errors(expected["uid"], live, expected) == []


def test_classify_committed_but_absent(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    coverage = verifier.classify_fleet_coverage({expected["uid"]: expected}, {})
    assert coverage.committed_but_absent == (expected["uid"],)
    assert coverage.live_and_matching == ()
    assert coverage.live_count == 0


def test_classify_live_but_uncommitted(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    extra = _live_rule(expected, uid="grafana-only-rule")
    coverage = verifier.classify_fleet_coverage(
        {expected["uid"]: expected}, {expected["uid"]: expected, extra["uid"]: extra}
    )
    assert coverage.live_but_uncommitted == ("grafana-only-rule",)
    assert coverage.live_and_matching == (expected["uid"],)


def test_classify_present_but_paused(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    live = _live_rule(expected, isPaused=True)
    coverage = verifier.classify_fleet_coverage({expected["uid"]: expected}, {expected["uid"]: live})
    assert coverage.present_but_paused == (expected["uid"],)
    assert coverage.live_and_matching == ()


def test_classify_present_but_divergent(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    live = _live_rule(expected, title="wrong", condition="wrong")
    coverage = verifier.classify_fleet_coverage({expected["uid"]: expected}, {expected["uid"]: live})
    assert coverage.present_but_divergent == (f"{expected['uid']} (title,condition)",)
    assert coverage.live_and_matching == ()


def test_paused_and_divergent_rule_is_listed_in_both_buckets(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    live = _live_rule(expected, isPaused=True, title="wrong")
    coverage = verifier.classify_fleet_coverage({expected["uid"]: expected}, {expected["uid"]: live})
    assert coverage.present_but_paused == (expected["uid"],)
    assert coverage.present_but_divergent == (f"{expected['uid']} (title)",)


def test_fleet_fail_on_none_is_silent_when_ungated_rules_are_missing(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    coverage = verifier.classify_fleet_coverage(
        {expected["uid"]: expected, "ungated": expected},
        {},
    )
    assert verifier.fleet_gate_failures(coverage, verifier.RULE_UIDS, "none") == []


def test_fleet_fail_on_gated_ignores_ungated_absence(verifier: SimpleNamespace) -> None:
    gated_uid = verifier.RULE_UIDS[0]
    expected = verifier._committed_rules()[gated_uid]
    coverage = verifier.classify_fleet_coverage(
        {gated_uid: expected, "ungated-missing": expected},
        {gated_uid: expected},
    )
    assert verifier.fleet_gate_failures(coverage, (gated_uid,), "gated") == []
    assert coverage.committed_but_absent == ("ungated-missing",)


def test_fleet_fail_on_gated_fails_when_a_gated_uid_is_absent(verifier: SimpleNamespace) -> None:
    gated_uid = verifier.RULE_UIDS[0]
    expected = verifier._committed_rules()[gated_uid]
    coverage = verifier.classify_fleet_coverage({gated_uid: expected}, {})
    failures = verifier.fleet_gate_failures(coverage, (gated_uid,), "gated")
    assert failures == [f"live alert rule {gated_uid} is absent from Grafana"]


def test_fleet_fail_on_all_includes_live_but_uncommitted(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    extra = _live_rule(expected, uid="grafana-only-rule")
    coverage = verifier.classify_fleet_coverage(
        {expected["uid"]: expected}, {expected["uid"]: expected, extra["uid"]: extra}
    )
    failures = verifier.fleet_gate_failures(coverage, verifier.RULE_UIDS, "all")
    assert "live alert rule grafana-only-rule is not in the committed exports" in failures


def test_fleet_report_does_not_include_contact_point_settings(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    coverage = verifier.classify_fleet_coverage({expected["uid"]: expected}, {})
    lines = verifier.format_fleet_report(coverage, committed_count=1, gated_uids=verifier.RULE_UIDS)
    blob = " ".join(lines)
    assert "must-never-be-logged" not in blob
    assert "bottoken" not in blob
    assert "COMMITTED_BUT_ABSENT (1):" in blob
    assert "UNPROVEN:" in blob


def test_index_live_rules_rejects_a_non_list_payload(verifier: SimpleNamespace) -> None:
    with pytest.raises(verifier.AlertRouteError, match="non-list payload"):
        verifier.index_live_rules({"rules": []}, path="/api/v1/provisioning/alert-rules")


def test_index_live_rules_rejects_duplicate_uids(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    with pytest.raises(verifier.AlertRouteError, match="duplicate uid"):
        verifier.index_live_rules([expected, copy.deepcopy(expected)], path="/api/v1/provisioning/alert-rules")


def test_main_pusher_mode_requires_phase(
    verifier: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_pusher_live_alert_route.py",
            "--grafana-url",
            "https://monitor.omi.me",
            "--token-file",
            str(_token_file(tmp_path)),
        ],
    )
    assert verifier.main() == 1
    assert "pusher mode requires --phase" in capsys.readouterr().out


def test_main_fleet_report_exits_zero_when_only_ungated_rules_drift(
    verifier: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    committed = verifier.load_all_committed_rules()
    gated = verifier.load_gated_uids(committed)
    live = [copy.deepcopy(committed[uid]) for uid in gated]

    class _Response(io.BytesIO):
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def _urlopen(request: urllib.request.Request, timeout: int = 15) -> _Response:
        del timeout
        assert request.full_url.endswith("/api/v1/provisioning/alert-rules")
        assert "/api/v1/provisioning/contact-points" not in request.full_url
        return _Response(json.dumps(live).encode("utf-8"))

    monkeypatch.setattr(verifier.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_pusher_live_alert_route.py",
            "--grafana-url",
            "https://monitor.omi.me",
            "--token-file",
            str(_token_file(tmp_path)),
            "--mode",
            "fleet",
        ],
    )
    assert verifier.main() == 0
    output = capsys.readouterr().out
    assert "OK: fleet Grafana coverage report completed." in output
    assert "COMMITTED_BUT_ABSENT" in output
    assert "must-never-be-logged" not in output
    assert "FAIL:" not in output


def test_main_fleet_gated_fails_when_a_gated_uid_is_missing(
    verifier: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _Response(io.BytesIO):
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def _urlopen(request: urllib.request.Request, timeout: int = 15) -> _Response:
        del request, timeout
        return _Response(b"[]")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_pusher_live_alert_route.py",
            "--grafana-url",
            "https://monitor.omi.me",
            "--token-file",
            str(_token_file(tmp_path)),
            "--mode",
            "fleet",
            "--fail-on",
            "gated",
        ],
    )
    assert verifier.main() == 1
    output = capsys.readouterr().out
    assert f"FAIL: live alert rule {verifier.RULE_UIDS[0]} is absent from Grafana" in output
    assert "COMMITTED_BUT_ABSENT" in output
