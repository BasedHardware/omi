"""Fixtures for the unattributed Firestore reads alert: fire/resolve and its switch.

The rule's own annotations carry the live measurement (FC-alert-never-provably-fired);
these fixtures pin the threshold behaviour and both halves of the kill switch.
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


def rule() -> dict:
    return next(rule for rule in json.loads((ALERTS / "firestore.json").read_text()) if rule["uid"] == UID)


def ticks(instrumented: float, billed: float, seconds: int = 7200) -> list[tuple[int, dict]]:
    """One evaluation tick per minute with a fixed numerator and denominator."""
    return [
        (t, backtest.evaluate(rule(), {"A": {(): [instrumented]}, "B": {(): [billed]}}))
        for t in range(0, seconds, STEP)
    ]


def test_rule_shape_pointers_and_threshold():
    subject = rule()
    nodes = {node["refId"]: node["model"] for node in subject["data"]}
    assert subject["condition"] == "D"
    assert {node["datasourceUid"] for node in subject["data"] if node["refId"] in ("A", "B")} == {"gmp-cloud-run"}
    assert nodes["A"]["expr"] == "sum(rate(omi_firestore_billed_reads_by_caller_total[30m])) or vector(0)"
    assert nodes["B"]["expr"] == "avg_over_time(sum(firestore_googleapis_com:document_read_count)[30m:1m]) / 60"
    assert nodes["C"]["expression"] == "($B - $A) / $B"
    threshold = nodes["D"]["conditions"][0]["evaluator"]
    assert threshold == {"params": [0.03], "type": "gt"}
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
    # A real episode closes as soon as the ratio returns to 0.03.
    samples = ticks(900, 1000, 3600) + ticks(970, 1000, 3600)
    result = backtest.episodes(rule(), samples, 0, 7200, STEP)
    assert result["episodes"] == 1
    assert result["open_episodes"] == 0


def test_missing_instrumented_series_reads_as_fully_unattributed():
    # or vector(0) in A means a vanished counter cannot pass as healthy coverage.
    assert backtest.evaluate(rule(), {"A": {(): [0]}, "B": {(): [1000]}}) == {(): 1.0}
    assert backtest.episodes(rule(), ticks(0, 1000), 0, 7200, STEP)["episodes"] == 1


def test_missing_billed_series_stays_no_data_not_a_page():
    # B absent produces no frame; the billed-side guard is omi-firestore-metric-absent.
    assert backtest.evaluate(rule(), {"A": {(): [900]}, "B": {}}) == {}
    assert rule()["noDataState"] == "OK"


def test_selector_is_enabled_by_default_and_a_fixture_proves_disable(verifier, tmp_path, monkeypatch):
    committed = verifier.load_all_committed_rules()
    assert UID in committed
    # Enabled by default: the alert-rule selector imports and verifies this UID.
    assert UID in verifier.load_gated_uids(committed)
    assert UID in json.loads(GATE.read_text())["uids"]

    enabled = tmp_path / "gate-enabled.json"
    enabled.write_text(json.dumps({"uids": [UID]}))
    # Disable: the selector still names other rules, but not this one.
    disabled = tmp_path / "gate-disabled.json"
    disabled.write_text(json.dumps({"uids": ["omi-capture-finalization-memory-fence"]}))

    monkeypatch.setitem(verifier.load_gated_uids.__globals__, "GATE_FILE", enabled)
    assert verifier.load_gated_uids(committed) == (UID,)
    # A rule that is absent live fails the gated fleet check while selected.
    coverage = verifier.classify_fleet_coverage({UID: committed[UID]}, {})
    assert verifier.fleet_gate_failures(coverage, (UID,), "gated") == [f"live alert rule {UID} is absent from Grafana"]

    # Disable: removing the UID from the selector takes it out of the import set.
    monkeypatch.setitem(verifier.load_gated_uids.__globals__, "GATE_FILE", disabled)
    assert UID not in verifier.load_gated_uids(committed)
    assert verifier.fleet_gate_failures(coverage, (), "gated") == []


def test_switch_pauses_and_resumes_the_rule(verifier):
    subject = rule()
    paused = dict(subject, isPaused=True)
    live_paused = dict(subject, isPaused=True)
    # Disable: isPaused true matches a paused live rule and Grafana stops evaluating it.
    assert verifier.mismatched_definition_keys(live_paused, paused) == []
    # Enable: the default false rule cannot match a paused live rule.
    assert verifier.mismatched_definition_keys(live_paused, subject) == ["isPaused"]
    assert verifier.mismatched_definition_keys(dict(subject), subject) == []


def test_development_import_skips_the_production_only_datasource(verifier):
    # The gmp-cloud-run shadow datasource is a production overlay, so the
    # automatic development import must not install this page.
    assert UID in verifier.PRODUCTION_ONLY_IMPORT_UIDS
    assert UID in verifier.load_live_stt_import_rules(production=True)
    assert UID not in verifier.load_live_stt_import_rules(production=False)
