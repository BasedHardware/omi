"""Hermetic Modulate modelled-line tests: measured Prometheus volume × the
committed, dated rate-card price. No network, no credentials, no account
reads. The Modulate ORG key must never be read by this line (no API exists)."""

from decimal import Decimal
import importlib.util
import json
import pathlib

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "finops"


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, FINOPS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mm(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    monkeypatch.delenv("FINOPS_MODULATE_ORG_KEY", raising=False)
    module = load("pull_modulate_modelled")
    # point the committed card at a fixture copy so a future v2 edit cannot
    # silently re-price this test's expectations
    card = json.loads((FINOPS.parents[1] / "config" / "rate_card_v2.json").read_text())
    fixture_card = tmp_path / "rate_card_v2.json"
    fixture_card.write_text(json.dumps(card))
    monkeypatch.setattr(module, "RATE_CARD", fixture_card)
    return module


def prom_artifact(tmp_path, result):
    (tmp_path / "prom_stt_7d.json").write_text(json.dumps({"daily": {"d_live_stt_audio_seconds": {"result": result}}}))


def test_committed_price_is_the_dated_rate_card_entry(mm):
    price = mm.price_from_card(json.loads(mm.RATE_CARD.read_text()))
    # rate card v2, committed 2026-10-18 @ f6a358902db: $0.06/hour
    # (platform.modulate.ai Multilingual Transcription streaming; 100 credits = $1)
    assert price["price_usd_per_hour"] == "0.060000000"
    assert price["price_as_of"] == "2026-10-18"
    assert "modulate" in price["price_source"].lower()


@pytest.mark.parametrize(
    "card",
    [
        {},
        {"transcription": {}},
        {"transcription": {"modulate": {}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": 0, "status": "card", "source": "s"}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": "60000", "status": "card", "source": "s"}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": 60000, "status": "provisional", "source": "s"}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": 60000, "status": "card"}}},
    ],
)
def test_price_rejects_anything_not_a_committed_card(mm, card):
    with pytest.raises(mm.ModelledError):
        mm.price_from_card(card)


def test_seconds_take_only_modulate_provider_and_map_bucket_to_prior_day(mm, tmp_path):
    raw = json.loads((FIXTURES / "prom_live_stt_audio_seconds.json").read_text())
    prom = {"daily": {"d_live_stt_audio_seconds": {"result": raw}}}
    seconds = mm.modulate_seconds(prom, "2026-10-20", "2026-10-21")
    assert seconds == {"2026-10-20": Decimal("36000"), "2026-10-21": Decimal("7200")}


def test_modelled_rows_are_seconds_times_committed_price(mm):
    rows = mm.modelled_rows({"2026-10-20": Decimal("36000")}, mm.price_from_card(json.loads(mm.RATE_CARD.read_text())))
    assert rows == [{"date": "2026-10-20", "audio_seconds": "36000.000000000", "usd": "0.600000000"}]


def test_main_writes_ready_artifact_marked_modelled(mm, tmp_path, capsys, monkeypatch):
    prom_artifact(tmp_path, json.loads((FIXTURES / "prom_live_stt_audio_seconds.json").read_text()))
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["pull_modulate_modelled.py", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)],
    )
    mm.main()
    artifact = json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text())
    assert artifact["status"] == "ready"
    assert artifact["method"] == "modelled"
    assert artifact["price_usd_per_hour"] == "0.060000000"
    assert artifact["price_as_of"] == "2026-10-18"
    assert {r["date"]: r["usd"] for r in artifact["rows"]} == {
        "2026-10-20": "0.600000000",
        "2026-10-21": "0.120000000",
    }
    err = capsys.readouterr().err
    assert "0.720000000" in err  # parsed aggregates only


def test_main_skips_when_series_missing_and_never_guesses(mm, tmp_path, monkeypatch):
    prom_artifact(tmp_path, {"status": "success", "data": {"result": []}})
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["pull_modulate_modelled.py", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)],
    )
    mm.main()
    assert json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text()) == {
        "status": "skipped",
        "reason": "prometheus_series_missing",
    }


def test_main_skips_without_prom_artifact_or_card(mm, tmp_path, monkeypatch):
    import sys

    def run_main():
        monkeypatch.setattr(
            sys,
            "argv",
            ["pull_modulate_modelled.py", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)],
        )
        mm.main()

    run_main()
    assert (
        json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text())["reason"]
        == "prometheus_artifact_unavailable"
    )

    (tmp_path / "stt_modulate_modelled_daily.json").unlink()
    monkeypatch.setattr(mm, "RATE_CARD", tmp_path / "absent.json")
    run_main()
    assert json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text())["reason"] == "rate_card_unavailable"


def test_modulate_line_never_reads_the_org_key():
    """The ORG key binding exists for a future API; this line must not use it."""
    source = (FINOPS / "pull_modulate_modelled.py").read_text()
    assert "FINOPS_MODULATE_ORG_KEY" not in source
    assert "modulate_org" not in source
    assert "modulate-developer-apis" not in source
