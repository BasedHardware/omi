"""Operator gates must remain ahead of every migration store access."""

import json
from unittest.mock import Mock

import pytest

from scripts import batch_pipeline_allowance_migration as cli


@pytest.fixture
def harness(monkeypatch):
    store = Mock()
    monkeypatch.setattr(cli, 'FirestoreStore', store)
    monkeypatch.setattr(cli.logging, 'disable', lambda _: None)
    return store


@pytest.mark.parametrize(
    'arguments,tier',
    [
        (['--apply'], 'prod-operator'),
        (['--apply', '--confirm-reviewed-rollout-go'], 'ro-prod'),
        (['--apply', '--dry-run', '--confirm-reviewed-rollout-go'], 'prod-operator'),
        (['--dry-run'], 'prod-operator'),
        (['--concurrency', '33'], 'ro-prod'),
        (['--concurrency', '0'], 'ro-prod'),
        (['--max-rows-per-second', '0'], 'ro-prod'),
        (['--max-rows-per-second', 'nan'], 'ro-prod'),
        (['--max-rows-per-second', 'inf'], 'ro-prod'),
    ],
)
def test_rejected_before_any_store_access(harness, monkeypatch, arguments, tier):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(cli.sys, 'argv', ['migration', '--stage', 'prod', *arguments])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    harness.assert_not_called()


def test_prod_apply_refuses_emulator_even_with_operator_identity(harness, monkeypatch):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8085')
    monkeypatch.setattr(cli.sys, 'argv', ['migration', '--stage', 'prod', '--apply', '--confirm-reviewed-rollout-go'])
    with pytest.raises(SystemExit):
        cli.main()
    harness.assert_not_called()


def test_apply_shares_limiter_across_pages_and_drains_executor(harness, monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(
        cli.sys,
        'argv',
        [
            'migration',
            '--stage',
            'prod',
            '--apply',
            '--confirm-reviewed-rollout-go',
            '--max-pages',
            '3',
            '--concurrency',
            '32',
            '--max-rows-per-second',
            '50',
        ],
    )
    apply = Mock(side_effect=[{'complete': False}, {'complete': True}])
    shutdown = Mock()
    monkeypatch.setattr(cli, 'apply_page', apply)
    monkeypatch.setattr(cli, 'shutdown_executors', shutdown)
    cli.main()
    assert apply.call_count == 2
    first, second = (call.kwargs for call in apply.call_args_list)
    assert first['concurrency'] == 32
    assert first['rate_limiter'] is second['rate_limiter']
    assert first['rate_limiter'].rate == 50
    shutdown.assert_called_once_with()
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == [
        {'complete': False},
        {'complete': True},
    ]


def test_default_apply_is_sequential_and_unlimited(harness, monkeypatch):
    monkeypatch.setattr(cli.sys, 'argv', ['migration', '--stage', 'dev', '--apply', '--confirm-reviewed-rollout-go'])
    apply = Mock(return_value={'complete': True})
    monkeypatch.setattr(cli, 'apply_page', apply)
    cli.main()
    assert apply.call_args.kwargs['concurrency'] == 1
    assert apply.call_args.kwargs['rate_limiter'].rate is None


def _raise_chain(*errors):
    """Raise errors[0] from errors[1] from ... and return the outermost."""
    cause = None
    for error in reversed(errors):
        try:
            if cause is None:
                raise error
            raise error from cause
        except BaseException as raised:
            cause = raised
    return cause


@pytest.mark.parametrize(
    'error,error_type,retryable',
    [
        (
            cli.api_exceptions.DeadlineExceeded('jobs/secret-doc-id'),
            'google.api_core.exceptions.DeadlineExceeded',
            True,
        ),
        (cli.api_exceptions.Aborted('owner contention'), 'google.api_core.exceptions.Aborted', True),
        (cli.api_exceptions.ServiceUnavailable('unavailable'), 'google.api_core.exceptions.ServiceUnavailable', True),
        (cli.api_exceptions.InternalServerError('internal'), 'google.api_core.exceptions.InternalServerError', True),
        (cli.api_exceptions.ResourceExhausted('quota'), 'google.api_core.exceptions.ResourceExhausted', True),
        (
            cli.MigrationOwnerChanged('migration owner changed; retry the page'),
            'database.batch_pipeline_allowance_migration.MigrationOwnerChanged',
            True,
        ),
        (cli.api_exceptions.PermissionDenied('denied'), 'google.api_core.exceptions.PermissionDenied', False),
        (ValueError('owner mismatch users/secret-uid'), 'builtins.ValueError', False),
    ],
)
def test_error_report_names_the_class_and_never_the_message(error, error_type, retryable):
    report = cli.error_report(error)
    assert report == {'errors': 1, 'error_type': error_type, 'retryable': retryable}
    assert 'secret' not in json.dumps(report)


def test_error_report_walks_the_whole_cause_chain():
    error = _raise_chain(
        cli.FirestoreContentionExhausted('contention on jobs/secret-doc-id'),
        cli.api_exceptions.RetryError('retries exhausted', None),
        cli.api_exceptions.Aborted('jobs/secret-doc-id'),
    )
    report = cli.error_report(error)
    assert report['retryable'] is True
    assert report['cause_types'] == ['google.api_core.exceptions.RetryError', 'google.api_core.exceptions.Aborted']
    assert 'secret' not in json.dumps(report)


def test_error_report_treats_an_expired_transaction_as_contention():
    error = _raise_chain(RuntimeError('page failed'), cli.api_exceptions.InvalidArgument('Transaction has expired'))
    assert cli.error_report(error)['retryable'] is True


def test_error_report_ignores_implicit_context():
    for suppress in (True, False):
        try:
            try:
                raise cli.api_exceptions.Aborted('incidental')
            except cli.api_exceptions.Aborted:
                if suppress:
                    raise ValueError('real stop') from None
                raise ValueError('real stop')
        except ValueError as error:
            report = cli.error_report(error)
        assert report == {'errors': 1, 'error_type': 'builtins.ValueError', 'retryable': False}


def test_error_report_reads_the_sdk_retry_error_cause_attribute():
    error = cli.api_exceptions.RetryError('Timeout of 60.0s exceeded', cli.api_exceptions.Aborted('jobs/secret-doc-id'))
    assert error.__cause__ is None
    report = cli.error_report(error)
    assert report == {
        'errors': 1,
        'error_type': 'google.api_core.exceptions.RetryError',
        'retryable': True,
        'cause_types': ['google.api_core.exceptions.Aborted'],
    }
    assert 'secret' not in json.dumps(report)


def test_error_report_keeps_a_fatal_retry_error_cause_fatal():
    error = cli.api_exceptions.RetryError('exhausted', cli.api_exceptions.PermissionDenied('denied'))
    assert cli.error_report(error)['retryable'] is False


@pytest.mark.parametrize(
    'chain',
    [
        (cli.api_exceptions.DeadlineExceeded('outer'), cli.api_exceptions.PermissionDenied('denied')),
        (cli.FirestoreContentionExhausted('outer'), cli.api_exceptions.NotFound('jobs/secret-doc-id')),
        (RuntimeError('page'), cli.api_exceptions.Aborted('a'), cli.api_exceptions.FailedPrecondition('index')),
    ],
)
def test_a_fatal_rpc_status_anywhere_in_the_chain_vetoes_retry(chain):
    report = cli.error_report(_raise_chain(*chain))
    assert report['retryable'] is False
    assert 'secret' not in json.dumps(report)


@pytest.mark.parametrize(
    'chain',
    [
        (cli.api_exceptions.PermissionDenied('denied'), cli.api_exceptions.Aborted('a')),
        (
            cli.api_exceptions.NotFound('jobs/secret-doc-id'),
            cli.api_exceptions.InvalidArgument('Transaction has expired'),
        ),
    ],
)
def test_a_fatal_status_raised_from_a_transient_cause_stays_fatal(chain):
    report = cli.error_report(_raise_chain(*chain))
    assert report['retryable'] is False
    assert 'secret' not in json.dumps(report)


@pytest.mark.parametrize(
    'explicit,sdk',
    [
        (cli.api_exceptions.Aborted('a'), cli.api_exceptions.PermissionDenied('jobs/secret-doc-id')),
        (cli.api_exceptions.PermissionDenied('jobs/secret-doc-id'), cli.api_exceptions.Aborted('a')),
    ],
)
def test_a_retry_error_walks_both_its_explicit_and_sdk_causes(explicit, sdk):
    try:
        raise cli.api_exceptions.RetryError('exhausted', sdk) from explicit
    except cli.api_exceptions.RetryError as error:
        report = cli.error_report(error)
    assert report['retryable'] is False
    assert set(report['cause_types']) == {
        'google.api_core.exceptions.Aborted',
        'google.api_core.exceptions.PermissionDenied',
    }
    assert 'secret' not in json.dumps(report)


def test_a_retry_error_with_both_causes_transient_stays_retryable():
    try:
        raise cli.api_exceptions.RetryError('exhausted', cli.api_exceptions.DeadlineExceeded('d')) from (
            cli.api_exceptions.Aborted('a')
        )
    except cli.api_exceptions.RetryError as error:
        assert cli.error_report(error)['retryable'] is True


def test_a_non_exception_retry_error_cause_still_yields_a_stop_line():
    error = cli.api_exceptions.RetryError('exhausted', None)
    error._cause = 'not an exception'
    error.__cause__ = None
    assert cli.error_report(error) == {
        'errors': 1,
        'error_type': 'google.api_core.exceptions.RetryError',
        'retryable': False,
    }


def test_error_report_is_not_retryable_when_any_sibling_failure_is_not():
    error = cli.api_exceptions.Aborted('first')
    error.migration_sibling_errors = (cli.api_exceptions.DeadlineExceeded('x'), ValueError('users/secret-uid'))
    report = cli.error_report(error)
    assert report['errors'] == 3
    assert report['retryable'] is False
    assert report['sibling_types'] == ['builtins.ValueError', 'google.api_core.exceptions.DeadlineExceeded']
    assert 'secret' not in json.dumps(report)


def test_error_report_is_retryable_when_every_sibling_failure_is():
    error = cli.api_exceptions.Aborted('first')
    error.migration_sibling_errors = (cli.MigrationOwnerChanged('retry the page'),)
    assert cli.error_report(error)['retryable'] is True


def test_run_prints_only_the_classified_stop_line_and_exits_1(monkeypatch, capsys):
    def fail():
        raise cli.api_exceptions.DeadlineExceeded('jobs/secret-doc-id')

    monkeypatch.setattr(cli, 'main', fail)
    assert cli.run() == 1
    out = capsys.readouterr()
    assert json.loads(out.out) == {
        'errors': 1,
        'error_type': 'google.api_core.exceptions.DeadlineExceeded',
        'retryable': True,
    }
    assert 'secret' not in out.out + out.err


def test_run_returns_0_on_success(monkeypatch):
    monkeypatch.setattr(cli, 'main', lambda: None)
    assert cli.run() == 0
