"""Demand admission must prefer vendors whenever evidence is ambiguous."""

from types import SimpleNamespace

import pytest

from config.live_demand import language_qualified, resolve_live_demand
from routers.listen.demand_routing import DemandPolicy
from routers.listen.lane_meter import LiveLaneMeter
from utils.stt.live_metrics import DEMAND_LANE_SECONDS, DEMAND_SWITCHES


def test_dark_defaults_and_invalid_config(monkeypatch):
    for key in ('STT_LIVE_DEMAND_ENABLED', 'STT_LIVE_DEMAND_PERCENT', 'STT_LIVE_DEMAND_UID_ALLOWLIST'):
        monkeypatch.delenv(key, raising=False)
    assert not resolve_live_demand().admits('user')
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_UID_ALLOWLIST', ' user, second ')
    assert resolve_live_demand().admits('user')
    assert not resolve_live_demand().admits('other')
    for invalid in ('nan', 'inf', '-1', '101', 'invalid'):
        monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', invalid)
        assert not resolve_live_demand().admits('user')


def test_stable_uid_allocation_and_global_kill(monkeypatch):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '5')
    first = [resolve_live_demand().admits(str(i)) for i in range(1000)]
    assert first == [resolve_live_demand().admits(str(i)) for i in range(1000)]
    assert 20 < sum(first) < 80
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'false')
    assert not any(resolve_live_demand().admits(str(i)) for i in range(1000))


@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'foreground': False},
        {'foreground': 0, 'transcript_visible': False},
        {'foreground': False, 'transcript_visible': True},
    ],
)
def test_unknown_old_and_mixed_reports_retain_vendor(payload):
    policy = DemandPolicy()
    policy.observe({'foreground': False, 'transcript_visible': False})
    policy.observe(payload)
    assert policy.decide(enabled=True, visible=False, consumer=False) == 'vendor'


def test_hysteresis_fast_flips_and_consumer_priority():
    now = [0.0]
    policy = DemandPolicy(lambda: now[0])
    assert policy.decide(enabled=True, visible=False, consumer=False) == 'vendor'
    policy.observe({'foreground': True, 'transcript_visible': False})
    assert policy.decide(enabled=True, visible=False, consumer=False) == 'parakeet'
    assert not policy.ready('vendor', 'parakeet', 30)
    now[0] = 30
    assert policy.ready('vendor', 'parakeet', 30)
    policy.switched()
    policy.observe({'foreground': True, 'transcript_visible': True})
    assert policy.decide(enabled=True, visible=True, consumer=False) == 'vendor'
    assert policy.ready('parakeet', 'vendor', 30)
    policy.observe({'foreground': True, 'transcript_visible': False})
    now[0] = 31
    assert not policy.ready('vendor', 'parakeet', 30)
    for consumer in (True, None):
        assert policy.decide(enabled=True, visible=False, consumer=consumer) == 'vendor'
    assert policy.decide(enabled=True, visible=True, consumer=False) == 'vendor'
    assert policy.decide(enabled=False, visible=False, consumer=False) == 'vendor'
    policy.fallback = True
    assert policy.decide(enabled=True, visible=False, consumer=False) == 'vendor'


@pytest.mark.parametrize(
    'declared,multi,expected,qualified',
    [
        ('en', False, ('en',), True),
        ('en-US', False, ('en',), True),
        ('en', True, ('en',), False),
        ('pt', False, ('en',), False),
        ('auto', False, ('en',), False),
        ('multi', False, ('en',), False),
        ('en', False, ('en', 'pt'), False),
    ],
)
def test_declared_english_only(declared, multi, expected, qualified):
    host = SimpleNamespace(
        request=SimpleNamespace(language=declared),
        language='en',
        multi_lang_enabled=multi,
        language_profile=SimpleNamespace(primary='en', expected=expected, multi=multi),
    )
    assert language_qualified(host) == qualified


def test_lane_meter_counts_flag_off_and_switches_once():
    now = [0.0]
    meter = LiveLaneMeter(lambda: now[0])
    vendor = DEMAND_LANE_SECONDS.labels(lane='vendor', reason='baseline', demand_cohort='ineligible')
    cheap = DEMAND_LANE_SECONDS.labels(lane='parakeet', reason='hidden', demand_cohort='ineligible')
    switches = DEMAND_SWITCHES.labels(from_lane='vendor', to_lane='parakeet', reason='hidden')
    before_switches = switches._value.get()
    before_vendor, before_cheap = vendor._value.get(), cheap._value.get()
    meter.transition('soniox')
    now[0] = 5
    meter.transition('parakeet', reason='hidden')
    now[0] = 12
    meter.close()
    meter.close()
    assert vendor._value.get() - before_vendor == 5
    assert cheap._value.get() - before_cheap == 7
    assert switches._value.get() - before_switches == 1
