"""Contracts for the live Grafana finalization-alert release gate."""

from __future__ import annotations

import copy
import io
import runpy
import urllib.error
from pathlib import Path
from types import SimpleNamespace

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
