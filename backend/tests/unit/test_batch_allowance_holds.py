"""The generation changes only with plan authority or the usage period."""

from datetime import datetime, timezone

import pytest

from utils.batch_pipeline.allowance_hold import enabled, generation


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def test_usage_counter_changes_do_not_reoffer_a_generation_but_plan_and_month_do():
    start = stamp('2026-11-14')
    user = {'subscription': {'plan': 'basic', 'status': 'active'}}
    first = generation(user, start)
    assert generation({**user, 'usage': 0, 'display_name': 'unrelated'}, start + 3600) == first
    assert generation({'subscription': {'plan': 'unlimited', 'status': 'active'}}, start) != first
    assert generation(user, stamp('2026-12-01')) != first


def test_subscription_expiry_changes_generation_without_a_writer():
    now = stamp('2026-11-14')
    user = {'subscription': {'plan': 'plus', 'current_period_end': now + 60}}
    assert generation(user, now) != generation(user, now + 61)


@pytest.mark.parametrize(
    'value,expected', [(None, True), ('on', True), ('OFF', False), (' off ', False), ('false', True)]
)
def test_switch_is_on_unless_explicitly_off(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', value)
    assert enabled() is expected
