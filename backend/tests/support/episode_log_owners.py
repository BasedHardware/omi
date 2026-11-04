"""Explicit ownership for legacy test stores that model only conversation documents."""

from importlib import import_module


def without_episode_log_owner(monkeypatch):
    # Resolve the bound module even when an isolated test replaces its parent package.
    store = import_module('database.episode_log')
    monkeypatch.setattr(store, 'state', lambda *args, **kwargs: {})
