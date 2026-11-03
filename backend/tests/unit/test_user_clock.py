from unittest.mock import MagicMock

import pytest

from utils import user_clock
from utils.model_text import DisplayClock

HCM = DisplayClock.from_name('Asia/Ho_Chi_Minh')


@pytest.fixture
def stored_zone(monkeypatch):
    lookup = MagicMock(return_value='Asia/Ho_Chi_Minh')
    monkeypatch.setattr(user_clock.notification_db, 'get_user_time_zone', lookup)
    return lookup


def test_turn_zone_wins_without_a_stored_lookup(stored_zone):
    assert user_clock.clock_for_turn({'user_timezone': 'Asia/Ho_Chi_Minh'}, 'uid') == HCM
    stored_zone.assert_not_called()


def test_turn_without_zone_reads_the_stored_zone(stored_zone):
    assert user_clock.clock_for_turn({}, 'uid') == HCM
    stored_zone.assert_called_once_with('uid')


def test_turn_without_zone_or_uid_is_utc(stored_zone):
    assert user_clock.clock_for_turn({}, None) == DisplayClock.utc()
    stored_zone.assert_not_called()


def test_failed_lookup_falls_back_to_labelled_utc(monkeypatch):
    monkeypatch.setattr(user_clock.notification_db, 'get_user_time_zone', MagicMock(side_effect=RuntimeError('down')))
    assert user_clock.clock_for_uid('uid') == DisplayClock.utc()


def test_config_reads_the_runnable_config(stored_zone):
    assert user_clock.clock_for_config({'configurable': {'user_timezone': 'Asia/Ho_Chi_Minh'}}) == HCM
    assert user_clock.clock_for_config(None) == DisplayClock.utc()
