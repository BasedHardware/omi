"""Which vendor_held jobs the maintenance held sweep re-wakes (lost deferred wakes, 2026-11-27)."""

import math

import pytest

from database.outbox_provider_stt import REWAKE_AFTER_SECONDS, _held_overdue

NOW = 1_000_000.0


def held(redrive_at):
    return {'state': 'vendor_held', 'vendor_hold': {'redrive_at': redrive_at}}


@pytest.mark.parametrize(
    'job, overdue',
    [
        (held(NOW - REWAKE_AFTER_SECONDS), True),
        (held(NOW - 14 * 86400), True),
        (held(NOW - REWAKE_AFTER_SECONDS + 1), False),  # its queued wake may still fire
        (held(NOW + 300), False),
        (held(None), True),  # a malformed hold cannot prove a live wake
        (held(math.nan), True),
        (held(True), True),
        ({'state': 'vendor_held'}, True),
        ({**held(NOW - 86400), 'state': 'provider_pending'}, False),
        ({**held(NOW - 86400), 'state': 'provider_running'}, False),
    ],
)
def test_only_overdue_holds_are_rewoken(job, overdue):
    assert _held_overdue(job, NOW) is overdue
