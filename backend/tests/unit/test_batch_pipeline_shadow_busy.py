"""Ordinary runnable work wins, while parked debt cannot poison shadow idle offers."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from database.batch_pipeline_shadow import RECORD_PENDING_BUSY_SECONDS, pool_busy


class MetadataQuery:
    """Synthetic metadata query fixture; query/index shapes have their own real-builder guard."""

    def __init__(self, rows, filters=(), limit=None):
        self.rows, self.filters, self.bound = rows, filters, limit

    def where(self, field, op, value):
        return MetadataQuery(self.rows, (*self.filters, (field, op, value)), self.bound)

    def order_by(self, field):
        return self

    def select(self, fields):
        return self

    def limit(self, value):
        return MetadataQuery(self.rows, self.filters, value)

    def stream(self):
        matches = []
        for row in self.rows:
            for field, op, value in self.filters:
                actual = row.get(field)
                if actual is None or not (
                    actual == value if op == '==' else actual <= value if op == '<=' else actual > value
                ):
                    break
            else:
                matches.append(SimpleNamespace(to_dict=lambda row=row: deepcopy(row)))
        return iter(matches[: self.bound])


def busy(rows):
    original = deepcopy(rows)
    client = SimpleNamespace(collection=lambda name: MetadataQuery(rows))
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
