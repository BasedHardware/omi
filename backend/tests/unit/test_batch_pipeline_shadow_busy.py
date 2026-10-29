"""Ordinary runnable work wins, while parked debt cannot poison shadow idle offers."""

from copy import deepcopy

import pytest

from tests.unit.fixtures.batch_shadow_metadata_query import metadata_client

from database.batch_pipeline_shadow import BUSY_HOLD_SCAN_LIMIT, RECORD_PENDING_BUSY_SECONDS, pool_busy


def busy(rows):
    original = deepcopy(rows)
    client = metadata_client(rows)
    result = pool_busy(client, 'batch_pipeline_dev', now=10000.0)
    assert rows == original  # The probe never repairs or changes ordinary work.
    return result


def retry(*, available=9999.0, attempt=1, maximum=5, **values):
    return {
        'state': 'retry',
        'available_at': available,
        'attempt': attempt,
        'policy_parts': {'scheduler': {'max_attempts': maximum}},
        **values,
    }


@pytest.mark.parametrize(
    'row',
    [
        {'state': 'leased', 'lease_until': 9999.0},
        {'state': 'leased', 'lease_until': 10000.0},
        retry(available=10001.0),
        {'state': 'record_pending', 'enqueued_at': 0.0},
        {'state': 'record_pending', 'enqueued_at': 10000.0 - RECORD_PENDING_BUSY_SECONDS},
    ],
)
def test_parked_or_expired_work_does_not_block_shadow(row):
    assert not busy([row])


@pytest.mark.parametrize(
    'row',
    [
        {'state': 'ready'},
        {'state': 'leased', 'lease_until': 10001.0},
        retry(available=10000.0),
        retry(enqueued_at=0.0),  # Old age never excludes a due retry with attempts left.
        retry(attempt=5),  # The scheduler may still promote it outside the serving retry-cap cohort.
        retry(attempt=9),
        {'state': 'record_pending', 'enqueued_at': 9999.0},
    ],
)
def test_runnable_work_still_blocks_shadow(row):
    assert busy([row])


def test_old_parked_population_does_not_hide_live_work():
    parked = [retry(available=20000.0, enqueued_at=0.0) for _ in range(175)]
    assert not busy(parked)
    assert busy([*parked, {'state': 'ready'}])
    assert busy([*parked, retry()])


@pytest.mark.parametrize('attempt,maximum', [(None, 5), (True, 5), (-1, 5), (1, None), (1, 0), (1, 21)])
def test_attempt_metadata_cannot_release_a_due_retry(attempt, maximum):
    assert busy([retry(attempt=attempt, maximum=maximum)])


def test_due_retry_at_attempt_cap_behind_parked_population_retains_priority():
    parked = [retry(available=20000.0) for _ in range(175)]
    assert busy([*parked, retry(attempt=5)])


def test_empty_pool_is_idle():
    assert not busy([])


@pytest.mark.parametrize('state', ['ready', 'retry'])
def test_authoritative_allowance_hold_does_not_block_idle_gpu(state):
    row = retry(state=state, compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'})
    assert not busy([row])


def test_policy_hold_survives_unevaluated_refresh_but_a_new_allow_wins():
    row = retry(last_policy_hold={'reason': 'allowance_exhausted'})
    assert not busy([row])
    row['compute_decision'] = {'outcome': 'allowed'}
    assert busy([row])


def test_other_hold_reasons_remain_busy():
    assert busy([retry(compute_decision={'outcome': 'held', 'reason': 'synthetic_other_hold'})])


@pytest.mark.parametrize('state', ['ready', 'retry'])
def test_unknown_nonempty_decision_overrides_stale_allowance_hold(state):
    assert busy(
        [
            retry(
                state=state,
                compute_decision={'status': 'pending_review'},
                last_policy_hold={'reason': 'allowance_exhausted'},
            )
        ]
    )


def test_held_prefix_does_not_hide_runnable_retry_at_attempt_cap():
    held = [retry(compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'}) for _ in range(168)]
    assert not busy(held)
    assert busy([*held, retry(attempt=5)])


def test_full_held_scan_fails_busy_for_unmeasured_tail():
    held = [
        retry(compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'})
        for _ in range(BUSY_HOLD_SCAN_LIMIT)
    ]
    assert not busy(held)
    assert busy([*held, held[0]])
