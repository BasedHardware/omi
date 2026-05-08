"""Pytest fixtures for the omi-cli test suite.

Each test gets:

* An isolated config dir under a temp path (via the ``OMI_CONFIG`` env var).
* A pre-seeded "default" profile with a fake API key.
* A respx mock router pointing at the fake API base URL so HTTP calls are
  intercepted and asserted against, rather than going to the real Omi API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
import respx
from typer.testing import CliRunner

from omi_cli import config as cfg
from omi_cli.auth.store import store_api_key

FAKE_API_BASE = "https://api.test.omi.local"
FAKE_API_KEY = "omi_dev_" + ("x" * 32)


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate the config file to ``tmp_path`` for each test."""
    target = tmp_path / "config.toml"
    monkeypatch.setenv(cfg.ENV_CONFIG_PATH, str(target))
    # Clean up any inherited credentials from the user's real env.
    for var in (cfg.ENV_API_KEY, cfg.ENV_API_BASE, cfg.ENV_PROFILE):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("OMI_NO_COLOR", raising=False)
    return target


@pytest.fixture
def authed_profile(config_path: Path) -> cfg.Profile:
    """Create a default profile pre-loaded with a fake API key + custom api_base."""
    return store_api_key("default", FAKE_API_KEY, api_base=FAKE_API_BASE)


@pytest.fixture
def respx_mock() -> Iterator[respx.MockRouter]:
    """A respx router scoped to the fake API base URL."""
    with respx.mock(base_url=FAKE_API_BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer's CliRunner — used to invoke the root ``app`` in tests.

    Click 8.2+ separates stderr from stdout by default (the old ``mix_stderr``
    argument was removed). Tests can read ``result.stderr`` directly to assert
    the JSON-mode agent contract.
    """
    return CliRunner()


@pytest.fixture(autouse=True)
def _reset_typer_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop Typer/Rich from picking up the real terminal width during tests."""
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "200")
