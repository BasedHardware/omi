"""Historical tier (T1+) age rule, trigger table and kill-switch defaults."""

from datetime import datetime, timedelta, timezone

import pytest

from config import historical_tier
from utils.conversations import sync_hold_completion
from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger, RelevancePolicy
from utils.episodes import member_notes

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
HOURS_72 = 72 * 3600


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        historical_tier.TIER_ENABLED_ENV,
        historical_tier.OPEN_ENABLED_ENV,
        historical_tier.VECTOR_ENABLED_ENV,
        'ENRICHMENT_MAX_AGE_HOURS',
        historical_tier.GLOBAL_DAILY_LIMIT_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def test_boundary_matches_the_enrichment_age_gate_exactly():
    # The 72 h enrichment gate parks rows strictly older than 72 h, so the tier does too.
    assert not historical_tier.applies(NOW - timedelta(seconds=HOURS_72), 'device_bound', NOW)
    assert historical_tier.applies(NOW - timedelta(seconds=HOURS_72 + 1), 'device_bound', NOW)
    assert not historical_tier.applies(NOW - timedelta(hours=1), 'legacy', NOW)


@pytest.mark.parametrize('trust', ['untrusted', None])
def test_untrusted_or_missing_clock_keeps_full_processing(trust):
    old = NOW - timedelta(days=20)
    if trust == 'untrusted':
        assert not historical_tier.applies(old, trust, NOW)
    else:
        assert historical_tier.applies(old, trust, NOW)
    assert not historical_tier.applies(None, 'legacy', NOW)


def test_epoch_seconds_and_naive_datetimes_are_utc():
    started = (NOW - timedelta(days=4)).replace(tzinfo=None)
    assert historical_tier.applies(started, 'legacy', NOW.timestamp())
    assert historical_tier.applies((NOW - timedelta(days=4)).timestamp(), 'legacy', NOW)


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [('', HOURS_72), ('96', 96 * 3600), ('1.5', 5400), ('x', HOURS_72), ('-4', HOURS_72), ('inf', HOURS_72)],
)
def test_the_tier_boundary_is_the_enrichment_age_gate(monkeypatch, raw, expected):
    from utils.enrichment import age_gate

    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', raw)
    assert historical_tier.min_age_seconds() == expected == age_gate.max_age_seconds()


def test_a_moved_gate_moves_the_tier_with_it(monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '96')
    assert not historical_tier.applies(NOW - timedelta(hours=80), 'legacy', NOW)
    assert historical_tier.applies(NOW - timedelta(hours=97), 'legacy', NOW)


def test_gate_off_means_no_tier(monkeypatch):
    # ENRICHMENT_MAX_AGE_HOURS=0 restores automatic summaries for old rows, so nothing is historical.
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    assert not historical_tier.applies(NOW - timedelta(days=30), 'legacy', NOW)


def test_switches_are_on_unless_set_off(monkeypatch):
    assert historical_tier.tier_enabled() and historical_tier.open_enabled() and historical_tier.vector_enabled()
    monkeypatch.setenv(historical_tier.TIER_ENABLED_ENV, 'false')
    monkeypatch.setenv(historical_tier.OPEN_ENABLED_ENV, 'off')
    monkeypatch.setenv(historical_tier.VECTOR_ENABLED_ENV, '0')
    assert not historical_tier.tier_enabled()
    assert not historical_tier.open_enabled()
    assert not historical_tier.vector_enabled()


@pytest.mark.parametrize(('raw', 'expected'), [('', 10000), ('0', 0), ('-3', 0), ('250', 250), ('many', 10000)])
def test_global_daily_limit(monkeypatch, raw, expected):
    monkeypatch.setenv(historical_tier.GLOBAL_DAILY_LIMIT_ENV, raw)
    assert historical_tier.global_daily_limit() == expected


def test_is_historical_reads_dicts_and_models():
    assert historical_tier.is_historical({'processing_tier': 'historical'})
    assert not historical_tier.is_historical({'processing_tier': None})
    assert not historical_tier.is_historical(object())


def test_historical_open_trigger_is_an_explicit_regeneration_that_keeps_the_row():
    mode = PROCESSING_MODES[ProcessingTrigger.HISTORICAL_OPEN]
    assert (mode.run_now, mode.reprocess, mode.relevance) == (True, True, RelevancePolicy.KEEP)
    # An open-time summary settles an outstanding sync hold and is never a live-member wait.
    assert ProcessingTrigger.HISTORICAL_OPEN in sync_hold_completion.EXPLICIT
    assert ProcessingTrigger.HISTORICAL_OPEN in member_notes.EXPLICIT
    assert set(PROCESSING_MODES) == set(ProcessingTrigger)
