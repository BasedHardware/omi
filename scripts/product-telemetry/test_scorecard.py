from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("scorecard.py")
SPEC = importlib.util.spec_from_file_location("product_telemetry_scorecard", SCRIPT)
assert SPEC and SPEC.loader
scorecard_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scorecard_module
SPEC.loader.exec_module(scorecard_module)


def _fixture(name: str):
    events, report = scorecard_module.read_jsonl(
        Path(__file__).parents[2] / "contracts/product-telemetry/fixtures" / name
    )
    return events, report


def test_fixture_scorecard_reports_real_regression_inputs():
    events, report = _fixture("regression.jsonl")
    result = scorecard_module.scorecard(events, as_of=scorecard_module._parse_time("2026-09-22T00:00:00Z"))

    assert report.valid == 14
    assert result["metrics"]["journey_reliability"]["value"] == 0.6
    assert result["metrics"]["retention_d1"]["status"] == "ok"
    assert result["metrics"]["retention_d30"]["status"] == "insufficient_evidence"
    assert result["metrics"]["helpfulness_rate"]["value"] == 0.0


def test_paid_churn_requires_snapshot_and_excludes_scheduled_cancellation():
    events, _ = _fixture("billing.jsonl")
    result = scorecard_module.scorecard(events, as_of=scorecard_module._parse_time("2026-09-03T00:00:00Z"))
    metric = result["metrics"]["paid_churn_rate"]
    assert metric["status"] == "ok"
    assert metric["snapshot_id"] == "start-2026-09-01"
    assert metric["numerator"] == 1 and metric["denominator"] == 2


def test_paid_churn_counts_ended_subscription_even_when_stripe_reason_is_cancellation_requested():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory(
            {
                "event_id": "snapshot",
                "event_name": "Billing Paid Population Snapshot",
                "user_id": "u1",
                "occurred_at": "2026-09-01T00:00:00Z",
                "namespace": "mobile",
                "environment": "production",
                "app_build": "1.0.0",
                "properties": {
                    "snapshot_id": "start",
                    "snapshot_role": "start_of_window",
                    "snapshot_at": "2026-09-01T00:00:00Z",
                },
            }
        ),
        factory(
            {
                "event_id": "ended",
                "event_name": "Billing Subscription Churned",
                "user_id": "u1",
                "occurred_at": "2026-09-02T00:00:00Z",
                "namespace": "mobile",
                "environment": "production",
                "app_build": "1.0.0",
                "properties": {"reason": "cancellation_requested"},
            }
        ),
    ]
    result = scorecard_module.scorecard(
        [event for event in events if event is not None],
        as_of=scorecard_module._parse_time("2026-09-03T00:00:00Z"),
    )
    assert result["metrics"]["paid_churn_rate"]["numerator"] == 1


def test_paid_churn_without_snapshot_is_insufficient():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "s", "event_name": "Billing Subscription Started", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z"}),
        factory({"event_id": "c", "event_name": "Billing Subscription Churned", "user_id": "u", "occurred_at": "2026-09-02T00:00:00Z"}),
    ]
    result = scorecard_module.scorecard([event for event in events if event is not None])
    assert result["metrics"]["paid_churn_rate"]["status"] == "insufficient_evidence"
    assert result["metrics"]["paid_churn_rate"]["denominator"] == 0


def test_duplicate_and_late_policy_is_explicit():
    path = Path(__file__).with_name("_tmp_events.jsonl")
    path.write_text(
        "\n".join(
            [
                json.dumps({"event_id": "same", "event_name": "Product Value", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z", "ingested_at": "2026-09-01T00:05:00Z"}),
                json.dumps({"event_id": "same", "event_name": "Product Value", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        events, report = scorecard_module.read_jsonl(path)
    finally:
        path.unlink()
    assert len(events) == 1
    assert report.duplicates == 1
    assert report.late == 1
    assert report.late_seconds == 300


def test_missing_data_is_not_a_confident_zero():
    result = scorecard_module.scorecard([])
    assert result["status"] == "insufficient_evidence"
    assert result["metrics"] == {}


def test_recording_linkage_requires_explicit_authoritative_join():
    event_factory = scorecard_module.Event.from_mapping
    events = [
        event_factory(
            {
                "event_id": "r1",
                "event_name": "Recording Started",
                "user_id": "u1",
                "occurred_at": "2026-09-01T00:00:00Z",
                "properties": {"recording_id": "rec-1"},
            }
        ),
        event_factory(
            {
                "event_id": "r2",
                "event_name": "Product Journey Outcome",
                "user_id": "u1",
                "occurred_at": "2026-09-01T00:00:01Z",
                "properties": {"journey": "capture", "correlation_id": "rec-1", "object_id": "conv-1"},
            }
        ),
    ]
    result = scorecard_module.scorecard([event for event in events if event is not None])
    assert result["metrics"]["recording_conversation_linkage"]["value"] == 1.0


def test_experiment_uses_exposure_denominator_and_detects_imbalance():
    events, _ = _fixture("experiment.jsonl")
    result = scorecard_module.experiment_comparison(
        events,
        experiment_id="ui-v2",
        metric="success",
        as_of=scorecard_module._parse_time("2026-09-03T00:00:00Z"),
    )
    assert result["status"] == "ok"
    assert result["variants"]["control"]["assigned"] == 2
    assert result["variants"]["treatment"]["assigned"] == 2
    assert result["variants"]["treatment"]["matured"] == 2
    assert result["comparison"]["allocation_imbalance"] > 0.1


def test_workflow_emits_actionable_packet_for_seeded_regression():
    events, _ = _fixture("regression.jsonl")
    packet = scorecard_module.evidence_packet(events, baseline_build="1.0.0", candidate_build="1.1.0", threshold=0.05)
    assert packet["status"] == "regression_detected"
    assert packet["proposed_action"]["type"] == "investigate_and_reproduce"
    assert "1.1.0" in packet["attribution"]["builds"]
    assert packet["attribution"]["trace_ids"] == ["tr-1", "tr-2"]


def test_experiment_fixture_compares_corrected_candidate_with_holdout():
    events, _ = _fixture("experiment-corrected.jsonl")
    result = scorecard_module.experiment_comparison(
        events,
        experiment_id="ui-corrected",
        metric="success",
        as_of=scorecard_module._parse_time("2026-09-03T00:00:00Z"),
    )
    assert result["status"] == "ok"
    assert result["comparison"]["absolute_difference"] == 0.0
    assert result["variants"]["control"]["matured"] == 1
    assert result["variants"]["candidate"]["matured"] == 1


def test_experiment_reader_accepts_posthog_feature_outcome_and_skips_qa():
    event_factory = scorecard_module.Event.from_mapping
    events = [
        event_factory({"event_id": "x1", "event_name": "experiment_assigned", "user_id": "u1", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "ui-feature", "variant": "control"}}),
        event_factory({"event_id": "x2", "event_name": "experiment_exposed", "user_id": "u1", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"experiment_key": "ui-feature", "variant": "control"}}),
        event_factory({"event_id": "x3", "event_name": "experiment_assigned", "user_id": "u2", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "ui-feature", "variant": "candidate"}}),
        event_factory({"event_id": "x4", "event_name": "experiment_exposed", "user_id": "u2", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"experiment_key": "ui-feature", "variant": "candidate"}}),
        event_factory({"event_id": "x5", "event_name": "Product Journey Outcome", "user_id": "u1", "occurred_at": "2026-09-02T00:00:00Z", "properties": {"$feature/ui-feature": "control", "experiment_context_verified": True, "journey": "summary_feedback", "outcome": "success"}}),
        event_factory({"event_id": "x6", "event_name": "Product Journey Outcome", "user_id": "u2", "occurred_at": "2026-09-02T00:00:00Z", "properties": {"$feature/ui-feature": "candidate", "experiment_context_verified": True, "journey": "summary_feedback", "outcome": "success", "experiment_qa": True}}),
    ]
    result = scorecard_module.experiment_comparison(
        [event for event in events if event is not None],
        experiment_id="ui-feature",
        journey="summary_feedback",
        as_of=scorecard_module._parse_time("2026-09-03T00:00:00Z"),
    )
    assert result["status"] == "insufficient_evidence"
    assert result["variants"]["control"]["successes"] == 1
    assert result["variants"]["candidate"]["successes"] == 0


def test_posthog_mapping_prefers_product_time_and_namespace_and_keeps_repeats_without_ids():
    first = scorecard_module.Event.from_mapping(
        {
            "event": "Product Value",
            "distinct_id": "u1",
            "timestamp": "2026-09-02T00:00:00Z",
            "uuid": "posthog-1",
            "$app_namespace": "mobile",
            "properties": {"occurred_at": "2026-09-01T00:00:00Z", "$app_build": "42", "client_app_namespace": "com.friend.ios", "client_app_profile": "production", "environment": "backend-prod"},
        }
    )
    second = scorecard_module.Event.from_mapping(
        {
            "event": "Product Value",
            "distinct_id": "u1",
            "timestamp": "2026-09-02T00:00:00Z",
            "properties": {"occurred_at": "2026-09-01T00:00:00Z"},
        }
    )
    assert first is not None and first.occurred_at == scorecard_module._parse_time("2026-09-01T00:00:00Z")
    assert first.namespace == "com.friend.ios" and first.environment == "production" and first.server_environment == "backend-prod"
    assert first.app_build == "42" and first.event_id == "posthog-1"
    assert second is not None and second.event_id == ""


def test_posthog_query_requires_and_renders_bounded_window():
    rendered = scorecard_module._render_posthog_query(
        "SELECT * FROM events WHERE timestamp >= {date_from} AND timestamp < {date_to} LIMIT 50001",
        since="2026-09-01T00:00:00Z",
        until="2026-09-02T00:00:00Z",
    )
    assert "{date_from}" not in rendered and "{date_to}" not in rendered
    assert "toDateTime('2026-09-01T00:00:00Z')" in rendered
    with pytest.raises(ValueError):
        scorecard_module._render_posthog_query("SELECT 1", since="2026-09-02T00:00:00Z", until="2026-09-01T00:00:00Z")
    with pytest.raises(ValueError, match="placeholders"):
        scorecard_module._render_posthog_query("SELECT 1 LIMIT 50001", since="2026-09-01T00:00:00Z", until="2026-09-02T00:00:00Z")
    with pytest.raises(ValueError, match="LIMIT 50001"):
        scorecard_module._render_posthog_query("SELECT * FROM events WHERE timestamp >= {date_from} AND timestamp < {date_to}", since="2026-09-01T00:00:00Z", until="2026-09-02T00:00:00Z")


def test_checked_in_posthog_queries_have_bounded_window_and_sentinel_limit():
    query_dir = Path(__file__).parents[2] / "contracts/product-telemetry/posthog"
    for path in sorted(query_dir.glob("*.hogql")):
        query = path.read_text(encoding="utf-8")
        assert "{date_from}" in query and "{date_to}" in query
        assert "LIMIT 50001" in query
        rendered = scorecard_module._render_posthog_query(
            query,
            since="2026-09-01T00:00:00Z",
            until="2026-09-02T00:00:00Z",
        )
        assert "{date_from}" not in rendered and "{date_to}" not in rendered


class _PostHogResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _PostHogOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return _PostHogResponse(json.dumps(self.payload).encode("utf-8"))


def _posthog_query_fixture():
    return "SELECT * FROM events WHERE timestamp >= {date_from} AND timestamp < {date_to} LIMIT 50001"


def test_posthog_fetch_requires_explicit_complete_marker_and_sends_sentinel_limit(monkeypatch):
    payload = {
        "columns": ["event_id", "event_name", "user_id", "occurred_at", "namespace", "environment", "app_build", "properties"],
        "results": [["e1", "Product Value", "u1", "2026-09-01T00:00:00Z", "mobile", "production", "1", {}]],
        "hasMore": False,
    }
    opener = _PostHogOpener(payload)
    monkeypatch.setenv("POSTHOG_HOST", "https://posthog.example")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "123")
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "secret")
    monkeypatch.setattr(scorecard_module.urllib.request, "build_opener", lambda *_args: opener)

    events = scorecard_module.fetch_posthog_events(
        _posthog_query_fixture(),
        since="2026-09-01T00:00:00Z",
        until="2026-09-02T00:00:00Z",
    )

    assert len(events) == 1
    sent_query = json.loads(opener.request.data.decode("utf-8"))["query"]["query"]
    assert "LIMIT 50001" in sent_query
    assert "{date_from}" not in sent_query


@pytest.mark.parametrize(
    "metadata",
    [
        {"hasMore": True},
        {"partial": True},
        {"hasMore": "ambiguous"},
        {"row_count": 2},
    ],
)
def test_posthog_fetch_rejects_incomplete_or_ambiguous_results(monkeypatch, metadata):
    payload = {"results": [["e1"]], **metadata}
    opener = _PostHogOpener(payload)
    monkeypatch.setenv("POSTHOG_HOST", "https://posthog.example")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "123")
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "secret")
    monkeypatch.setattr(scorecard_module.urllib.request, "build_opener", lambda *_args: opener)

    with pytest.raises(RuntimeError, match="complete local export|more rows|incomplete|ambiguous"):
        scorecard_module.fetch_posthog_events(
            _posthog_query_fixture(),
            since="2026-09-01T00:00:00Z",
            until="2026-09-02T00:00:00Z",
        )


def test_posthog_fetch_rejects_safety_cap_and_invalid_connection_settings(monkeypatch):
    with pytest.raises(RuntimeError, match="safety cap"):
        scorecard_module._validate_posthog_completeness({"results": [None] * scorecard_module.POSTHOG_RESULT_LIMIT, "hasMore": False})

    query = _posthog_query_fixture()
    monkeypatch.setenv("POSTHOG_HOST", "http://posthog.example")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "123")
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "secret")
    with pytest.raises(RuntimeError, match="HTTPS origin"):
        scorecard_module.fetch_posthog_events(query, since="2026-09-01T00:00:00Z", until="2026-09-02T00:00:00Z")

    monkeypatch.setenv("POSTHOG_HOST", "https://user:password@posthog.example")
    with pytest.raises(RuntimeError, match="HTTPS origin"):
        scorecard_module.fetch_posthog_events(query, since="2026-09-01T00:00:00Z", until="2026-09-02T00:00:00Z")

    monkeypatch.setenv("POSTHOG_HOST", "https://posthog.example")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "project")
    with pytest.raises(RuntimeError, match="numeric"):
        scorecard_module.fetch_posthog_events(query, since="2026-09-01T00:00:00Z", until="2026-09-02T00:00:00Z")


def test_retention_uses_account_created_and_closed_day_windows():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "s", "event_name": "Account Created", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z"}),
        factory({"event_id": "v1", "event_name": "Product Value", "user_id": "u", "occurred_at": "2026-09-02T12:00:00Z"}),
        factory({"event_id": "v2", "event_name": "Product Value", "user_id": "u", "occurred_at": "2026-09-03T00:00:00Z"}),
    ]
    result = scorecard_module.activation_and_retention(
        [event for event in events if event is not None],
        as_of=scorecard_module._parse_time("2026-09-03T00:00:00Z"),
    )
    # D1 is not mature until signup+2d, and the event at signup+2d belongs to
    # D2, never to the closed D1 [signup+1d, signup+2d) window.
    assert result["retention_d1"]["status"] == "ok"
    assert result["retention_d1"]["value"] == 1.0


def test_feedback_counts_only_durable_submission_and_deduplicates_feedback_id():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "fx", "event_name": "Product Journey Started", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"journey": "summary_feedback"}}),
        factory({"event_id": "fo", "event_name": "Product Journey Outcome", "user_id": "u", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"journey": "summary_feedback", "outcome": "failure"}}),
        factory({"event_id": "f1", "event_name": "Product Feedback Submitted", "user_id": "u", "occurred_at": "2026-09-01T00:00:02Z", "properties": {"feedback_id": "id-1", "value": 1}}),
        factory({"event_id": "f2", "event_name": "Product Feedback Submitted", "user_id": "u", "occurred_at": "2026-09-01T00:00:03Z", "properties": {"feedback_id": "id-1", "value": -1}}),
    ]
    result = scorecard_module.feedback_metrics([event for event in events if event is not None])
    assert result["helpfulness_exposure_response_rate"]["value"] == 1.0
    assert result["helpfulness_rate"]["value"] == 1.0


def test_feedback_id_deduplication_is_scoped_to_authenticated_user():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory(
            {
                "event_id": "exposure-1",
                "event_name": "Product Journey Started",
                "user_id": "u1",
                "occurred_at": "2026-09-01T00:00:00Z",
                "properties": {"journey": "summary_feedback"},
            }
        ),
        factory(
            {
                "event_id": "exposure-2",
                "event_name": "Product Journey Started",
                "user_id": "u2",
                "occurred_at": "2026-09-01T00:00:00Z",
                "properties": {"journey": "summary_feedback"},
            }
        ),
        factory(
            {
                "event_id": "feedback-1",
                "event_name": "Product Feedback Submitted",
                "user_id": "u1",
                "occurred_at": "2026-09-01T00:00:01Z",
                "properties": {"feedback_id": "same-id", "value": 1},
            }
        ),
        factory(
            {
                "event_id": "feedback-2",
                "event_name": "Product Feedback Submitted",
                "user_id": "u2",
                "occurred_at": "2026-09-01T00:00:02Z",
                "properties": {"feedback_id": "same-id", "value": -1},
            }
        ),
    ]
    result = scorecard_module.feedback_metrics([event for event in events if event is not None])
    assert result["helpfulness_exposure_response_rate"]["numerator"] == 2
    assert result["helpfulness_rate"]["denominator"] == 2
    assert result["helpfulness_rate"]["numerator"] == 1


def test_journey_does_not_create_attempts_for_orphans_and_pipeline_close_is_cancelled():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "orphan", "event_name": "Product Journey Outcome", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"correlation_id": "missing", "journey": "capture", "outcome": "success"}}),
        factory({"event_id": "start", "event_name": "Recording Started", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"recording_id": "rec"}}),
        factory({"event_id": "done", "event_name": "Recording Completed", "user_id": "u", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"recording_id": "rec", "reason": "pipeline_closed", "audio_observed": True}}),
    ]
    result = scorecard_module.journey_metrics([event for event in events if event is not None], as_of=scorecard_module._parse_time("2026-09-02T00:00:00Z"))
    assert result["journey_reliability"]["value"] == 0.0
    assert result["journey_reliability"]["terminal"]["cancelled"] == 1
    assert result["journey_reliability"]["orphan_outcomes"] == 1


def test_recording_close_does_not_claim_end_to_end_success_or_native_batch_loss():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "start", "event_name": "Recording Started", "user_id": "u", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"recording_id": "rec-live"}}),
        factory({"event_id": "done", "event_name": "Recording Completed", "user_id": "u", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"recording_id": "rec-live", "reason": "user_stopped", "audio_observed": True, "audio_observation_coverage": "dart_ingress"}}),
        factory({"event_id": "batch-start", "event_name": "Recording Started", "user_id": "u", "occurred_at": "2026-09-01T00:01:00Z", "properties": {"recording_id": "rec-batch"}}),
        factory({"event_id": "batch-done", "event_name": "Recording Completed", "user_id": "u", "occurred_at": "2026-09-01T00:01:01Z", "properties": {"recording_id": "rec-batch", "reason": "user_stopped", "audio_observed": False, "audio_observation_coverage": "native_batch_unavailable"}}),
    ]
    result = scorecard_module.journey_metrics([event for event in events if event is not None], as_of=scorecard_module._parse_time("2026-09-02T00:00:00Z"))
    assert result["journey_reliability"]["value"] == 0.0
    assert result["journey_reliability"]["terminal"]["unknown"] == 2


def test_experiment_missing_outcome_stays_in_denominator_with_bounds():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "a1", "event_name": "experiment_assigned", "user_id": "control", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "control"}}),
        factory({"event_id": "x1", "event_name": "experiment_exposed", "user_id": "control", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"experiment_key": "e", "variant": "control"}}),
        factory({"event_id": "a2", "event_name": "experiment_assigned", "user_id": "compact", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "compact"}}),
        factory({"event_id": "x2", "event_name": "experiment_exposed", "user_id": "compact", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"experiment_key": "e", "variant": "compact"}}),
        factory({"event_id": "o1", "event_name": "experiment_outcome", "user_id": "control", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"experiment_key": "e", "metric": "success", "value": 1}}),
    ]
    result = scorecard_module.experiment_comparison([event for event in events if event is not None], experiment_id="e", as_of=scorecard_module._parse_time("2026-09-02T00:00:00Z"))
    assert result["status"] == "insufficient_evidence"
    assert result["comparison"]["control"] == "control"
    assert result["variants"]["compact"]["matured"] == 1
    assert result["variants"]["compact"]["missing_outcomes"] == 1
    assert result["variants"]["compact"]["success_rate"] is None
    assert result["variants"]["compact"]["success_rate_bounds"] == [0.0, 1.0]


def test_unverified_feature_properties_cannot_attribute_product_outcomes():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "a1", "event_name": "experiment_assigned", "user_id": "u1", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "control"}}),
        factory({"event_id": "x1", "event_name": "experiment_exposed", "user_id": "u1", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"experiment_key": "e", "variant": "control"}}),
        factory({"event_id": "a2", "event_name": "experiment_assigned", "user_id": "u2", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "candidate"}}),
        factory({"event_id": "x2", "event_name": "experiment_exposed", "user_id": "u2", "occurred_at": "2026-09-01T00:00:01Z", "properties": {"experiment_key": "e", "variant": "candidate"}}),
        factory({"event_id": "o1", "event_name": "Product Journey Outcome", "user_id": "u1", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"$feature/e": "control", "outcome": "success"}}),
        factory({"event_id": "o2", "event_name": "Product Journey Outcome", "user_id": "u2", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"$feature/e": "candidate", "experiment_context_verified": True, "journey": "summary_feedback", "outcome": "success"}}),
    ]
    result = scorecard_module.experiment_comparison([event for event in events if event is not None], experiment_id="e", journey="summary_feedback", as_of=scorecard_module._parse_time("2026-09-02T00:00:00Z"))
    assert result["status"] == "insufficient_evidence"
    assert result["variants"]["control"]["missing_outcomes"] == 1
    assert result["variants"]["candidate"]["successes"] == 1


def test_experiment_ignores_feature_properties_on_non_outcome_events_and_requires_journey_for_product_outcomes():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "x1", "event_name": "experiment_exposed", "user_id": "control", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "control"}}),
        factory({"event_id": "x2", "event_name": "experiment_exposed", "user_id": "candidate", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "candidate"}}),
        factory({"event_id": "x3", "event_name": "$identify", "user_id": "control", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"$feature/e": "control"}}),
        factory({"event_id": "x4", "event_name": "Product Journey Outcome", "user_id": "candidate", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"$feature/e": "candidate", "experiment_context_verified": True, "journey": "search", "outcome": "success"}}),
    ]
    result = scorecard_module.experiment_comparison(
        [event for event in events if event is not None],
        experiment_id="e",
        as_of=scorecard_module._parse_time("2026-09-02T00:00:00Z"),
    )
    assert result["status"] == "insufficient_evidence"
    assert result["variants"]["control"]["missing_outcomes"] == 1
    assert result["variants"]["candidate"]["missing_outcomes"] == 1


def test_experiment_failure_metric_counts_failure_outcome():
    factory = scorecard_module.Event.from_mapping
    events = [
        factory({"event_id": "x1", "event_name": "experiment_exposed", "user_id": "control", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "control"}}),
        factory({"event_id": "x2", "event_name": "experiment_exposed", "user_id": "candidate", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "candidate"}}),
        factory({"event_id": "x3", "event_name": "Product Journey Outcome", "user_id": "control", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"$feature/e": "control", "experiment_context_verified": True, "journey": "summary_feedback", "outcome": "failure", "failure": "server"}}),
        factory({"event_id": "x4", "event_name": "Product Journey Outcome", "user_id": "candidate", "occurred_at": "2026-09-01T01:00:00Z", "properties": {"$feature/e": "candidate", "experiment_context_verified": True, "journey": "summary_feedback", "outcome": "success", "failure": "none"}}),
    ]
    result = scorecard_module.experiment_comparison(
        [event for event in events if event is not None],
        experiment_id="e",
        metric="failure",
        journey="summary_feedback",
        as_of=scorecard_module._parse_time("2026-09-02T00:00:00Z"),
    )
    assert result["status"] == "ok"
    assert result["variants"]["control"]["successes"] == 1
    assert result["variants"]["candidate"]["successes"] == 0


def test_experiment_unknown_variant_and_conflicting_version_fail_closed():
    factory = scorecard_module.Event.from_mapping
    unknown = [
        factory({"event_id": "x1", "event_name": "experiment_exposed", "user_id": "u1", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "unregistered", "experiment_version": 1}}),
        factory({"event_id": "x2", "event_name": "experiment_exposed", "user_id": "u2", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "control", "experiment_version": 1}}),
    ]
    result = scorecard_module.experiment_comparison([event for event in unknown if event is not None], experiment_id="e")
    assert result["status"] == "insufficient_evidence"
    assert result["reason"] == "unknown_variant"

    conflict = [
        factory({"event_id": "x3", "event_name": "experiment_exposed", "user_id": "u1", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "control", "experiment_version": 1}}),
        factory({"event_id": "x4", "event_name": "experiment_exposed", "user_id": "u2", "occurred_at": "2026-09-01T00:00:00Z", "properties": {"experiment_key": "e", "variant": "candidate", "experiment_version": 2}}),
    ]
    result = scorecard_module.experiment_comparison([event for event in conflict if event is not None], experiment_id="e")
    assert result["status"] == "insufficient_evidence"
    assert result["reason"] == "experiment_version_conflict"


def test_billing_snapshot_converter_is_local_and_bounded():
    snapshot = scorecard_module.Path(__file__).with_name("_billing_rows.json")
    snapshot.write_text(
        json.dumps(
            [
                {"uid": "u1", "plan": "unlimited", "status": "active"},
                {"uid": "u2", "plan": "basic", "status": "active"},
                {"uid": "u1", "plan": "unlimited", "status": "active", "customer": "must-not-emit"},
            ]
        ),
        encoding="utf-8",
    )
    try:
        import importlib.util
        billing_spec = importlib.util.spec_from_file_location("billing_snapshot", Path(__file__).with_name("billing_snapshot.py"))
        assert billing_spec and billing_spec.loader
        billing = importlib.util.module_from_spec(billing_spec)
        sys.modules[billing_spec.name] = billing
        billing_spec.loader.exec_module(billing)
        rows = billing.load_rows(snapshot)
        events = billing.convert(rows, snapshot_id="start-1", snapshot_at=scorecard_module._parse_time("2026-09-01T00:00:00Z"))
    finally:
        snapshot.unlink()
    assert len(events) == 1
    assert events[0]["event_name"] == "Billing Paid Population Snapshot"
    assert "customer" not in events[0]["properties"]
    assert events[0]["properties"]["billing_scope"] == "billing_independent"


def test_billing_snapshot_converter_requires_explicit_scope_for_mobile_join():
    billing_spec = importlib.util.spec_from_file_location("billing_snapshot_scoped", Path(__file__).with_name("billing_snapshot.py"))
    assert billing_spec and billing_spec.loader
    billing = importlib.util.module_from_spec(billing_spec)
    sys.modules[billing_spec.name] = billing
    billing_spec.loader.exec_module(billing)
    events = billing.convert(
        [{"uid": "u1", "plan": "unlimited", "status": "active"}],
        snapshot_id="start-1",
        snapshot_at=scorecard_module._parse_time("2026-09-01T00:00:00Z"),
        namespace="com.friend.ios",
        environment="production",
        app_build="1.0.0",
    )
    assert events[0]["client_app_namespace"] == "com.friend.ios"
    assert events[0]["client_app_profile"] == "production"
    assert events[0]["app_build"] == "1.0.0"
    assert events[0]["properties"]["billing_scope"] == "mobile_join"
