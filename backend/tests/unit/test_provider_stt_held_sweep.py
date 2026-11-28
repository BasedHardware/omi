"""Which vendor_held jobs the maintenance held sweep re-wakes (lost deferred wakes, 2026-11-27)."""

import math

import pytest

from config.batch_pipeline_retention import LIFECYCLE_SECONDS
from database.outbox_provider_stt import REWAKE_AFTER_SECONDS, _held_inside_retention, _held_overdue, _held_recoverable
from utils.batch_pipeline.input_retention import STAGING_BUCKET

NOW = 100_000_000.0
STAGED = f'gs://{STAGING_BUCKET}/u/segment.enc'


def held(redrive_at, **fields):
    return {'state': 'vendor_held', 'vendor_hold': {'redrive_at': redrive_at}, **fields}


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


@pytest.mark.parametrize(
    'fields, inside',
    [
        ({'audio_uri': STAGED, 'enqueued_at': NOW - 86400}, True),  # legacy admission: enqueue clock
        ({'audio_uri': STAGED, 'audio_staged_at': NOW - 86400, 'enqueued_at': NOW - 86400}, True),
        # Audio staged before the cutoff is expired even when a newer enqueue time would look fresh.
        ({'audio_uri': STAGED, 'audio_staged_at': NOW - LIFECYCLE_SECONDS - 1, 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'audio_staged_at': NOW - LIFECYCLE_SECONDS, 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'enqueued_at': NOW - LIFECYCLE_SECONDS}, False),
        # Invalid staging clocks cannot prove retention, whatever the enqueue time says.
        ({'audio_uri': STAGED, 'audio_staged_at': math.nan, 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'audio_staged_at': 'yesterday', 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'audio_staged_at': True, 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'audio_staged_at': 0, 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'audio_staged_at': None, 'enqueued_at': NOW - 60}, False),
        ({'audio_uri': STAGED, 'enqueued_at': math.inf}, False),
        ({'audio_uri': STAGED}, False),
        # Audio outside the staging bucket has no staging clock under the contract.
        ({'audio_uri': 'gs://elsewhere/u/segment.enc', 'enqueued_at': NOW - 60}, False),
        ({'enqueued_at': NOW - 60}, False),
    ],
)
def test_only_audio_provably_inside_retention_is_rearmed(fields, inside):
    job = held(NOW - 86400, **fields)
    assert _held_inside_retention(job, NOW) is inside
    assert _held_recoverable(job, NOW) is inside
