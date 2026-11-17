"""Projection-clock operator admission, page pacing and safe early completion."""

import json
from unittest.mock import Mock

import pytest

from scripts import batch_pipeline_projection_followup_backfill as cli


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def read(self):
        return self.now

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.now += delay


@pytest.fixture
def operator(monkeypatch):
    store = Mock()
    monkeypatch.setattr(cli, 'FirestoreStore', store)
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    return store


def arguments(monkeypatch, *extra):
    monkeypatch.setattr(cli.sys, 'argv', ['stamp', '--stage', 'prod', *extra])


@pytest.mark.parametrize(
    'extra,tier',
    [
        (['--apply'], 'prod-operator'),
        (['--apply', '--confirm-writers-deployed'], 'ro-prod'),
        (['--max-pages', '2'], 'ro-prod'),
        (['--max-pages', '0'], 'ro-prod'),
        (['--max-pages', '10001'], 'ro-prod'),
        (['--page-size', '0'], 'ro-prod'),
        (['--page-size', '201'], 'ro-prod'),
        *[(['--max-rows-per-second', value], 'ro-prod') for value in ['0', '-1', 'nan', 'inf', '1e-323']],
    ],
)
def test_invalid_or_unadmitted_invocations_do_not_construct_a_store(operator, monkeypatch, extra, tier):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    arguments(monkeypatch, *extra)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    operator.assert_not_called()


def test_emulator_is_not_a_production_identity_bypass(operator, monkeypatch):
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8085')
    arguments(monkeypatch, '--apply', '--confirm-writers-deployed')
    with pytest.raises(SystemExit):
        cli.main()
    operator.assert_not_called()


def test_default_dry_run_is_one_unpaced_page(operator, monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    page = Mock(return_value={'complete': False, 'scanned': 3, 'missing': 2, 'stamped': 0})
    limiter = Mock()
    monkeypatch.setattr(cli, 'stamp_page', page)
    monkeypatch.setattr(cli, 'PageRateLimiter', Mock(return_value=limiter))
    arguments(monkeypatch)
    cli.main()
    page.assert_called_once()
    assert page.call_args.args[0] is operator.return_value
    assert page.call_args.kwargs == {'size': 200, 'apply': False}
    limiter.acquire.assert_not_called()
    assert json.loads(capsys.readouterr().out)['apply'] is False


def test_one_limiter_paces_every_page_before_store_reads_and_stops_at_completion(operator, monkeypatch, capsys):
    clock = Clock()
    real = cli.PageRateLimiter
    monkeypatch.setattr(
        cli, 'PageRateLimiter', lambda rate, size: real(rate, size, clock=clock.read, sleep=clock.sleep)
    )
    starts = []

    def page(*_, **kwargs):
        starts.append(clock.now)
        assert kwargs == {'size': 50, 'apply': True}
        # Second page is short. Full-page reservation is conservative; neither
        # this nor IO time grants a catch-up burst on the next page.
        return {'complete': len(starts) == 3, 'scanned': 2 if len(starts) == 2 else 50}

    monkeypatch.setattr(cli, 'stamp_page', page)
    arguments(
        monkeypatch,
        '--apply',
        '--confirm-writers-deployed',
        '--max-pages',
        '10',
        '--page-size',
        '50',
        '--max-rows-per-second',
        '10',
    )
    cli.main()
    assert starts == [0.0, 5.0, 10.0]
    assert clock.sleeps == [5.0, 5.0]
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(reports) == 3 and reports[-1]['complete'] is True
    assert all(report['apply'] is True for report in reports)


def test_default_apply_has_a_finite_ten_row_page_budget(operator, monkeypatch):
    limiter = Mock()
    factory = Mock(return_value=limiter)
    page = Mock(return_value={'complete': True})
    monkeypatch.setattr(cli, 'PageRateLimiter', factory)
    monkeypatch.setattr(cli, 'stamp_page', page)
    arguments(monkeypatch, '--apply', '--confirm-writers-deployed')
    cli.main()
    factory.assert_called_once_with(10.0, 200)
    limiter.acquire.assert_called_once_with()
    page.assert_called_once()


def test_slow_io_earns_no_catchup_credit_and_waits_use_bounded_sleeps():
    clock = Clock()
    limiter = cli.PageRateLimiter(10, 50, clock=clock.read, sleep=clock.sleep)
    limiter.acquire()
    clock.now = 100.0
    limiter.acquire()
    limiter.acquire()
    assert clock.now == 105.0 and clock.sleeps == [5.0]
    limiter = cli.PageRateLimiter(1, 200, clock=clock.read, sleep=clock.sleep)
    limiter.acquire()
    before = len(clock.sleeps)
    limiter.acquire()
    assert clock.sleeps[before:] == [60.0, 60.0, 60.0, 20.0]


def test_page_failure_stops_without_admitting_or_checkpointing_another_page(operator, monkeypatch):
    page = Mock(side_effect=RuntimeError('synthetic page failure'))
    monkeypatch.setattr(cli, 'stamp_page', page)
    arguments(monkeypatch, '--apply', '--confirm-writers-deployed', '--max-pages', '3')
    with pytest.raises(RuntimeError, match='synthetic page failure'):
        cli.main()
    page.assert_called_once()


def test_low_rate_reports_bounded_wait_progress_without_customer_values(capsys):
    clock = Clock()
    limiter = cli.PageRateLimiter(1, 200, clock=clock.read, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    captured = capsys.readouterr()
    assert captured.out == ''
    reports = [json.loads(line) for line in captured.err.splitlines()]
    assert [report['wait_seconds'] for report in reports] == [200.0, 140.0, 80.0, 20.0]
    assert all(
        set(report) == {'operation', 'outcome', 'wait_seconds'} and report['outcome'] == 'pacing' for report in reports
    )
