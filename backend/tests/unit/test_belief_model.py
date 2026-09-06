from datetime import datetime, timedelta, timezone

import pytest

from utils.memory.belief_model import (
    CURRENT_BAND_MIN,
    FADING_BAND_MIN,
    HALF_LIFE_DAYS_BY_CLASS,
    CurrencyBand,
    belief_model_enabled,
    belief_view,
    compute_currency,
    currency_band,
    derive_half_life_days,
    resolve_last_evidenced_at,
    passes_proactive_bar,
)

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
CAPTURED = NOW - timedelta(days=30)


def test_currency_is_one_when_half_life_is_null():
    assert (
        compute_currency(
            half_life_days=None,
            last_evidenced_at=CAPTURED,
            now=NOW,
        )
        == 1.0
    )


def test_currency_is_half_after_one_half_life():
    value = compute_currency(
        half_life_days=30,
        last_evidenced_at=CAPTURED,
        now=NOW,
    )
    assert value == pytest.approx(0.5)


def test_currency_is_quarter_after_two_half_lives():
    value = compute_currency(
        half_life_days=15,
        last_evidenced_at=CAPTURED,
        now=NOW,
    )
    assert value == pytest.approx(0.25)


def test_re_evidence_resets_the_clock():
    stale = compute_currency(
        half_life_days=30,
        last_evidenced_at=CAPTURED,
        now=NOW,
    )
    fresh = compute_currency(
        half_life_days=30,
        last_evidenced_at=NOW - timedelta(hours=1),
        now=NOW,
    )
    assert stale == pytest.approx(0.5)
    assert fresh == pytest.approx(1.0, rel=1e-3)


def test_named_date_is_current_until_valid_to_then_history():
    valid_to = NOW - timedelta(seconds=1)
    assert (
        compute_currency(
            half_life_days=30,
            last_evidenced_at=CAPTURED,
            now=NOW - timedelta(days=1),
            valid_to=valid_to,
        )
        == 1.0
    )
    assert (
        compute_currency(
            half_life_days=30,
            last_evidenced_at=CAPTURED,
            now=NOW,
            valid_to=valid_to,
        )
        == 0.0
    )


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_currency(
            half_life_days=None,
            last_evidenced_at=datetime(2026, 9, 2, 12, 0),
            now=NOW,
        )


def test_bands():
    assert currency_band(1.0) is CurrencyBand.current
    assert currency_band(CURRENT_BAND_MIN + 1e-9) is CurrencyBand.current
    assert currency_band(CURRENT_BAND_MIN) is CurrencyBand.fading
    assert currency_band(FADING_BAND_MIN) is CurrencyBand.fading
    assert currency_band(FADING_BAND_MIN - 1e-9) is CurrencyBand.history
    assert currency_band(0.0) is CurrencyBand.history


def test_stored_numeric_half_life_wins():
    assert (
        derive_half_life_days(
            stored_half_life_days=7,
            user_asserted=True,
            belief_class="identity",
        )
        == 7
    )


def test_belief_class_identity_is_durable_without_stored_half_life():
    assert derive_half_life_days(belief_class="identity") is None


def test_legacy_user_asserted_does_not_decay():
    assert derive_half_life_days(user_asserted=True, tier="short_term") is None


def test_legacy_priors_from_class_category_tier():
    assert derive_half_life_days(belief_class="identity") is None
    assert derive_half_life_days(belief_class="preference") == 180
    assert derive_half_life_days(belief_class="state") == 30
    assert derive_half_life_days(belief_class="episodic") == 7
    assert derive_half_life_days(belief_class="meta_residue") == 1
    assert derive_half_life_days(belief_class="meta_standing") is None
    assert derive_half_life_days(kind="document") is None
    assert derive_half_life_days(tier="short_term") == 30
    assert derive_half_life_days(category="interesting", tier="short_term") == 30
    assert derive_half_life_days(tier="long_term") is None
    assert derive_half_life_days(category="system", tier="long_term") is None
    assert derive_half_life_days(tier="archive") is None


def test_last_evidenced_defaults_to_captured_at():
    assert resolve_last_evidenced_at(captured_at=CAPTURED) == CAPTURED
    corroborated = NOW - timedelta(days=2)
    assert resolve_last_evidenced_at(captured_at=CAPTURED, last_corroborated_at=corroborated) == corroborated


def test_belief_view_legacy_state_is_fading_at_one_half_life():
    view = belief_view(
        captured_at=CAPTURED,
        now=NOW,
        category="system",
        tier="short_term",
    )
    assert view.half_life_days == 30
    assert view.currency == pytest.approx(0.5)
    assert view.band is CurrencyBand.fading
    assert view.as_of == CAPTURED


def test_proactive_bar_requires_current_user_and_not_contradicted():
    current = belief_view(
        captured_at=NOW,
        now=NOW,
        belief_class="identity",
    )
    fading = belief_view(
        captured_at=CAPTURED,
        now=NOW,
        stored_half_life_days=30,
    )
    assert passes_proactive_bar(current, subject_scope="primary_user") is True
    assert passes_proactive_bar(current, subject_scope="third_party") is False
    assert passes_proactive_bar(current, subject_scope="media_screen") is False
    assert passes_proactive_bar(fading, subject_scope="primary_user") is False
    assert passes_proactive_bar(current, subject_scope="primary_user", superseded_by="newer") is False
    assert passes_proactive_bar(current, subject_scope="primary_user", confidence=0.0) is False


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    assert belief_model_enabled() is False
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "false")
    assert belief_model_enabled() is False
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    assert belief_model_enabled() is True


def test_class_priors_match_the_ratified_table():
    assert HALF_LIFE_DAYS_BY_CLASS["identity"] is None
    assert HALF_LIFE_DAYS_BY_CLASS["relationship"] is None
    assert HALF_LIFE_DAYS_BY_CLASS["preference"] == 180
    assert HALF_LIFE_DAYS_BY_CLASS["plan"] == 30
    assert HALF_LIFE_DAYS_BY_CLASS["episodic"] == 7
    assert HALF_LIFE_DAYS_BY_CLASS["meta_residue"] == 1
    assert HALF_LIFE_DAYS_BY_CLASS["meta_standing"] is None


def test_subject_scope_never_defaults_unknown_to_the_user():
    from utils.memory.belief_model import horizon_from_extraction, subject_scope_from_extraction

    assert subject_scope_from_extraction(attribution="user") == "primary_user"
    assert subject_scope_from_extraction(attribution="third_party") == "third_party"
    assert subject_scope_from_extraction(about="the user") == "primary_user"
    assert subject_scope_from_extraction(about="YouTube video") == "third_party"
    assert subject_scope_from_extraction(about="Sarah") == "third_party"
    assert subject_scope_from_extraction() == "third_party"
    assert subject_scope_from_extraction(extracted_scope="media_screen") == "third_party"
    assert subject_scope_from_extraction(about="David", user_name="David Zheng") == "primary_user"
    assert subject_scope_from_extraction(about="david", user_name="David Zheng") == "primary_user"
    assert (
        subject_scope_from_extraction(about="Sam", attribution="third_party", user_name="David Zheng") == "third_party"
    )


def test_horizon_from_extraction_honors_user_asserted_and_overrides():
    from utils.memory.belief_model import horizon_from_extraction

    assert horizon_from_extraction(belief_class="state", user_asserted=True) == ("state", None)
    assert horizon_from_extraction(belief_class="identity") == ("identity", None)
    assert horizon_from_extraction(belief_class="episodic") == ("episodic", 7.0)
    assert horizon_from_extraction(belief_class="plan", half_life_days_override=7) == ("plan", 7)
    assert horizon_from_extraction(belief_class="unknown") == ("state", 30.0)


def test_record_view_reads_category_from_item_audit_bag():
    from types import SimpleNamespace

    from utils.memory.belief_model import belief_view_for_record

    record = SimpleNamespace(
        captured_at=CAPTURED,
        half_life_days=None,
        last_corroborated_at=None,
        valid_to=None,
        user_asserted=False,
        belief_class=None,
        kind="fact",
        category=None,
        promotion={"category": "manual"},
        tier="long_term",
    )
    view = belief_view_for_record(record, now=NOW)
    assert view.half_life_days is None


def test_public_overlay_is_empty_when_flag_off(monkeypatch):
    from types import SimpleNamespace

    from utils.memory.belief_model import public_belief_overlay

    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    record = SimpleNamespace(
        captured_at=CAPTURED,
        half_life_days=30,
        last_corroborated_at=None,
        valid_to=None,
        user_asserted=False,
        belief_class="state",
        kind="fact",
        category=None,
        tier="short_term",
        subject_scope="primary_user",
    )
    assert public_belief_overlay(record, now=NOW) == {}


def test_public_overlay_includes_band_and_as_of_when_flag_on(monkeypatch):
    from types import SimpleNamespace

    from utils.memory.belief_model import CurrencyBand, public_belief_overlay

    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    record = SimpleNamespace(
        captured_at=CAPTURED,
        half_life_days=30,
        last_corroborated_at=None,
        valid_to=None,
        user_asserted=False,
        belief_class="state",
        kind="fact",
        category=None,
        tier="short_term",
        subject_scope="primary_user",
    )
    overlay = public_belief_overlay(record, now=NOW)
    assert overlay["currency_band"] == CurrencyBand.fading.value
    assert overlay["as_of"] == CAPTURED
    assert overlay["half_life_days"] == 30
