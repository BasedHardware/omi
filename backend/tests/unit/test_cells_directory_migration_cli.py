"""Cells/directory operators own one direct IAM connection; no live database needed."""

from pathlib import Path
import sys
from unittest.mock import Mock

import google.auth
from google.auth.transport import requests as auth_requests
import pytest

from database.cells import __main__ as cells_cli
from database.directory import __main__ as directory_cli
from database.jobstore import connection


@pytest.fixture(params=[(cells_cli, 'CELLS'), (directory_cli, 'DIRECTORY')], ids=['cells', 'directory'])
def cli(request, monkeypatch):
    module, prefix = request.param
    monkeypatch.setenv(f'{prefix}_PG_HOST', 'direct-private-ip')
    monkeypatch.setenv(f'{prefix}_PG_DATABASE', 'migration-db')
    monkeypatch.setenv(f'{prefix}_PG_USER', 'migration-owner@project.iam')
    # Runtime DSNs must never become a fallback for a migration operator.
    monkeypatch.setenv(f'{prefix}_PG_DSN', 'postgresql://runtime-pooler/runtime-db')
    forbidden_pool = Mock(side_effect=AssertionError('migration CLI must never construct a Pool'))
    monkeypatch.setattr(connection, 'Pool', forbidden_pool)
    monkeypatch.setattr(module, 'Pool', forbidden_pool, raising=False)
    return module, prefix


@pytest.fixture(params=['migrate', 'status'])
def command(request, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['operator', request.param])
    return request.param


def test_single_direct_connection(cli, command, monkeypatch, capsys):
    module, _ = cli
    conn = Mock(spec=['close'])
    dial = Mock(return_value=conn)
    connector = Mock(return_value=dial)
    migrate = Mock(return_value=[1, 2])
    version = Mock(return_value=2)
    monkeypatch.setattr(module, 'iam_connector', connector)
    monkeypatch.setattr(module, 'migrate', migrate)
    monkeypatch.setattr(module, 'current_version', version)

    module.main()

    connector.assert_called_once_with('direct-private-ip', 'migration-db', 'migration-owner@project.iam')
    dial.assert_called_once_with()
    if command == 'migrate':
        migrate.assert_called_once_with(conn, directory=Path(module.__file__).parent / 'migrations')
        version.assert_not_called()
        assert capsys.readouterr().out == '[1, 2]\n'
    else:
        version.assert_called_once_with(conn)
        migrate.assert_not_called()
        assert capsys.readouterr().out == '2\n'
    conn.close.assert_called_once_with()


@pytest.mark.parametrize('error_type', [ConnectionError, TimeoutError])
def test_direct_dial_failure_is_fatal(cli, command, error_type, monkeypatch, capsys):
    module, _ = cli
    error = error_type('direct dial failed')
    dial = Mock(side_effect=error)
    connector = Mock(return_value=dial)
    migrate = Mock()
    version = Mock()
    monkeypatch.setattr(module, 'iam_connector', connector)
    monkeypatch.setattr(module, 'migrate', migrate)
    monkeypatch.setattr(module, 'current_version', version)

    with pytest.raises(error_type) as raised:
        module.main()

    assert raised.value is error
    connector.assert_called_once_with('direct-private-ip', 'migration-db', 'migration-owner@project.iam')
    dial.assert_called_once_with()
    migrate.assert_not_called()
    version.assert_not_called()
    assert capsys.readouterr().out == ''


def test_operation_failure_closes_connection(cli, command, monkeypatch):
    module, _ = cli
    conn = Mock(spec=['close'])
    monkeypatch.setattr(module, 'iam_connector', Mock(return_value=Mock(return_value=conn)))
    monkeypatch.setattr(module, 'migrate', Mock(side_effect=RuntimeError('operation failed')))
    monkeypatch.setattr(module, 'current_version', Mock(side_effect=RuntimeError('operation failed')))

    with pytest.raises(RuntimeError, match='operation failed'):
        module.main()

    conn.close.assert_called_once_with()


@pytest.mark.parametrize('missing', ['HOST', 'DATABASE', 'USER'])
def test_missing_direct_config_never_uses_runtime_dsn(cli, command, missing, monkeypatch):
    module, prefix = cli
    monkeypatch.delenv(f'{prefix}_PG_{missing}')
    connector = Mock()
    monkeypatch.setattr(module, 'iam_connector', connector)

    with pytest.raises(KeyError, match=f'{prefix}_PG_{missing}'):
        module.main()

    connector.assert_not_called()


def test_help_documents_direct_endpoint_and_owner(cli, monkeypatch, capsys):
    module, prefix = cli
    monkeypatch.setattr(sys, 'argv', ['operator', '--help'])
    connector = Mock()
    monkeypatch.setattr(module, 'iam_connector', connector)

    with pytest.raises(SystemExit) as raised:
        module.main()

    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    for text in (f'{prefix}_PG_HOST', f'{prefix}_PG_DATABASE', f'{prefix}_PG_USER', '5432', 'ADC', 'migration-owner'):
        assert text in help_text
    connector.assert_not_called()


def test_direct_cli_preserves_iam_token_auth(cli, command, monkeypatch):
    module, _ = cli
    credentials = Mock(token='fresh-iam-token')
    adc = Mock(return_value=(credentials, 'project'))
    request = object()
    conn = Mock(spec=['close'])
    driver = Mock()
    driver.connect.return_value = conn
    monkeypatch.setattr(google.auth, 'default', adc)
    monkeypatch.setattr(auth_requests, 'Request', Mock(return_value=request))
    monkeypatch.setattr(connection, '_psycopg', lambda: driver)
    monkeypatch.setattr(module, 'migrate', Mock(return_value=[]))
    monkeypatch.setattr(module, 'current_version', Mock(return_value=0))

    module.main()

    adc.assert_called_once_with(scopes=['https://www.googleapis.com/auth/sqlservice.login'])
    credentials.refresh.assert_called_once_with(request)
    driver.connect.assert_called_once()
    assert driver.connect.call_args.args == ()
    # Timeout policy belongs to the shared connector's owner; guard the CLI's auth contract.
    expected = {
        'host': 'direct-private-ip',
        'port': 5432,
        'dbname': 'migration-db',
        'user': 'migration-owner@project.iam',
        'password': 'fresh-iam-token',
        'sslmode': 'require',
        'autocommit': True,
    }
    assert driver.connect.call_args.kwargs.items() >= expected.items()
    conn.close.assert_called_once_with()
