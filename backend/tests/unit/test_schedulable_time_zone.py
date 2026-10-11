"""Timezone admission: only zones the scheduler can serve get stored.

Validators ran on zoneinfo while every consumer (hour-grouped recipient
queries, day bounds, recap routes) runs on pytz — a zone the host tzdb
knows but pytz does not was accepted, stored, and never scheduled.
is_schedulable_time_zone makes pytz the single authority.
"""

import pytest

from utils.other.timezone import is_schedulable_time_zone


def test_pytz_only_zones_are_rejected():
    # Host tzdb serves these; the pinned pytz build does not.
    for zone in ('Factory', 'localtime'):
        assert is_schedulable_time_zone(zone) is False, zone


def test_real_zones_are_accepted():
    for zone in ('America/New_York', 'UTC', 'Europe/Berlin'):
        assert is_schedulable_time_zone(zone) is True, zone
    # America/Coyhaique arrived in tzdata 2025a; the pinned pytz==2024.1
    # predates it, so admission rejects it until pytz is upgraded — exactly
    # the divergence this change exists to stop.
    assert is_schedulable_time_zone('America/Coyhaique') is False


def test_garbage_and_empty_are_rejected():
    for zone in ('Mars/Olympus', '', '  '):
        assert is_schedulable_time_zone(zone) is False, zone
    assert is_schedulable_time_zone(None) is False
    assert is_schedulable_time_zone(123) is False
