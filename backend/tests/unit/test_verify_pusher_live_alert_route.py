"""Contracts for the live Grafana finalization-alert release gate."""

from __future__ import annotations

import copy
import io
import json
import runpy
import urllib.error
import urllib.parse
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


def test_serving_check_keeps_min_over_non_deleting_targets_and_does_not_use_max() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'up{job=~"pusher-metrics|backend-listen-metrics"}' in source
    assert "kube_pod_deletion_timestamp" in source
    assert "kube_pod_status_phase" not in source
    assert 'max(up{job=~"pusher-metrics|backend-listen-metrics"})' not in source


def _ksm_present() -> dict[str, Any]:
    return {"status": "success", "data": {"result": [{"metric": {}, "value": [1, "8"]}]}}


def _ksm_absent() -> dict[str, Any]:
    return {"status": "success", "data": {"result": []}}


def _series_query(series: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "success", "data": {"result": series}}


def _target(job: str, pod: str, value: str = "1", namespace: str = "prod-omi-backend", **labels: str) -> dict[str, Any]:
    metric = {"job": job, "namespace": namespace, "pod": pod}
    metric.update(labels)
    return {"metric": metric, "value": [1, value]}


def _deletion(pod: str, namespace: str = "prod-omi-backend", stamp: str = "1.792061362e+09") -> dict[str, Any]:
    return {"metric": {"namespace": namespace, "pod": pod, "uid": "uid-1"}, "value": [1, stamp]}


def _serving_errors(
    verifier: SimpleNamespace,
    up_series: list[dict[str, Any]],
    deletion_query: dict[str, Any],
    ksm_presence_query: dict[str, Any],
    *,
    phase: str = "postrollout",
) -> list[str]:
    rules, datasource, _up, metric_query, contact_points = _inputs(verifier)
    return verifier.validate_live_route(
        rules,
        datasource,
        _series_query(up_series),
        metric_query,
        contact_points,
        phase=phase,
        deletion_query=deletion_query,
        ksm_presence_query=ksm_presence_query,
    )


def test_healthy_replacement_targets_pass(verifier: SimpleNamespace) -> None:
    errors = _serving_errors(
        verifier,
        [
            _target("pusher-metrics", "pusher-a"),
            _target("pusher-metrics", "pusher-b"),
            _target("backend-listen-metrics", "listen-a"),
        ],
        _series_query([]),
        _ksm_present(),
    )
    assert errors == []


@pytest.mark.parametrize("job", ["pusher-metrics", "backend-listen-metrics"])
def test_deleting_down_pod_does_not_fail_healthy_replacements(verifier: SimpleNamespace, job: str) -> None:
    """Old-pod drain leaves phase Running and up=0 until grace + preStop finish.
    Pusher and backend-listen share the namespace/pod join, so either job's
    terminating target is ignored while its replacement stays in min(up)."""
    other = "backend-listen-metrics" if job == "pusher-metrics" else "pusher-metrics"
    up_series = [
        _target(job, f"{job}-new"),
        _target(job, f"{job}-old", "0", phase="Running"),
        _target(other, f"{other}-new"),
    ]
    deletion_query = _series_query([_deletion(f"{job}-old")])
    assessment = verifier.serving_up_by_job(_series_query(up_series), deletion_query, _ksm_present())
    assert assessment.excluded_targets == 1
    assert assessment.by_job[job] == "1"
    assert assessment.deletion_timestamps_confirmed is True
    assert _serving_errors(verifier, up_series, deletion_query, _ksm_present()) == []


def test_down_non_terminating_pod_fails_even_when_phase_is_running(verifier: SimpleNamespace) -> None:
    errors = _serving_errors(
        verifier,
        [
            _target("pusher-metrics", "pusher-new"),
            _target("pusher-metrics", "pusher-broken", "0", phase="Running"),
            _target("backend-listen-metrics", "listen-a"),
        ],
        _series_query([_deletion("pusher-broken", stamp="0")]),
        _ksm_present(),
    )
    message = next(error for error in errors if "scrape targets" in error)
    assert "pusher-metrics=0" in message
    assert "backend-listen-metrics=1" in message
    assert "not treated as terminating" not in message


def test_missing_scrape_job_still_fails_when_deletions_are_confirmed(verifier: SimpleNamespace) -> None:
    errors = _serving_errors(
        verifier,
        [_target("backend-listen-metrics", "listen-a")],
        _series_query([]),
        _ksm_present(),
    )
    message = next(error for error in errors if "scrape targets" in error)
    assert "pusher-metrics=absent" in message
    assert "backend-listen-metrics=1" in message


def test_kube_state_metrics_absent_does_not_excuse_a_down_target(verifier: SimpleNamespace) -> None:
    """Empty deletion results are not proof that a down pod is draining. Without
    kube_pod_info, the gate keeps that target in min(up) and fails."""
    errors = _serving_errors(
        verifier,
        [
            _target("pusher-metrics", "pusher-new"),
            _target("pusher-metrics", "pusher-old", "0", phase="Running"),
            _target("backend-listen-metrics", "listen-a"),
        ],
        _series_query([]),
        _ksm_absent(),
    )
    message = next(error for error in errors if "scrape targets" in error)
    assert "pusher-metrics=0" in message
    assert "not treated as terminating" in message


def test_kube_state_metrics_absent_still_passes_when_every_target_is_up(verifier: SimpleNamespace) -> None:
    errors = _serving_errors(
        verifier,
        [
            _target("pusher-metrics", "pusher-a"),
            _target("backend-listen-metrics", "listen-a"),
        ],
        {"status": "error"},
        _ksm_absent(),
    )
    assert errors == []


def test_job_with_only_terminating_targets_is_absent(verifier: SimpleNamespace) -> None:
    errors = _serving_errors(
        verifier,
        [
            _target("pusher-metrics", "pusher-old", "0"),
            _target("backend-listen-metrics", "listen-a"),
        ],
        _series_query([_deletion("pusher-old")]),
        _ksm_present(),
    )
    message = next(error for error in errors if "scrape targets" in error)
    assert "pusher-metrics=absent" in message


def test_deletion_timestamp_in_another_namespace_does_not_exclude_the_target(verifier: SimpleNamespace) -> None:
    errors = _serving_errors(
        verifier,
        [
            _target("pusher-metrics", "pusher-old", "0"),
            _target("backend-listen-metrics", "listen-a"),
        ],
        _series_query([_deletion("pusher-old", namespace="dev-omi-backend")]),
        _ksm_present(),
    )
    message = next(error for error in errors if "scrape targets" in error)
    assert "pusher-metrics=0" in message
    assert "not treated as terminating" not in message


def test_pusher_gate_queries_per_target_up_and_deletion_timestamps(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    queries: list[str] = []

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path.startswith("/api/datasources/proxy/uid/prometheus/api/v1/query?"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["query"][0]
            queries.append(query)
            if query == verifier.POD_DELETION_TIMESTAMP_QUERY:
                raise verifier.AlertRouteError("deletion timestamps unavailable")
            if query == verifier.KSM_POD_INFO_COUNT_QUERY:
                return _ksm_absent()
            if query == verifier.SERVING_UP_QUERY:
                return up_query
            return metric_query
        if path.startswith("/api/v1/provisioning/alert-rules/"):
            return rules[path.rsplit("/", 1)[-1]]
        if path == "/api/datasources/uid/prometheus/health":
            return datasource
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        raise AssertionError(path)

    monkeypatch.setitem(verifier._run_pusher_gate.__globals__, "_request_json", fake_request)
    assert verifier._run_pusher_gate("https://monitor.omi.me", "secret", "postrollout", 1) == []
    assert verifier.SERVING_UP_QUERY in queries
    assert verifier.POD_DELETION_TIMESTAMP_QUERY in queries
    assert verifier.KSM_POD_INFO_COUNT_QUERY in queries
    assert 'max(up{job=~"pusher-metrics|backend-listen-metrics"})' not in " ".join(queries)


def test_deletion_query_error_still_fails_a_down_target(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    up_query["data"]["result"] = [
        _target("pusher-metrics", "pusher-new"),
        _target("pusher-metrics", "pusher-old", "0"),
        _target("backend-listen-metrics", "listen-a"),
    ]

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path.startswith("/api/datasources/proxy/uid/prometheus/api/v1/query?"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["query"][0]
            if query in (verifier.POD_DELETION_TIMESTAMP_QUERY, verifier.KSM_POD_INFO_COUNT_QUERY):
                raise verifier.AlertRouteError("kube-state-metrics unavailable")
            if query == verifier.SERVING_UP_QUERY:
                return up_query
            return metric_query
        if path.startswith("/api/v1/provisioning/alert-rules/"):
            return rules[path.rsplit("/", 1)[-1]]
        if path == "/api/datasources/uid/prometheus/health":
            return datasource
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        raise AssertionError(path)

    monkeypatch.setitem(verifier._run_pusher_gate.__globals__, "_request_json", fake_request)
    failures = verifier._run_pusher_gate("https://monitor.omi.me", "secret", "postrollout", 1)
    assert any("pusher-metrics=0" in failure and "not treated as terminating" in failure for failure in failures)


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
    errors = verifier.validate_live_route(
        rules,
        datasource,
        up_query,
        metric_query,
        contact_points,
        phase="prepublish",
        deletion_query=_series_query([]),
        ksm_presence_query=_ksm_present(),
    )
    message = next(error for error in errors if "scrape targets" in error)
    assert "backend-listen-metrics=1" in message
    assert "pusher-metrics=0" in message
    assert "not treated as terminating" not in message


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


def test_live_stt_import_allowlist_matches_committed_rules(verifier: SimpleNamespace) -> None:
    rules = verifier.load_live_stt_import_rules()
    gated = verifier.load_gated_uids(verifier.load_all_committed_rules())
    assert set(rules) == set(gated) | set(verifier.DATASOURCE_CANARY_UIDS)
    assert set(verifier.RULE_UIDS) <= set(rules)
    assert "omi-datasource-gmp" not in rules
    non_live_stt = set(gated) - set(verifier.LIVE_STT_IMPORT_UIDS)
    assert (set(rules) - set(verifier.DATASOURCE_CANARY_UIDS) - non_live_stt) == {
        rule["uid"] for rule in json.loads((verifier.ALERT_SOURCES / "live-stt.json").read_text())
    }
    assert set(verifier.LIVE_STT_IMPORT_UIDS) | set(verifier.REDIS_CACHE_IMPORT_UIDS) | set(verifier.RULE_UIDS) <= set(
        gated
    )


def test_live_stt_import_upserts_only_allowlisted_rules_and_checks_telegram_route(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = verifier.load_live_stt_import_rules()
    existing_uid = verifier.LIVE_STT_IMPORT_UIDS[0]
    calls: list[tuple[str, bool]] = []
    contact_points = [
        {
            "name": verifier.TELEGRAM_RECEIVER,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path == verifier.ALERT_RULE_LIST_PATH:
            return [{"uid": existing_uid}]
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        if path.startswith(verifier.MUTE_TIMING_PATH + "/"):
            return {
                "name": path.rsplit("/", 1)[-1],
                "time_intervals": [{"times": [{"begin_time": "00:00", "end_time": "24:00"}]}],
            }
        uid = path.rsplit("/", 1)[-1]
        if uid in verifier.DATASOURCE_CANARY_UIDS:
            assert [key for key, _ in calls] == list(verifier.DATASOURCE_CANARY_UIDS)
            return rules[uid]
        raise AssertionError(f"unexpected Grafana read path: {path}")

    def fake_write(_url: str, uid: str, _rule: dict[str, Any], _token: str, *, exists: bool) -> None:
        calls.append((uid, exists))

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_request_json", fake_request)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_write_rule", fake_write)
    assert verifier._run_live_stt_import("https://monitor.omi.me", "secret") == []
    assert {uid for uid, _exists in calls} == set(rules)
    assert (existing_uid, True) in calls
    assert all(exists for uid, exists in calls if uid == existing_uid)


def test_import_rejects_missing_verified_telegram_receiver(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = verifier.load_live_stt_import_rules()
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "_request_json",
        lambda _url, path, _token, **_kwargs: (
            [{"uid": uid} for uid in rules] if path == verifier.ALERT_RULE_LIST_PATH else []
        ),
    )
    failures = verifier._run_live_stt_import("https://monitor.omi.me", "secret")
    assert failures == ["verified Telegram alert receiver is missing or resolve notifications are disabled"]


def test_committed_mute_timings_cover_every_referenced_interval(verifier: SimpleNamespace) -> None:
    committed = verifier.load_committed_mute_timings()
    for production in (True, False):
        referenced = verifier._referenced_mute_timings(verifier.load_live_stt_import_rules(production=production))
        assert referenced, "the import set is expected to reference at least omi-tier-silent"
        assert set(referenced) <= set(committed)


def test_import_creates_a_missing_referenced_mute_timing_before_writing_any_rule(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = verifier.load_live_stt_import_rules(production=False)
    name = verifier._referenced_mute_timings(rules)[0]
    contact_points = [
        {
            "name": verifier.TELEGRAM_RECEIVER,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]
    events: list[tuple[str, str]] = []

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        if path == f"{verifier.MUTE_TIMING_PATH}/{name}":
            # Still absent on the read-back after creation.
            return None
        raise AssertionError(f"unexpected Grafana read path: {path}")

    def fake_create(_url: str, timing: dict[str, Any], _token: str) -> None:
        events.append(("create", timing["name"]))

    def fake_write(_url: str, uid: str, _rule: dict[str, Any], _token: str, *, exists: bool) -> None:
        events.append(("rule", uid))

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_request_json", fake_request)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_create_mute_timing", fake_create)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_write_rule", fake_write)
    with pytest.raises(verifier.AlertRouteError, match="did not become readable after creation"):
        verifier._run_live_stt_import("https://monitor.omiapi.com", "secret")
    # Creation was attempted from the committed definition and no rule was written.
    assert events == [("create", name)]


def test_import_creates_a_missing_mute_timing_and_proceeds(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = verifier.load_live_stt_import_rules(production=False)
    name = verifier._referenced_mute_timings(rules)[0]
    committed = verifier.load_committed_mute_timings()[name]
    contact_points = [
        {
            "name": verifier.TELEGRAM_RECEIVER,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]
    created: list[dict[str, Any]] = []
    events: list[tuple[str, str]] = []

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        if path == f"{verifier.MUTE_TIMING_PATH}/{name}":
            return committed if created else None
        raise AssertionError(f"unexpected Grafana read path: {path}")

    def fake_create(_url: str, timing: dict[str, Any], _token: str) -> None:
        created.append(timing)

    def fake_write(_url: str, uid: str, _rule: dict[str, Any], _token: str, *, exists: bool) -> None:
        events.append(("rule", uid))

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_request_json", fake_request)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_create_mute_timing", fake_create)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_write_rule", fake_write)
    assert verifier._run_live_stt_import("https://monitor.omiapi.com", "secret") == []
    assert created == [committed]
    assert {uid for kind, uid in events if kind == "rule"} == set(rules)
    assert f"CREATED mute timing {name}" in capsys.readouterr().out


def test_import_never_overwrites_an_existing_mute_timing(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = verifier.load_live_stt_import_rules()
    contact_points = [
        {
            "name": verifier.TELEGRAM_RECEIVER,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        if path.startswith(verifier.MUTE_TIMING_PATH + "/"):
            return {
                "name": path.rsplit("/", 1)[-1],
                "time_intervals": [{"times": [{"begin_time": "00:00", "end_time": "24:00"}]}],
            }
        if path.startswith(verifier.ALERT_RULE_LIST_PATH + "/"):
            return rules[path.rsplit("/", 1)[-1]]
        raise AssertionError(f"unexpected Grafana read path: {path}")

    def fail_create(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an existing mute timing must never be rewritten")

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_request_json", fake_request)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_create_mute_timing", fail_create)
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "_write_rule",
        lambda _url, uid, _rule, _token, *, exists: None,
    )
    assert verifier._run_live_stt_import("https://monitor.omi.me", "secret") == []


@pytest.mark.parametrize(
    "narrowing",
    [
        pytest.param(
            {
                "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "times": [{"begin_time": "09:00", "end_time": "17:00"}],
            },
            id="business-hours",
        ),
        pytest.param({"months": ["january"]}, id="january-only"),
        pytest.param({"years": ["2026"]}, id="single-year"),
        pytest.param({"days_of_month": ["1", "2"]}, id="two-days-a-month"),
    ],
)
def test_import_fails_closed_when_a_live_mute_timing_drifts_from_the_committed_window(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, narrowing: dict[str, Any]
) -> None:
    """A narrower live mute window would let agent-tier rules page Telegram
    outside the committed silence; the import names the drift instead of
    trusting the existing timing blindly (review rounds 1 and 2 on #23612:
    business hours, then the calendar selectors the signature must not
    ignore)."""

    rules = verifier.load_live_stt_import_rules()
    name = verifier._referenced_mute_timings(rules)[0]
    contact_points = [
        {
            "name": verifier.TELEGRAM_RECEIVER,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]
    narrowed_timing = {"name": name, "time_intervals": [dict(narrowing, location="UTC")]}

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        if path == f"{verifier.MUTE_TIMING_PATH}/{name}":
            return narrowed_timing
        raise AssertionError(f"unexpected Grafana read path: {path}")

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, "_request_json", fake_request)
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "_create_mute_timing",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("a drifted timing must not be recreated")),
    )
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "_write_rule",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("no rule may be written under a drifted timing")
        ),
    )
    with pytest.raises(verifier.AlertRouteError, match="differs from the committed definition"):
        verifier._run_live_stt_import("https://monitor.omi.me", "secret")


def test_import_fails_closed_when_a_referenced_mute_timing_is_uncommitted(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = verifier.load_live_stt_import_rules()
    name = verifier._referenced_mute_timings(rules)[0]
    contact_points = [
        {
            "name": verifier.TELEGRAM_RECEIVER,
            "type": "telegram",
            "disableResolveMessage": False,
            "settings": {"bottoken": "must-never-be-logged"},
        }
    ]

    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "_request_json",
        lambda _url, path, _token, **_kwargs: ([] if path == verifier.ALERT_RULE_LIST_PATH else contact_points),
    )
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "load_committed_mute_timings",
        lambda: {key: value for key, value in verifier.load_committed_mute_timings().items() if key != name},
    )
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        "_write_rule",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no rule may be written")),
    )
    with pytest.raises(verifier.AlertRouteError, match="no committed definition"):
        verifier._run_live_stt_import("https://monitor.omi.me", "secret")


def test_live_stt_fleet_scope_reports_only_the_import_allowlist(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = verifier.load_live_stt_import_rules()
    monkeypatch.setitem(
        verifier._run_fleet_coverage.__globals__,
        "_request_json",
        lambda *_args, **_kwargs: list(committed.values()),
    )
    failures, report = verifier._run_fleet_coverage(
        "https://monitor.omi.me", "secret", 1, "gated", alert_set="live-stt"
    )
    assert failures == []
    count = len(committed)
    assert set(verifier.RULE_UIDS) <= set(committed)
    assert report[0] == (f"FLEET committed={count} live={count} gated={count} matching={count} gated_matching={count}")
    assert "COMMITTED_BUT_ABSENT (0): -" in report
    assert "LIVE_BUT_UNCOMMITTED (0): -" in report


@pytest.mark.parametrize(("exists", "method"), [(False, "POST"), (True, "PUT")])
def test_import_request_uses_post_for_missing_and_put_for_existing_uid(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, exists: bool, method: str
) -> None:
    captured: list[urllib.request.Request] = []

    class _Response(io.BytesIO):
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        verifier.urllib.request, "urlopen", lambda request, timeout=15: (captured.append(request), _Response())[1]
    )
    uid = verifier.LIVE_STT_IMPORT_UIDS[0]
    verifier._write_rule("https://monitor.omi.me", uid, {"uid": uid}, "secret", exists=exists)
    assert len(captured) == 1
    assert captured[0].get_method() == method
    assert captured[0].full_url.endswith(verifier.ALERT_RULE_LIST_PATH + (f"/{uid}" if exists else ""))


def test_committed_split_exports_are_the_fleet_inventory(verifier: SimpleNamespace) -> None:
    committed = verifier.load_all_committed_rules()
    combined_path = verifier.ROOT / "backend/charts/monitoring/alert-rules.json"
    combined = {rule["uid"] for rule in json.loads(combined_path.read_text(encoding="utf-8"))}
    assert set(committed) == combined
    assert len(committed) >= len(verifier.RULE_UIDS)


def _with_grafana_assigned_query_defaults(rule: dict[str, Any]) -> dict[str, Any]:
    live = copy.deepcopy(rule)
    for node in live["data"]:
        if not isinstance(node, dict):
            continue
        node.setdefault("queryType", "")
        model = node.get("model")
        if isinstance(model, dict):
            model.setdefault("intervalMs", 1000)
            model.setdefault("maxDataPoints", 43200)
    return live


def test_grafana_assigned_metadata_does_not_count_as_definition_drift(verifier: SimpleNamespace) -> None:
    expected = next(iter(verifier._committed_rules().values()))
    live = _live_rule(expected, id=999, updated="2099-01-01T00:00:00Z", provenance="api")
    assert verifier.mismatched_definition_keys(live, expected) == []
    assert verifier.rule_definition_errors(expected["uid"], live, expected) == []

    canary = verifier.load_all_committed_rules()[verifier.DATASOURCE_CANARY_UIDS[0]]
    live_canary = _live_rule(_with_grafana_assigned_query_defaults(canary), id=7, provenance="api")
    assert verifier.mismatched_definition_keys(live_canary, canary) == []
    assert verifier.rule_definition_errors(canary["uid"], live_canary, canary) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("queryType", "range"),
        ("intervalMs", 2000),
        ("maxDataPoints", 100),
    ],
)
def test_grafana_assigned_query_defaults_reject_a_different_value(
    verifier: SimpleNamespace, field: str, value: object
) -> None:
    canary = copy.deepcopy(verifier.load_all_committed_rules()[verifier.DATASOURCE_CANARY_UIDS[1]])
    live = _with_grafana_assigned_query_defaults(canary)
    expression = next(node for node in live["data"] if node.get("datasourceUid") == "__expr__")
    if field == "queryType":
        expression["queryType"] = value
    else:
        expression["model"][field] = value
    assert verifier.mismatched_definition_keys(live, canary) == ["data"]

    committed = copy.deepcopy(canary)
    committed_expression = next(node for node in committed["data"] if node.get("datasourceUid") == "__expr__")
    if field == "queryType":
        committed_expression["queryType"] = "instant"
        expression["queryType"] = ""
    else:
        committed_expression["model"][field] = 5000 if field == "intervalMs" else 20
        expression["model"][field] = 1000 if field == "intervalMs" else 43200
    assert verifier.mismatched_definition_keys(live, committed) == ["data"]


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


@pytest.fixture(scope="module")
def redis_import_inputs(verifier: SimpleNamespace) -> tuple[dict[str, dict], str]:
    # Importing the fallback module graph and parsing every committed export is
    # setup, not the behavior under test; keep it out of the CPU-guarded call.
    from utils.observability.fallback import bucket_component

    return verifier.load_live_stt_import_rules(), bucket_component("redis_cache")


def test_redis_import_rules_match_emitted_cache_write_labels(
    verifier: SimpleNamespace, redis_import_inputs: tuple[dict[str, dict], str]
) -> None:
    rules, redis_bucket = redis_import_inputs
    for uid in verifier.REDIS_CACHE_IMPORT_UIDS:
        expressions = [item.get("model", {}).get("expr", "") for item in rules[uid]["data"]]
        expression = next(expr for expr in expressions if "omi_fallback_total" in expr)
        assert f'component="{redis_bucket}"' in expression
        assert 'from_mode="cache_write"' in expression
        assert 'outcome="degraded"' in expression
        assert 'auth_error|connection_error|timeout' in expression


@pytest.mark.parametrize("uid", ["omi-redis-cache-conn-warn", "omi-redis-cache-conn-page"])
def test_missing_redis_rule_fails_live_import_scope(verifier: SimpleNamespace, monkeypatch, uid) -> None:
    rules = verifier.load_live_stt_import_rules()
    monkeypatch.setitem(
        verifier._run_fleet_coverage.__globals__,
        "_request_json",
        lambda *_args, **_kwargs: [rule for key, rule in rules.items() if key != uid],
    )
    failures, _ = verifier._run_fleet_coverage("https://monitor.omi.me", "secret", 1, "gated", alert_set="live-stt")
    assert any(uid in failure for failure in failures)


@pytest.mark.parametrize('uid', ['omi-datasource-prometheus', 'omi-datasource-cloud-monitoring'])
@pytest.mark.parametrize('field,value', [('isPaused', True), ('execErrState', 'KeepLast'), ('noDataState', 'OK')])
def test_import_requires_active_fail_closed_canary_source(verifier, monkeypatch, uid, field, value):
    committed = copy.deepcopy(verifier.load_all_committed_rules())
    committed[uid][field] = value
    monkeypatch.setitem(verifier.load_live_stt_import_rules.__globals__, 'load_all_committed_rules', lambda: committed)
    with pytest.raises(verifier.AlertRouteError, match='must be active and page'):
        verifier.load_live_stt_import_rules()


@pytest.mark.parametrize('mutation', ['paused', 'error', 'nodata', 'identity', 'receiver', 'nonobject'])
def test_canary_readback_failure_prevents_business_keep_last_writes(verifier, monkeypatch, mutation):
    rules = verifier.load_live_stt_import_rules()
    broken = copy.deepcopy(rules[verifier.DATASOURCE_CANARY_UIDS[0]])
    if mutation == 'paused':
        broken['isPaused'] = True
    elif mutation == 'error':
        broken['execErrState'] = 'KeepLast'
    elif mutation == 'nodata':
        broken['noDataState'] = 'OK'
    elif mutation == 'identity':
        broken['labels']['alert_identity'] = 'wrong'
    elif mutation == 'receiver':
        broken['notification_settings']['receiver'] = 'wrong'
    else:
        broken = []
    writes = []

    def read(_base, path, _token, **kwargs):
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path.endswith('/contact-points'):
            return [{'name': verifier.TELEGRAM_RECEIVER, 'type': 'telegram'}]
        if path.startswith(verifier.MUTE_TIMING_PATH + '/'):
            return {
                'name': path.rsplit('/', 1)[-1],
                'time_intervals': [{'times': [{'begin_time': '00:00', 'end_time': '24:00'}]}],
            }
        uid = path.rsplit('/', 1)[-1]
        return broken if uid == verifier.DATASOURCE_CANARY_UIDS[0] else rules[uid]

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, '_request_json', read)
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        '_write_rule',
        lambda _base, uid, *_args, **kwargs: writes.append(uid),
    )
    assert verifier._run_live_stt_import('https://monitor.omi.me', 'dummy-secret')
    assert writes == list(verifier.DATASOURCE_CANARY_UIDS)


def test_prod_import_reads_canaries_back_before_finalization_rules(verifier, monkeypatch):
    rules = verifier.load_live_stt_import_rules()
    events: list[tuple[str, str]] = []
    written: dict[str, dict] = {}

    def read(_base, path, _token, **kwargs):
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path.endswith('/contact-points'):
            return [{'name': verifier.TELEGRAM_RECEIVER, 'type': 'telegram'}]
        if path.startswith(verifier.MUTE_TIMING_PATH + '/'):
            return {
                'name': path.rsplit('/', 1)[-1],
                'time_intervals': [{'times': [{'begin_time': '00:00', 'end_time': '24:00'}]}],
            }
        uid = path.rsplit('/', 1)[-1]
        events.append(('read', uid))
        return _with_grafana_assigned_query_defaults(rules[uid])

    def write(_base, uid, rule, *_args, **kwargs):
        events.append(('write', uid))
        written[uid] = rule

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, '_request_json', read)
    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, '_write_rule', write)
    assert verifier._run_live_stt_import('https://monitor.omi.me', 'dummy-secret') == []
    canaries = list(verifier.DATASOURCE_CANARY_UIDS)
    assert events[: len(canaries)] == [('write', uid) for uid in canaries]
    assert events[len(canaries) : len(canaries) * 2] == [('read', uid) for uid in canaries]
    later = events[len(canaries) * 2 :]
    assert all(kind == 'write' for kind, _uid in later)
    later_uids = [uid for _kind, uid in later]
    assert set(verifier.RULE_UIDS) <= set(later_uids)
    assert all(written[uid]['execErrState'] == 'KeepLast' for uid in verifier.RULE_UIDS)
    assert events.index(('write', verifier.RULE_UIDS[0])) > events.index(('read', canaries[-1]))


def test_nondefault_canary_query_readback_stops_before_finalization_rules(verifier, monkeypatch):
    rules = verifier.load_live_stt_import_rules()
    writes: list[str] = []

    def read(_base, path, _token, **kwargs):
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path.endswith('/contact-points'):
            return [{'name': verifier.TELEGRAM_RECEIVER, 'type': 'telegram'}]
        if path.startswith(verifier.MUTE_TIMING_PATH + '/'):
            return {
                'name': path.rsplit('/', 1)[-1],
                'time_intervals': [{'times': [{'begin_time': '00:00', 'end_time': '24:00'}]}],
            }
        uid = path.rsplit('/', 1)[-1]
        live = _with_grafana_assigned_query_defaults(rules[uid])
        if uid == verifier.DATASOURCE_CANARY_UIDS[0]:
            expression = next(node for node in live['data'] if node.get('datasourceUid') == '__expr__')
            expression['model']['intervalMs'] = 2000
        return live

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, '_request_json', read)
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        '_write_rule',
        lambda _base, uid, *_args, **kwargs: writes.append(uid),
    )
    failures = verifier._run_live_stt_import('https://monitor.omi.me', 'dummy-secret')
    assert writes == list(verifier.DATASOURCE_CANARY_UIDS)
    assert failures
    assert all('data does not match' in failure for failure in failures)
    assert not any(uid in failure for failure in failures for uid in verifier.RULE_UIDS)


@pytest.mark.parametrize('uid', ['omi-datasource-prometheus', 'omi-datasource-cloud-monitoring'])
@pytest.mark.parametrize('mutation', ['absent', 'paused', 'error', 'nodata', 'identity', 'receiver'])
def test_live_stt_postimport_gate_includes_canaries(verifier, monkeypatch, uid, mutation):
    live = copy.deepcopy(verifier.load_live_stt_import_rules())
    if mutation == 'absent':
        live.pop(uid)
    elif mutation == 'paused':
        live[uid]['isPaused'] = True
    elif mutation == 'error':
        live[uid]['execErrState'] = 'KeepLast'
    elif mutation == 'nodata':
        live[uid]['noDataState'] = 'OK'
    elif mutation == 'identity':
        live[uid]['labels']['alert_identity'] = 'wrong'
    else:
        live[uid]['notification_settings']['receiver'] = 'wrong'
    monkeypatch.setitem(
        verifier._run_fleet_coverage.__globals__, '_request_json', lambda *_args, **kwargs: list(live.values())
    )
    failures, _ = verifier._run_fleet_coverage(
        'https://monitor.omi.me', 'dummy-secret', 1, 'gated', alert_set='live-stt'
    )
    assert any(uid in failure for failure in failures)


def test_development_loader_restores_errors_without_mutating_sources(verifier, monkeypatch):
    canonical = verifier.load_all_committed_rules()
    snapshot = copy.deepcopy(canonical)
    monkeypatch.setitem(verifier.load_live_stt_import_rules.__globals__, 'load_all_committed_rules', lambda: canonical)
    development = verifier.load_live_stt_import_rules(production=False)
    gated = verifier.load_gated_uids(canonical)
    assert set(development) == set(gated)
    assert set(verifier.RULE_UIDS) <= set(development)
    assert set(verifier.DATASOURCE_CANARY_UIDS).isdisjoint(development)
    assert all(rule['execErrState'] != 'KeepLast' for rule in development.values())
    assert all(development[uid]['execErrState'] == 'Error' for uid in verifier.RULE_UIDS)
    assert canonical == snapshot
    # Redis rules come directly from the shared canonical loader, so verify the
    # development copy is detached even for nested structures.
    uid = verifier.REDIS_CACHE_IMPORT_UIDS[0]
    development[uid]['labels']['alert_identity'] = 'changed'
    assert canonical == snapshot
    production = verifier.load_live_stt_import_rules()
    assert set(verifier.DATASOURCE_CANARY_UIDS) <= set(production)
    assert any(rule['execErrState'] == 'KeepLast' for rule in production.values())


@pytest.mark.parametrize('target', ['https://monitor.omiapi.com', 'https://custom.invalid'])
def test_nonproduction_import_never_installs_or_reads_production_canaries(verifier, monkeypatch, target):
    writes = {}
    paths = []

    def read(_base, path, _token, **kwargs):
        paths.append(path)
        if path == verifier.ALERT_RULE_LIST_PATH:
            return []
        if path.endswith('/contact-points'):
            return [{'name': verifier.TELEGRAM_RECEIVER, 'type': 'telegram'}]
        if path.startswith(verifier.MUTE_TIMING_PATH + '/'):
            return {
                'name': path.rsplit('/', 1)[-1],
                'time_intervals': [{'times': [{'begin_time': '00:00', 'end_time': '24:00'}]}],
            }
        raise AssertionError('nonproduction must not read production canaries')

    monkeypatch.setitem(verifier._run_live_stt_import.__globals__, '_request_json', read)
    monkeypatch.setitem(
        verifier._run_live_stt_import.__globals__,
        '_write_rule',
        lambda _base, uid, rule, *_args, **kwargs: writes.update({uid: rule}),
    )
    assert verifier._run_live_stt_import(target, 'dummy-token') == []
    gated = set(verifier.load_gated_uids(verifier.load_all_committed_rules()))
    assert set(writes) == gated
    assert set(verifier.RULE_UIDS) <= set(writes)
    assert all(rule['execErrState'] != 'KeepLast' for rule in writes.values())
    assert all(writes[uid]['execErrState'] == 'Error' for uid in verifier.RULE_UIDS)
    assert all(not any(uid in path for uid in verifier.DATASOURCE_CANARY_UIDS) for path in paths)


def test_development_fleet_does_not_require_production_canaries(verifier, monkeypatch):
    development = verifier.load_live_stt_import_rules(production=False)
    monkeypatch.setitem(
        verifier._run_fleet_coverage.__globals__, '_request_json', lambda *_args, **kwargs: list(development.values())
    )
    failures, report = verifier._run_fleet_coverage(
        'https://monitor.omiapi.com', 'dummy-token', 1, 'gated', alert_set='live-stt'
    )
    assert failures == []
    count = len(development)
    assert set(verifier.RULE_UIDS) <= set(development)
    assert report[0] == f'FLEET committed={count} live={count} gated={count} matching={count} gated_matching={count}'


def test_development_fleet_rejects_unprotected_keep_last(verifier, monkeypatch):
    development = verifier.load_live_stt_import_rules(production=False)
    uid = verifier.LIVE_STT_IMPORT_UIDS[0]
    development[uid]['execErrState'] = 'KeepLast'
    monkeypatch.setitem(
        verifier._run_fleet_coverage.__globals__, '_request_json', lambda *_args, **kwargs: list(development.values())
    )
    failures, _ = verifier._run_fleet_coverage(
        'https://monitor.omiapi.com', 'dummy-token', 1, 'gated', alert_set='live-stt'
    )
    assert any(uid in failure and 'execErrState' in failure for failure in failures)


def test_development_finalization_gate_expects_the_imported_error_state(verifier):
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    assert any(rule['execErrState'] == 'KeepLast' for rule in rules.values())
    development_live = verifier._development_rules(rules)
    assert verifier._committed_rules() == rules
    assert (
        verifier.validate_live_route(
            development_live, datasource, up_query, metric_query, contact_points, phase='postrollout', production=False
        )
        == []
    )
    # Production still requires the committed KeepLast definitions exactly.
    errors = verifier.validate_live_route(
        development_live, datasource, up_query, metric_query, contact_points, phase='postrollout'
    )
    assert any('execErrState does not match' in error for error in errors)


def test_development_finalization_gate_still_rejects_other_drift(verifier):
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    development_live = verifier._development_rules(rules)
    uid = next(iter(development_live))
    development_live[uid]['execErrState'] = 'OK'
    development_live[next(reversed(development_live))]['noDataState'] = 'OK'
    errors = verifier.validate_live_route(
        development_live, datasource, up_query, metric_query, contact_points, phase='postrollout', production=False
    )
    assert any(uid in error and 'execErrState' in error for error in errors)
    assert any('noDataState' in error for error in errors)


def test_pusher_gate_selects_development_expectations_by_grafana_host(verifier, monkeypatch):
    rules, datasource, up_query, metric_query, contact_points = _inputs(verifier)
    development_live = verifier._development_rules(rules)

    def read(_base, path, _token, **kwargs):
        if '/provisioning/alert-rules/' in path:
            return development_live[path.rsplit('/', 1)[-1]]
        if path.endswith('/health'):
            return datasource
        if 'min%28up' in path or 'min(up' in path:
            return up_query
        if '/api/v1/query' in path:
            return metric_query
        return contact_points

    monkeypatch.setitem(verifier._run_pusher_gate.__globals__, '_request_json', read)
    assert verifier._run_pusher_gate('https://monitor.omiapi.com', 'dummy-secret', 'postrollout', 1) == []
    production_failures = verifier._run_pusher_gate('https://monitor.omi.me', 'dummy-secret', 'postrollout', 1)
    assert production_failures
    assert all('execErrState does not match' in failure for failure in production_failures)


def _gate_requests(verifier: SimpleNamespace, up_responses: dict[str, list[object]], queries: list[str]):
    rules, datasource, _up, metric_query, contact_points = _inputs(verifier)

    def fake_request(_url: str, path: str, _token: str, **_kwargs: object) -> object:
        if path.startswith("/api/datasources/proxy/uid/prometheus/api/v1/query?"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["query"][0]
            queries.append(query)
            if query == verifier.POD_DELETION_TIMESTAMP_QUERY:
                return _series_query([])
            if query == verifier.KSM_POD_INFO_COUNT_QUERY:
                return _ksm_present()
            if query in up_responses:
                response = up_responses[query].pop(0)
                if isinstance(response, Exception):
                    raise response
                return response
            return metric_query
        if path.startswith("/api/v1/provisioning/alert-rules/"):
            return rules[path.rsplit("/", 1)[-1]]
        if path == "/api/datasources/uid/prometheus/health":
            return datasource
        if path == "/api/v1/provisioning/contact-points":
            return contact_points
        raise AssertionError(path)

    return fake_request


def test_prepublish_reads_windowed_up_and_postrollout_keeps_instant_up(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    healthy = _series_query([_target("pusher-metrics", "p"), _target("backend-listen-metrics", "l")])
    assert verifier.PREPUBLISH_UP_QUERY == ('max_over_time(up{job=~"pusher-metrics|backend-listen-metrics"}[2m])')
    for phase, expected in (("prepublish", verifier.PREPUBLISH_UP_QUERY), ("postrollout", verifier.SERVING_UP_QUERY)):
        queries: list[str] = []
        fake = _gate_requests(verifier, {expected: [healthy]}, queries)
        monkeypatch.setitem(verifier._run_pusher_gate.__globals__, "_request_json", fake)
        assert verifier._run_pusher_gate("https://monitor.omi.me", "secret", phase, 1) == []
        up_queries = {q for q in queries if q in (verifier.PREPUBLISH_UP_QUERY, verifier.SERVING_UP_QUERY)}
        assert up_queries == {expected}


def test_prepublish_retries_a_brief_miss_and_a_transient_query_error(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    missed = _series_query([_target("pusher-metrics", "p"), _target("backend-listen-metrics", "l", "0")])
    healthy = _series_query([_target("pusher-metrics", "p"), _target("backend-listen-metrics", "l")])
    responses = {verifier.PREPUBLISH_UP_QUERY: [verifier.AlertRouteError("HTTP 502"), missed, healthy]}
    fake = _gate_requests(verifier, responses, [])
    monkeypatch.setitem(verifier._run_pusher_gate.__globals__, "_request_json", fake)
    monkeypatch.setattr(verifier._run_pusher_gate.__globals__["time"], "sleep", lambda _s: None)
    assert verifier._run_pusher_gate("https://monitor.omi.me", "secret", "prepublish", 3) == []


def test_prepublish_still_fails_a_target_down_for_the_whole_window(
    verifier: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    down = _series_query([_target("pusher-metrics", "p"), _target("backend-listen-metrics", "l", "0")])
    fake = _gate_requests(verifier, {verifier.PREPUBLISH_UP_QUERY: [down, down]}, [])
    monkeypatch.setitem(verifier._run_pusher_gate.__globals__, "_request_json", fake)
    monkeypatch.setattr(verifier._run_pusher_gate.__globals__["time"], "sleep", lambda _s: None)
    failures = verifier._run_pusher_gate("https://monitor.omi.me", "secret", "prepublish", 2)
    assert any("backend-listen-metrics=0" in failure for failure in failures)


def test_attempts_default_to_six_only_for_prepublish(verifier: SimpleNamespace) -> None:
    assert verifier.resolve_attempts(None, mode="pusher", phase="prepublish") == 6
    assert verifier.resolve_attempts(None, mode="pusher", phase="postrollout") == 1
    assert verifier.resolve_attempts(None, mode="fleet", phase=None) == 1
    assert verifier.resolve_attempts(12, mode="pusher", phase="prepublish") == 12
