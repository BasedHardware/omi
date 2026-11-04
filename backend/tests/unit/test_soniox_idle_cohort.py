"""Uid-hash treatment cohort for the Soniox idle close."""

import pytest

from config import soniox_idle as idle_config
from config.soniox_idle import cohort_percent, idle_settings_for
from utils.stt.soniox_idle import SonioxIdleBudget


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        'SONIOX_IDLE_CLOSE_SECONDS',
        'SONIOX_IDLE_REARM_SECONDS',
        'SONIOX_IDLE_MAX_CLOSES_PER_HOUR',
        'SONIOX_IDLE_COHORT_PERCENT',
        'SONIOX_IDLE_COHORT_CLOSE_SECONDS',
        'SONIOX_IDLE_COHORT_REARM_SECONDS',
        'SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR',
    ):
        monkeypatch.delenv(name, raising=False)


def in_cohort_uid(percent):
    """A uid whose bucket lands below percent (deterministic per uid)."""
    from config.policy.batch import cohort_bucket

    for i in range(10000):
        uid = f'uid-{i}'
        if cohort_bucket(uid, idle_config.COHORT_SALT, bits=64) < percent:
            return uid
    raise AssertionError('no cohort uid found')


def test_cohort_percent_parsing(monkeypatch):
    assert cohort_percent() == 0.0
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '25')
    assert cohort_percent() == 25.0
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '250')
    assert cohort_percent() == 100.0
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', 'off')
    assert cohort_percent() == 0.0
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', 'not-a-number')
    assert cohort_percent() == 0.0


def test_defaults_are_control(monkeypatch):
    settings = idle_settings_for('user-1')
    assert settings.arm == 'control'
    assert settings.close_seconds == idle_config.DEFAULT_IDLE_CLOSE_SECONDS
    assert settings.rearm_seconds == idle_config.DEFAULT_REARM_SECONDS
    assert settings.max_closes_per_hour == idle_config.DEFAULT_MAX_CLOSES_PER_HOUR


def test_overrides_without_percent_are_control(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR', '30')
    assert idle_settings_for('user-1').arm == 'control'


def test_percent_without_overrides_is_control(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    assert idle_settings_for('user-1').arm == 'control'


def test_treatment_overrides_apply_inside_cohort(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR', '30')
    settings = idle_settings_for('user-1')
    assert settings.arm == 'treatment'
    assert settings.close_seconds == 30.0
    assert settings.max_closes_per_hour == 30
    assert settings.rearm_seconds == idle_config.DEFAULT_REARM_SECONDS


def test_treatment_close_floor_and_fallbacks(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '2')  # inside the VAD hangover
    settings = idle_settings_for('user-1')
    assert settings.close_seconds == idle_config.MIN_COHORT_CLOSE_SECONDS
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', 'off')  # off = no override
    assert idle_settings_for('user-1').close_seconds == idle_config.DEFAULT_IDLE_CLOSE_SECONDS


def test_speech_gate_cohort_goes_below_the_global_floors(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '10')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_REARM_SECONDS', '2')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR', '120')
    settings = idle_settings_for('user-1')
    assert settings.arm == 'treatment'
    assert settings.close_seconds == 10.0 < idle_config.MIN_IDLE_CLOSE_SECONDS
    assert settings.rearm_seconds == 2.0 < idle_config.MIN_REARM_SECONDS
    assert settings.max_closes_per_hour == 120


def test_speech_gate_floors_stay_past_the_hangover_and_bound_flapping(monkeypatch):
    assert idle_config.MIN_COHORT_CLOSE_SECONDS > idle_config.VAD_HANGOVER_SECONDS
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_REARM_SECONDS', '0.1')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR', '100000')
    settings = idle_settings_for('user-1')
    assert settings.rearm_seconds == idle_config.MIN_COHORT_REARM_SECONDS
    assert settings.max_closes_per_hour == idle_config.MAX_COHORT_CLOSES_PER_HOUR


def test_global_knobs_keep_their_floors(monkeypatch):
    # The global values reach every session without an arm comparison.
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '10')
    monkeypatch.setenv('SONIOX_IDLE_REARM_SECONDS', '2')
    settings = idle_settings_for('user-1')
    assert settings.arm == 'control'
    assert settings.close_seconds == idle_config.MIN_IDLE_CLOSE_SECONDS
    assert settings.rearm_seconds == idle_config.MIN_REARM_SECONDS


def test_prod_overlay_runs_the_speech_gate_dark():
    import pathlib

    import yaml

    chart = pathlib.Path(__file__).resolve().parents[2] / 'charts/backend-listen/prod_omi_backend_listen_values.yaml'
    env = {}

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('name'), str) and node['name'].startswith('SONIOX_IDLE_COHORT_') and 'value' in node:
                env[node['name']] = node['value']
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(yaml.safe_load(chart.read_text()))
    assert env['SONIOX_IDLE_COHORT_PERCENT'] == '0'  # the lead ramps it; 0 is the kill switch
    assert float(env['SONIOX_IDLE_COHORT_CLOSE_SECONDS']) >= idle_config.MIN_COHORT_CLOSE_SECONDS
    assert float(env['SONIOX_IDLE_COHORT_CLOSE_SECONDS']) < idle_config.MIN_IDLE_CLOSE_SECONDS
    assert float(env['SONIOX_IDLE_COHORT_REARM_SECONDS']) >= idle_config.MIN_COHORT_REARM_SECONDS
    assert 0 < int(env['SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR']) <= idle_config.MAX_COHORT_CLOSES_PER_HOUR


def test_out_of_cohort_uid_stays_control(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '10')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    uid = in_cohort_uid(10.0)
    assert idle_settings_for(uid).arm == 'treatment'
    # The same uid is deterministically assigned, and a tiny percent keeps
    # almost everyone else control: a different uid from the same scan pool
    # stays control at 10 percent unless it also buckets below it.
    from config.policy.batch import cohort_bucket

    other = next(
        f'uid-{i}' for i in range(10000) if cohort_bucket(f'uid-{i}', idle_config.COHORT_SALT, bits=64) >= 10.0
    )
    assert idle_settings_for(other).arm == 'control'
    assert idle_settings_for(None).arm == 'control'


def test_global_kill_switch_disables_cohort_too(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '0')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    settings = idle_settings_for('user-1')
    assert settings.close_seconds == 0.0
    assert settings.arm == 'control'


def test_budget_resolves_cohort_once(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR', '2')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_REARM_SECONDS', '7')
    budget = SonioxIdleBudget(uid='user-1')
    assert budget.arm == 'treatment'
    assert budget.close_seconds == 30.0
    assert budget.max_closes_per_hour == 2
    assert budget.rearm_seconds == 7.0
    # The resolved cap governs reserve_close for the whole session.
    assert budget.reserve_close(0.0)
    assert budget.reserve_close(1.0)
    assert not budget.reserve_close(2.0)


def test_budget_never_consults_identity_while_cohort_off(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')  # overrides alone: not armed
    calls = []

    def provider():
        calls.append('user-1')
        return 'user-1'

    budget = SonioxIdleBudget(uid_provider=provider)
    assert budget.arm == 'control'
    assert budget.close_seconds == idle_config.DEFAULT_IDLE_CLOSE_SECONDS
    assert budget.reserve_close(0.0)
    assert calls == []


def test_budget_consults_identity_lazily_once_armed(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    calls = []

    def provider():
        calls.append('user-1')
        return 'user-1'

    budget = SonioxIdleBudget(uid_provider=provider)
    assert budget.arm == 'treatment'
    assert budget.close_seconds == 30.0
    assert budget.arm == 'treatment'  # resolved once, provider not re-consulted
    assert calls == ['user-1']


def test_budget_without_identity_resolves_control(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')

    def provider():
        raise AttributeError('uid')

    budget = SonioxIdleBudget(uid_provider=provider)
    assert budget.arm == 'control'
    assert budget.close_seconds == idle_config.DEFAULT_IDLE_CLOSE_SECONDS


def test_cohort_metrics_pin_both_arms():
    from utils.stt.live_metrics import SONIOX_IDLE_COHORT_ARMS, soniox_idle_metrics

    metrics = soniox_idle_metrics()
    for arm in SONIOX_IDLE_COHORT_ARMS:
        assert metrics.cohort_closes.labels(arm=arm)
        assert metrics.cohort_reopens.labels(arm=arm)
        assert metrics.cohort_latency.labels(arm=arm)
        assert metrics.cohort_failures.labels(arm=arm)
        assert metrics.cohort_avoided.labels(arm=arm)
        for trigger in ('vad', 'no_frames'):
            assert metrics.cohort_closes_by_trigger.labels(arm=arm, trigger=trigger)
