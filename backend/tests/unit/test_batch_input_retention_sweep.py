"""Urgent expiry uses bounded object-age streams, independent of the held name cursor."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import batch_pipeline_quarantine_recovery as queries
from tests.unit.test_batch_input_retention import seed, ENQUEUED, NOW29
from tests.unit.test_batch_pipeline_quarantine_recovery import setup as setup, row
from utils.batch_pipeline import held_dead_letter as sweep
from utils.batch_pipeline.input_retention import TERMINAL_SECONDS, staged_enqueue


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_INPUT_EXPIRING_ENABLED', 'true')


class AgeQuery:
    """Read-only keyset model: missing clocks excluded, compound order and cursor enforced."""

    def __init__(self, client, filters=(), orders=(), after=None, size=None):
        self.client, self.filters, self.orders, self.after, self.size = client, filters, orders, after, size

    def where(self, field, op, value):
        return AgeQuery(self.client, self.filters + ((field, op, value),), self.orders, self.after, self.size)

    def order_by(self, field):
        return AgeQuery(self.client, self.filters, self.orders + (field,), self.after, self.size)

    def start_after(self, cursor):
        return AgeQuery(self.client, self.filters, self.orders, cursor, self.size)

    def limit(self, size):
        assert size == 128
        return AgeQuery(self.client, self.filters, self.orders, self.after, size)

    def document(self, sid):
        return SimpleNamespace(id=sid)

    def stream(self):
        assert self.orders in [('enqueued_at', '__name__'), ('audio_staged_at', '__name__')]
        assert self.size == 128
        clock = self.orders[0]
        self.client.calls.append((clock, self.size, self.after))
        rows = []
        assert all(op in {'in', '<='} for _, op, _ in self.filters)
        for key, job in self.client.rows.items():
            if len(key) != 2 or key[0] != 'batch_pipeline_prod_jobs' or clock not in job:
                continue
            _, sid = key
            if any(
                (
                    job.get(field) not in value
                    if op == 'in'
                    else type(job.get(field)) not in (int, float) or job[field] > value
                )
                for field, op, value in self.filters
            ):
                continue
            if self.after and (job[clock], sid) <= (self.after[clock], self.after['__name__'].id):
                continue
            rows.append((sid, deepcopy(job)))
        rows.sort(key=lambda pair: (pair[1][clock], pair[0]))
        return [SimpleNamespace(id=sid, to_dict=lambda job=job: deepcopy(job)) for sid, job in rows[: self.size]]


class AgeClient:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def collection(self, name):
        assert name == 'batch_pipeline_prod_jobs'
        return AgeQuery(self)


def urgent_runner(setup, monkeypatch, leg='gpu'):
    client, store, _ = seed(setup, leg)
    age = AgeClient(client.rows)
    store.run(lambda tx: tx.put('leases', sweep.CURSOR_KEY, {'held_after': 'zzzz-long-held-cursor'}))
    monkeypatch.setattr(
        sweep,
        'input_expiring_candidates',
        lambda client, namespace, now, **kwargs: queries.input_expiring_candidates(age, namespace, now, **kwargs),
    )
    monkeypatch.setattr(sweep, 'held_candidates', lambda *args, **kwargs: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *args, **kwargs: [])
    monkeypatch.setattr(sweep, 'held_expired_stock', lambda *args: 0)
    return client, store, age


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_due_row_behind_long_name_cursor_fires_before_cursor_page_in_one_tick(setup, monkeypatch, leg):
    client, store, age = urgent_runner(setup, monkeypatch, leg)

    def ordinary_page(*args, **kwargs):
        assert kwargs['after_id'] == 'zzzz-long-held-cursor'
        assert row(client)['dead_letter_reason'] == 'input_expiring'
        return []

    monkeypatch.setattr(sweep, 'held_candidates', ordinary_page)
    assert sweep.HeldDeadLetter(store).tick(NOW29) == {'expired': 1, 'requeued': 0}
    assert age.calls == [('enqueued_at', 128, None), ('audio_staged_at', 128, None)]


def test_fresh_restage_prefix_cannot_pin_legacy_urgency_cursor(setup, monkeypatch):
    client, store, age = urgent_runner(setup, monkeypatch)
    for i in range(129):
        sid = f'restaged-{i:03d}'
        client.rows['batch_pipeline_prod_jobs', sid] = {
            **deepcopy(row(client)),
            'segment_id': sid,
            'enqueued_at': ENQUEUED - 1,
            'audio_staged_at': NOW29,
        }
    assert sweep.HeldDeadLetter(store).tick(NOW29) == {'expired': 0, 'requeued': 0}
    assert row(client)['state'] == 'quarantined'
    assert sweep.HeldDeadLetter(store).tick(NOW29 + sweep.INTERVAL_SECONDS) == {'expired': 1, 'requeued': 0}
    assert age.calls[2][2]['enqueued_at'] == ENQUEUED - 1
    assert row(client)['dead_letter_reason'] == 'input_expiring'
    assert sweep.INTERVAL_SECONDS < 86400


def test_current_object_clock_orders_replacements_and_legacy_objects(setup, monkeypatch):
    client, _, age = urgent_runner(setup, monkeypatch)
    base = deepcopy(row(client))
    client.rows['batch_pipeline_prod_jobs', 'bad']['enqueued_at'] = ENQUEUED - 2
    client.rows['batch_pipeline_prod_jobs', 'replacement'] = {
        **base,
        'segment_id': 'replacement',
        'enqueued_at': 1,
        'audio_staged_at': ENQUEUED - 1,
    }
    client.rows['batch_pipeline_prod_jobs', 'fresh'] = {
        **base,
        'segment_id': 'fresh',
        'enqueued_at': 1,
        'audio_staged_at': NOW29,
    }
    page, cursors = queries.input_expiring_candidates(age, 'batch_pipeline_prod', NOW29)
    assert [sid for sid, _ in page] == ['bad', 'replacement']
    assert [staged_enqueue(job) for _, job in page] == [ENQUEUED - 2, ENQUEUED - 1]
    assert cursors == {'enqueued_at': None, 'audio_staged_at': None}


def test_fresh_restage_is_skipped_until_its_own_day29(setup, monkeypatch):
    client, store, _ = urgent_runner(setup, monkeypatch)
    row(client)['audio_staged_at'] = NOW29
    assert sweep.HeldDeadLetter(store).tick(NOW29) == {'expired': 0, 'requeued': 0}
    assert sweep.HeldDeadLetter(store).tick(NOW29 + TERMINAL_SECONDS) == {'expired': 1, 'requeued': 0}
    assert row(client)['dead_letter_reason'] == 'input_expiring'


def test_kill_off_has_no_urgency_queries(setup, monkeypatch):
    _, store, _ = urgent_runner(setup, monkeypatch)
    monkeypatch.setenv('BATCH_INPUT_EXPIRING_ENABLED', 'false')
    query = Mock(side_effect=AssertionError('urgency query while killed'))
    monkeypatch.setattr(sweep, 'input_expiring_candidates', query)
    assert sweep.HeldDeadLetter(store).tick(NOW29) == {'expired': 0, 'requeued': 0}
    query.assert_not_called()
