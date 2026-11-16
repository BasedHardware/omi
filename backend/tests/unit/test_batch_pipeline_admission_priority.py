from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from config.batch_pipeline import Priority
from utils.batch_pipeline.admission_priority import unit_priority
from tests.unit.test_batch_language_eligibility import defaults  # synthetic consent/funding fixture

FLAG = 'BATCH_PIPELINE_UNIT_CAPTURE_PRIORITY_ENABLED'


def unit(start=100, duration=500, **kwargs):
    return SimpleNamespace(capture_at=start, duration_seconds=duration, **kwargs)


def count(lane, reason):
    return (
        REGISTRY.get_sample_value('omi_batch_pipeline_priority_demotions_total', {'lane': lane, 'reason': reason}) or 0
    )


def test_recent_sync_unit_promoted_from_own_capture_end(monkeypatch):
    monkeypatch.setenv(FLAG, 'true')
    # Start age is 900s, end age 400s: a request seed based on an old sibling
    # must not determine this unit's scheduling urgency.
    assert unit_priority(Priority.RECENT, 'fresh', unit(), now=1000) == Priority.FRESH


@pytest.mark.parametrize('value', [None, 'false', 'off', '0', 'invalid'])
def test_disabled_preserves_seed(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(FLAG, raising=False)
    else:
        monkeypatch.setenv(FLAG, value)
    assert unit_priority(Priority.RECENT, 'fresh', unit(), now=1000) == Priority.RECENT


@pytest.mark.parametrize('seed', list(Priority))
@pytest.mark.parametrize('lane', ['fresh', 'backfill'])
@pytest.mark.parametrize('start', [100, -1000000])
def test_min_never_demotes(monkeypatch, seed, lane, start):
    monkeypatch.setenv(FLAG, 'true')
    assert unit_priority(seed, lane, unit(start), now=1000) <= seed


def test_divergence_counter(monkeypatch):
    monkeypatch.setenv(FLAG, 'true')
    before = count('fresh', 'seed_effective_divergence')
    unit_priority(Priority.RECENT, 'fresh', unit(), now=1000)
    assert count('fresh', 'seed_effective_divergence') == before + 1


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_unbound_backfill_gate_preserved_and_observable(monkeypatch, enabled):
    monkeypatch.setenv(FLAG, enabled)
    before = count('backfill', 'fresh_capture_not_fresh')
    assert unit_priority(Priority.RECENT, 'backfill', unit(), now=1000) == Priority.RECENT
    assert count('backfill', 'fresh_capture_not_fresh') == before + 1


def test_stored_capture_clock_and_recovery_trust(monkeypatch):
    monkeypatch.setenv(FLAG, 'true')
    assert unit_priority(Priority.RECENT, 'fresh', unit(stored_capture_at=-10000), now=1000) == Priority.RECENT
    assert unit_priority(Priority.RECENT, 'fresh', unit(recovery_id='synthetic'), now=1000) == Priority.RECENT


@pytest.mark.parametrize('start,duration', [(float('nan'), 500), (None, 500), (100, -1)])
def test_invalid_clock_keeps_seed(monkeypatch, start, duration):
    monkeypatch.setenv(FLAG, 'true')
    assert unit_priority(Priority.RECENT, 'fresh', unit(start, duration), now=1000) == Priority.RECENT


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,expected', [('true', Priority.FRESH), ('false', Priority.RECENT)])
async def test_sync_intake_writes_effective_unit_priority(monkeypatch, enabled, expected):
    from tests.unit.test_batch_language_eligibility import upload
    from utils.batch_pipeline import intake

    monkeypatch.setenv(FLAG, enabled)
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ADMISSION_SAMPLE_ENABLED', 'false')
    monkeypatch.setattr(intake, 'priority_for', lambda *_: Priority.RECENT)
    monkeypatch.setattr(intake.time, 'time', lambda: 500)
    _, staged, _ = await upload(monkeypatch, user_language='en')
    assert len(staged) == 1
    assert staged[0].priority == expected
