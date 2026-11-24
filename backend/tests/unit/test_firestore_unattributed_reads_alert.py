"""Fixtures for the unattributed Firestore reads alert and its billed-series guard.

The rule annotations carry the live measurement (FC-alert-never-provably-fired);
these fixtures pin the same-window ratio, the chronological resolve, the independent
completeness/freshness guard, and both halves of the kill switch.
"""

from __future__ import annotations

import importlib.util
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]
ALERTS = REPO / "backend/charts/monitoring/alerts"
GATE = REPO / "backend/charts/monitoring/live-alert-gate.json"
BACKTEST = REPO / "backend/scripts/alert_backtest.py"
VERIFIER = REPO / "backend/scripts/verify_pusher_live_alert_route.py"
UID = "omi-firestore-unattributed-reads"
BLIND_UID = "omi-firestore-unattributed-reads-blind"
STEP = 60


def _load_backtest():
    spec = importlib.util.spec_from_file_location("alert_backtest", BACKTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backtest = _load_backtest()


@pytest.fixture(scope="module")
def verifier() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(VERIFIER)))


def rule(uid: str = UID) -> dict:
    return next(rule for rule in json.loads((ALERTS / "firestore.json").read_text()) if rule["uid"] == uid)


def ticks(
    instrumented: float,
    billed: float,
    seconds: int = 7200,
    offset: int = 0,
) -> list[tuple[int, dict]]:
    """One evaluation tick per minute with a fixed numerator and denominator."""
    return [
        (
            offset + t,
            backtest.evaluate(rule(), {"A": {(): [instrumented]}, "B": {(): [billed]}}),
        )
        for t in range(0, seconds, STEP)
    ]


def guard_ticks(value: float, seconds: int = 7200) -> list[tuple[int, dict]]:
    """One evaluation tick per minute with a fixed guard value."""
    return [(t, backtest.evaluate(rule(BLIND_UID), {"A": {(): [value]}})) for t in range(0, seconds, STEP)]


EXPECTED_BILLED_TYPES = frozenset({"LOOKUP", "QUERY", "NOT_FOUND"})


def guard_for(ages: dict[str, float]) -> float:
    """The guard's semantics for a per-type sample-age map (max by type, then min).

    The expression selects only LOOKUP, QUERY and NOT_FOUND, so an unknown type
    cannot stand in for a missing expected type.
    """
    if set(ages) != EXPECTED_BILLED_TYPES:
        return 0.0
    return 1.0 if all(age < 900 for age in ages.values()) else 0.0


def test_main_rule_shape_and_threshold():
    subject = rule()
    nodes = {node["refId"]: node["model"] for node in subject["data"]}
    assert subject["condition"] == "D"
    assert {node["datasourceUid"] for node in subject["data"] if node["refId"] in ("A", "B")} == {"gmp-cloud-run"}
    assert nodes["A"]["expr"] == "sum(rate(omi_firestore_billed_reads_by_caller_total[30m])) or vector(0)"
    assert nodes["B"]["expr"] == "avg_over_time(sum(firestore_googleapis_com:document_read_count)[30m:1m]) / 60"
    assert nodes["C"]["expression"] == "($B - $A) / $B"
    assert nodes["D"]["conditions"][0]["evaluator"] == {"params": [0.03], "type": "gt"}
    assert subject["for"] == "30m"
    assert subject["noDataState"] == "OK"
    # Enabled by default: the per-rule switch is the committed isPaused flag.
    assert subject["isPaused"] is False


def test_gap_above_three_percent_sustained_fires():
    result = backtest.episodes(rule(), ticks(900, 1000), 0, 7200, STEP)
    assert result["episodes"] == 1
    assert result["longest_seconds"] >= 1800
    # Still above 0.03 at the end of the window: the episode stays open.
    assert result["open_episodes"] == 1


def test_gap_at_or_below_three_percent_resolves():
    # 0.02: ordinary attributed traffic never opens an episode.
    assert backtest.episodes(rule(), ticks(980, 1000), 0, 7200, STEP)["episodes"] == 0
    # Exactly 0.03 is the resolve side of `> 0.03`, not a firing tick.
    assert backtest.evaluate(rule(), {"A": {(): [970]}, "B": {(): [1000]}}) == {(): 0.0}


def test_chronological_resolve_closes_at_exactly_three_percent():
    # Phase 1 (0..3540s) is 10% unattributed; phase 2 starts at 3600s at exactly 3%.
    samples = ticks(900, 1000, seconds=3600) + ticks(970, 1000, seconds=3600, offset=3600)
    result = backtest.episodes(rule(), samples, 0, 7200, STEP)
    assert result["episodes"] == 1
    assert result["open_episodes"] == 0
    # The episode opens at 1800s (the 30m pending period) and closes at 3600s.
    assert result["longest_seconds"] == 1800
    # The closing tick is exactly 3%, not below it.
    assert backtest.evaluate(rule(), {"A": {(): [970]}, "B": {(): [1000]}}) == {(): 0.0}


def test_missing_instrumented_series_reads_as_fully_unattributed():
    # or vector(0) in A means a vanished counter cannot pass as healthy coverage.
    assert backtest.evaluate(rule(), {"A": {(): [0]}, "B": {(): [1000]}}) == {(): 1.0}
    assert backtest.episodes(rule(), ticks(0, 1000), 0, 7200, STEP)["episodes"] == 1


def test_blind_rule_shape_and_fail_closed_state():
    subject = rule(BLIND_UID)
    nodes = {node["refId"]: node["model"] for node in subject["data"]}
    assert subject["condition"] == "B"
    assert subject["data"][0]["datasourceUid"] == "gmp-cloud-run"
    assert "count by (type)" in nodes["A"]["expr"]
    assert "== bool 3" in nodes["A"]["expr"]
    assert "max by (type)" in nodes["A"]["expr"]
    assert "timestamp(" in nodes["A"]["expr"]
    assert "< bool 900" in nodes["A"]["expr"]
    # The expected billed types are named explicitly, so an unknown type cannot
    # replace a missing LOOKUP, QUERY or NOT_FOUND sample.
    assert nodes["A"]["expr"].count('type=~"LOOKUP|QUERY|NOT_FOUND"') == 2
    # Both halves are zero-filled so absence cannot turn the guard into NoData.
    assert nodes["A"]["expr"].count("or vector(0)") == 2
    assert nodes["B"]["conditions"][0]["evaluator"] == {"params": [1], "type": "lt"}
    assert subject["for"] == "30m"
    assert subject["noDataState"] == "Alerting"
    assert subject["isPaused"] is False


def test_blind_rule_fires_when_the_guard_is_zero():
    # The guard rule has no B query, so an absent billed series cannot make it NoData.
    assert backtest.evaluate(rule(BLIND_UID), {"A": {(): [0]}}) == {(): 1.0}
    result = backtest.episodes(rule(BLIND_UID), guard_ticks(0), 0, 7200, STEP)
    assert result["episodes"] == 1
    assert result["open_episodes"] == 1


def test_blind_rule_resolves_when_all_types_are_fresh():
    assert backtest.evaluate(rule(BLIND_UID), {"A": {(): [1]}}) == {(): 0.0}
    assert backtest.episodes(rule(BLIND_UID), guard_ticks(1), 0, 7200, STEP)["episodes"] == 0


def test_blind_rule_requires_freshness_for_each_type():
    # One stale type with two fresh types zeroes the guard; all three fresh is 1.
    assert guard_for({"LOOKUP": 100, "QUERY": 2000, "NOT_FOUND": 100}) == 0.0
    assert guard_for({"LOOKUP": 100, "QUERY": 100, "NOT_FOUND": 100}) == 1.0
    # A missing type is not the same as a stale one; both are zero.
    assert guard_for({"LOOKUP": 100, "QUERY": 100}) == 0.0
    # The guard value drives the rule: stale -> fires, fresh -> quiet.
    assert backtest.evaluate(
        rule(BLIND_UID), {"A": {(): [guard_for({"LOOKUP": 100, "QUERY": 2000, "NOT_FOUND": 100})]}}
    ) == {(): 1.0}
    assert backtest.evaluate(
        rule(BLIND_UID), {"A": {(): [guard_for({"LOOKUP": 100, "QUERY": 100, "NOT_FOUND": 100})]}}
    ) == {(): 0.0}


@pytest.mark.parametrize(
    "replaced",
    ["LOOKUP", "QUERY", "NOT_FOUND"],
)
def test_unknown_type_cannot_replace_an_expected_type(replaced):
    # A fresh unknown type must not satisfy a missing expected type. The guard
    # rule has no B query, so the ratio's billed frame is absent here.
    ages = {expected: 100 for expected in EXPECTED_BILLED_TYPES if expected != replaced}
    ages["FUTURE_TYPE"] = 100
    assert guard_for(ages) == 0.0
    assert backtest.evaluate(rule(BLIND_UID), {"A": {(): [guard_for(ages)]}}) == {(): 1.0}


def test_selector_is_enabled_by_default_and_a_fixture_proves_disable(verifier, tmp_path, monkeypatch):
    committed = verifier.load_all_committed_rules()
    for uid in (UID, BLIND_UID):
        assert uid in committed
        # Enabled by default: the alert-rule selector imports and verifies this UID.
        assert uid in verifier.load_gated_uids(committed)
        assert uid in json.loads(GATE.read_text())["uids"]

    enabled = tmp_path / "gate-enabled.json"
    enabled.write_text(json.dumps({"uids": [UID, BLIND_UID]}))
    # Disable: the selector still names other rules, but not these two.
    disabled = tmp_path / "gate-disabled.json"
    disabled.write_text(json.dumps({"uids": ["omi-capture-finalization-memory-fence"]}))

    monkeypatch.setitem(verifier.load_gated_uids.__globals__, "GATE_FILE", enabled)
    assert verifier.load_gated_uids(committed) == (UID, BLIND_UID)
    coverage = verifier.classify_fleet_coverage({uid: committed[uid] for uid in (UID, BLIND_UID)}, {})
    assert verifier.fleet_gate_failures(coverage, (UID, BLIND_UID), "gated") == [
        f"live alert rule {uid} is absent from Grafana" for uid in (UID, BLIND_UID)
    ]

    # Disable: removing the UIDs from the selector takes them out of the import set.
    monkeypatch.setitem(verifier.load_gated_uids.__globals__, "GATE_FILE", disabled)
    assert UID not in verifier.load_gated_uids(committed)
    assert BLIND_UID not in verifier.load_gated_uids(committed)
    assert verifier.fleet_gate_failures(coverage, (), "gated") == []


@pytest.mark.parametrize("uid", [UID, BLIND_UID])
def test_switch_pauses_and_resumes_each_rule(verifier, uid):
    subject = rule(uid)
    paused = dict(subject, isPaused=True)
    live_paused = dict(subject, isPaused=True)
    # Disable: isPaused true matches a paused live rule and Grafana stops evaluating it.
    assert verifier.mismatched_definition_keys(live_paused, paused) == []
    # Enable: the default false rule cannot match a paused live rule.
    assert verifier.mismatched_definition_keys(live_paused, subject) == ["isPaused"]
    assert verifier.mismatched_definition_keys(dict(subject), subject) == []


@pytest.mark.parametrize("uid", [UID, BLIND_UID])
def test_development_import_skips_the_production_only_datasource(verifier, uid):
    # The gmp-cloud-run shadow datasource is a production overlay, so the
    # automatic development import must not install these pages.
    assert uid in verifier.PRODUCTION_ONLY_IMPORT_UIDS
    assert uid in verifier.load_live_stt_import_rules(production=True)
    assert uid not in verifier.load_live_stt_import_rules(production=False)
