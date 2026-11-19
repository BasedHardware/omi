"""Bound cold copy-pool authentication without starting a timeout worker."""

from types import SimpleNamespace

import google.auth
import google.auth.transport.requests
import pytest

from database.jobstore import connection


@pytest.fixture
def setup(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(connection.time, 'monotonic', lambda: clock[0])
    requests, dials = [], []

    def request(*args, **kwargs):
        requests.append(kwargs['timeout'])
        clock[0] += 1

    monkeypatch.setattr(google.auth.transport.requests, 'Request', lambda: request)

    def default(*, scopes, request):
        request(url='http://synthetic.invalid/metadata', timeout=120)
        return (
            SimpleNamespace(
                token='synthetic', refresh=lambda req: req(url='http://synthetic.invalid/token', timeout=120)
            ),
            None,
        )

    monkeypatch.setattr(google.auth, 'default', default)
    conn = SimpleNamespace(closed=False)
    conn.close = lambda: setattr(conn, 'closed', True)

    def connect(**kwargs):
        dials.append(kwargs['connect_timeout'])
        return conn

    monkeypatch.setattr(connection, '_psycopg', lambda: SimpleNamespace(connect=connect))
    return SimpleNamespace(clock=clock, requests=requests, dials=dials, conn=conn)


def test_authentication_and_dial_share_setup_deadline(setup):
    assert connection.iam_connector('synthetic', 'db', 'user', setup_timeout_s=5)() is setup.conn
    assert setup.requests == [5, 4] and setup.dials == [3]


def test_authentication_cannot_start_a_dial_below_libpq_minimum(setup, monkeypatch):
    def default(*, scopes, request):
        setup.clock[0] += 4
        return SimpleNamespace(token='synthetic', refresh=lambda _: None), None

    monkeypatch.setattr(google.auth, 'default', default)
    with pytest.raises(TimeoutError, match='setup deadline'):
        connection.iam_connector('synthetic', 'db', 'user', setup_timeout_s=5)()
    assert setup.dials == []


def test_elapsed_dial_is_closed_before_pool_can_reuse_it(setup, monkeypatch):
    def slow_dial(**kwargs):
        setup.clock[0] += 4
        return setup.conn

    monkeypatch.setattr(connection, '_psycopg', lambda: SimpleNamespace(connect=slow_dial))
    with pytest.raises(TimeoutError, match='setup deadline'):
        connection.iam_connector('synthetic', 'db', 'user', setup_timeout_s=5)()
    assert setup.conn.closed
