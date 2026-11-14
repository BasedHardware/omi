"""Budget, low-output and hourly-step contracts for SCA-2189."""

import importlib.util
import json
import runpy
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / "backend/charts/monitoring"
RATIO = "omi-firestore-batch-reads-audio-hour"
NO_OUTPUT = "omi-firestore-batch-reads-no-output"
STEP = "omi-firestore-billed-reads-step"
RULES = {rule["uid"]: rule for rule in json.loads((MONITORING / "alerts/firestore.json").read_text())}
SPEC = importlib.util.spec_from_file_location("cost_backtest", REPO / "backend/scripts/alert_backtest.py")
BACKTEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKTEST)


def evaluate(uid, first, second):
    return BACKTEST.evaluate(RULES[uid], {"A": {(): [first]}, "B": {(): [second]}})


@pytest.mark.parametrize(
    "uid,first,second,expected",
    [
        (RATIO, 78000, 100, 1),
        (RATIO, 60000, 100, 0),
        (RATIO, 60001, 50, 1),
        (RATIO, 101000, 49.999, 0),
        (RATIO, 10000001, 0, 0),
        (NO_OUTPUT, 10000001, 49.999, 1),
        (NO_OUTPUT, 10000001, 0, 1),
        (NO_OUTPUT, 10000000, 0, 0),
        (NO_OUTPUT, 10000001, 50, 0),
        (STEP, 126000000, 100000000, 1),
        (STEP, 125000000, 100000000, 0),
        (STEP, 100000000, 100000000, 0),
    ],
)
def test_thresholds_and_complementary_output_guard(uid, first, second, expected):
    assert evaluate(uid, first, second) == {(): expected}


@pytest.mark.parametrize("uid,first,second", [(RATIO, 78000, 100), (NO_OUTPUT, 11000000, 0), (STEP, 126, 100)])
def test_two_hour_pending_then_resolve(uid, first, second):
    samples = [(minute * 60, evaluate(uid, first, second)) for minute in range(181)]
    samples.append((181 * 60, evaluate(uid, 0, 100)))
    result = BACKTEST.episodes(RULES[uid], samples, 0, 182 * 60, 60)
    assert result["episodes"] == 1
    assert result["open_episodes"] == 0
    assert result["longest_seconds"] == 3660
    short = BACKTEST.episodes(RULES[uid], samples[:120], 0, 7200, 60)
    assert short["episodes"] == 0


def test_batch_query_selects_both_caller_prefixes_and_uses_real_counters():
    for uid in (RATIO, NO_OUTPUT):
        nodes = RULES[uid]["data"]
        assert 'caller=~"(database|utils)\\\\.batch.*"' in nodes[0]["model"]["expr"]
        assert "increase(omi_firestore_billed_reads_by_caller_total" in nodes[0]["model"]["expr"]
        assert nodes[1]["model"]["expr"] == (
            "(sum(increase(omi_batch_pipeline_completed_audio_seconds_total[1h])) / 3600) or vector(0)"
        )
    assert "clamp_min(" in RULES[RATIO]["data"][0]["model"]["expr"]


def test_step_samples_seven_matching_full_hours_without_daily_subquery_alignment():
    nodes = RULES[STEP]["data"]
    metric = "firestore_googleapis_com:document_read_count"
    coverage = (
        "(min(count_over_time(" + metric + "[1h] offset 1ms)) >= 58) and "
        "(count(count by (type) (count_over_time(" + metric + "[1h] offset 1ms))) == 3)"
    )
    hourly = "last_over_time((sum(sum_over_time(" + metric + "[1h] offset 1ms)) and " + coverage + ")[1h:1h])"
    assert nodes[0]["model"]["expr"] == hourly
    historical = nodes[1]["model"]["expr"]
    expected = (
        "quantile(0.5, "
        + " or ".join(
            'label_replace(' + hourly[:-1] + f' offset {day}d), "day", "{day}", "", "")' for day in range(1, 8)
        )
        + ")"
    )
    union = expected[len("quantile(0.5, ") : -1]
    assert historical == "(" + expected + ") and (count(" + union + ") == 7) and (" + expected + " > 0)"
    assert RULES[STEP]["noDataState"] == "Alerting"
    assert "[7d:1d]" not in historical
    assert "increase(" not in hourly


@pytest.mark.parametrize("uid", [RATIO, NO_OUTPUT, STEP])
def test_rules_are_enabled_production_only_tickets_with_owner_and_rollback(uid):
    rule = RULES[uid]
    assert rule["for"] == "2h"
    assert rule["isPaused"] is False
    assert rule["annotations"]["severity"] == "ticket"
    assert rule["labels"]["tier"] == "agent"
    assert rule["labels"]["owner"] == "firestore-cost-owner"
    assert rule["labels"]["owner_issue"] == "SCA-2173"
    assert rule["notification_settings"]["receiver"] == "Omi - Services Alerting (Telegram)"
    assert {node["datasourceUid"] for node in rule["data"][:2]} == {"gmp-cloud-run"}
    verifier = runpy.run_path(str(REPO / "backend/scripts/verify_pusher_live_alert_route.py"))
    assert uid in json.loads((MONITORING / "live-alert-gate.json").read_text())["uids"]
    assert uid in verifier["load_live_stt_import_rules"](production=True)
    assert uid not in verifier["load_live_stt_import_rules"](production=False)
    assert verifier["mismatched_definition_keys"](dict(rule, isPaused=True), rule) == ["isPaused"]


def test_shared_checksum_pinned_promtool_hook_runs_the_cost_fixtures():
    script = REPO / "backend/scripts/check_record_token_lease_promql.py"
    source = script.read_text()
    assert "firestore_cost_budget.py" in source
    assert "hashlib.sha256" in source
    assert str(script.relative_to(REPO)) in (REPO / ".github/checks-manifest.yaml").read_text()
