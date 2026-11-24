"""Daily peak Home row counts stay uid-free and only move upward within a day."""

from prometheus_client import CollectorRegistry, Counter

from utils import home_rows_metric
from utils.home_rows_metric import observe_home_rows, reset_home_rows_for_tests


def _sample(registry: CollectorRegistry, name: str) -> float:
    for family in registry.collect():
        for sample in family.samples:
            if sample.name == name:
                return sample.value
    raise AssertionError(name)


def test_first_report_counts_an_empty_home(monkeypatch):
    registry = CollectorRegistry()
    total = Counter('omi_home_rows_user_day_sum', 'sum', registry=registry)
    days = Counter('omi_home_rows_user_day_count', 'days', registry=registry)
    monkeypatch.setattr(home_rows_metric, 'OMI_HOME_ROWS_USER_DAY_SUM', total)
    monkeypatch.setattr(home_rows_metric, 'OMI_HOME_ROWS_USER_DAY_COUNT', days)
    reset_home_rows_for_tests()

    assert observe_home_rows('u1', 0)
    assert observe_home_rows('u1', 5)
    assert not observe_home_rows('u1', 3)
    assert not observe_home_rows('', 1)
    assert not observe_home_rows('u1', True)  # type: ignore[arg-type]
    assert not observe_home_rows('u1', 501)

    assert _sample(registry, 'omi_home_rows_user_day_count_total') == 1
    assert _sample(registry, 'omi_home_rows_user_day_sum_total') == 5
    rendered = generate_text(registry)
    assert 'u1' not in rendered


def generate_text(registry: CollectorRegistry) -> str:
    from prometheus_client import generate_latest

    return generate_latest(registry).decode()
