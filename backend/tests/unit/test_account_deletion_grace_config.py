from datetime import timedelta

from config import account_deletion_grace


def test_grace_is_enabled_by_default_and_defaults_to_fourteen_days(monkeypatch):
    monkeypatch.delenv('ACCOUNT_DELETION_GRACE_ENABLED', raising=False)
    monkeypatch.delenv('ACCOUNT_DELETION_GRACE_WINDOW_DAYS', raising=False)

    assert account_deletion_grace.account_deletion_grace_enabled() is True
    assert account_deletion_grace.account_deletion_grace_window() == timedelta(days=14)


def test_grace_kill_switch_and_window_bounds(monkeypatch):
    monkeypatch.setenv('ACCOUNT_DELETION_GRACE_ENABLED', 'false')
    monkeypatch.setenv('ACCOUNT_DELETION_GRACE_WINDOW_DAYS', '9999')

    assert account_deletion_grace.account_deletion_grace_enabled() is False
    assert account_deletion_grace.account_deletion_grace_window() == timedelta(days=365)


def test_invalid_window_uses_the_default(monkeypatch):
    monkeypatch.setenv('ACCOUNT_DELETION_GRACE_WINDOW_DAYS', 'not-a-number')

    assert account_deletion_grace.account_deletion_grace_window() == timedelta(days=14)
