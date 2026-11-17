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
