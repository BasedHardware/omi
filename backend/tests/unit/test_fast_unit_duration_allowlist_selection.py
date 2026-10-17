"""The duration exemption list must not widen backend unit selection."""

from scripts import select_backend_unit_tests as selector

_ALERT_ROUTE_TEST = 'tests/unit/test_verify_pusher_live_alert_route.py'


def test_duration_allowlist_is_not_a_backend_selection_source() -> None:
    assert selector.is_selectable_backend_path('backend/tests/fast_unit_duration_allowlist.txt') is False
    selected, reason = selector.tests_for_changed_paths(
        ['backend/tests/fast_unit_duration_allowlist.txt'],
        [_ALERT_ROUTE_TEST],
    )
    assert selected == []
    assert reason == 'no backend files changed'


def test_duration_allowlist_keeps_an_alert_route_change_narrow() -> None:
    selected, reason = selector.tests_for_changed_paths(
        [
            'backend/scripts/verify_pusher_live_alert_route.py',
            'backend/tests/fast_unit_duration_allowlist.txt',
        ],
        [_ALERT_ROUTE_TEST],
    )
    assert selected == [_ALERT_ROUTE_TEST]
    assert reason == 'selected backend unit tests from changed paths and workflow contracts'
