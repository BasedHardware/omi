"""The operator command defaults to read-only and never echoes account data."""

from datetime import datetime, timezone
import json

import pytest

from scripts import expire_memory_reviews as script


@pytest.mark.parametrize('mode, dry_run', [([], True), (['--dry-run'], True), (['--apply'], False)])
def test_script_modes_print_only_aggregate_counts(monkeypatch, capsys, mode, dry_run):
    calls = []

    def expire(uid, **kwargs):
        calls.append((uid, kwargs))
        return {'pending': {'canonical_memory': 2, 'legacy': 1}}

    monkeypatch.setattr(script, 'expire_review_conflicts', expire)
    assert script.main(['--uid', 'synthetic-account', '--created-before', '2026-07-20T00:00:00Z', *mode]) == 0
    assert calls == [
        ('synthetic-account', {'created_before': datetime(2026, 7, 20, tzinfo=timezone.utc), 'dry_run': dry_run})
    ]
    output = capsys.readouterr()
    assert json.loads(output.out) == {'pending': {'canonical_memory': 2, 'legacy': 1}}
    assert output.err == ''
    assert 'synthetic-account' not in output.out


@pytest.mark.parametrize(
    'options',
    [
        ['--created-before', '2026-07-20'],
        ['--created-before', 'invalid'],
        ['--created-before', '2026-07-20T00:00:00Z', '--dry-run', '--apply'],
        ['--created-before', '2026-07-20T00:00:00Z', '--unknown', 'synthetic-account'],
    ],
)
def test_invalid_arguments_do_not_read_or_echo_values(monkeypatch, capsys, options):
    def unexpected_expire(*args, **kwargs):
        raise AssertionError('invalid arguments must not read')

    monkeypatch.setattr(script, 'expire_review_conflicts', unexpected_expire)
    with pytest.raises(SystemExit) as exc:
        script.main(['--uid', 'synthetic-account', *options])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert 'synthetic-account' not in output.out + output.err


def test_provider_exception_does_not_print_document_path(monkeypatch, capsys):
    def failing_expire(*args, **kwargs):
        raise RuntimeError('users/synthetic-account/memory_review_queue/private-content')

    monkeypatch.setattr(script, 'expire_review_conflicts', failing_expire)
    assert script.main(['--uid', 'synthetic-account', '--created-before', '2026-07-20T00:00:00Z']) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'Expiration failed; rerun dry-run before retrying apply.\n'
