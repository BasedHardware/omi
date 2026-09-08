"""Pytest fixtures for the omi-cli test suite.

Each test gets:

* An isolated config dir under a temp path (via the ``OMI_CONFIG`` env var).
* A pre-seeded "default" profile with a fake API key.
* A respx mock router pointing at the fake API base URL so HTTP calls are
  intercepted and asserted against, rather than going to the real Omi API.
"""

from __future__ import annotations

import os
import runpy
import sys
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import distribution
from io import StringIO
from pathlib import Path
from typing import Iterator, NamedTuple

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
    for var in (cfg.ENV_API_KEY, cfg.ENV_API_BASE, cfg.ENV_LOCAL_API_URL, cfg.ENV_LOCAL_TOKEN, cfg.ENV_PROFILE):
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
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        # Click 8.2+ removed mix_stderr and always captures stderr separately.
        pass
    return CliRunner()


@pytest.fixture(autouse=True)
def _reset_typer_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop Typer/Rich from picking up the real terminal width during tests."""
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "200")


class PublicCliResult(NamedTuple):
    exit_code: int
    stdout: str
    stderr: str


@pytest.fixture(params=["console", "module"])
def public_cli(request, monkeypatch, config_path):
    """Run either shipped entrypoint with isolated I/O and mockable HTTP.

    Resolve the console target from installed package metadata, and execute the
    actual __main__ module for ``python -m``. Calling the bare Typer app would
    bypass the public error handler and hide entrypoint regressions.
    """

    def invoke(args, *, input_text="", tty=False):
        stdout, stderr, stdin = StringIO(), StringIO(), StringIO(input_text)
        stdin.isatty = lambda: tty
        exit_code = 0
        with monkeypatch.context() as invocation:
            invocation.setattr(sys, "argv", ["omi", "--no-color", *args])
            invocation.setattr(sys, "stdin", stdin)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    if request.param == "console":
                        entry = next(
                            ep
                            for ep in distribution("omi-cli").entry_points
                            if ep.group == "console_scripts" and ep.name == "omi"
                        )
                        entry.load()()
                    else:
                        runpy.run_module("omi_cli", run_name="__main__")
                except SystemExit as exc:
                    exit_code = exc.code or 0
        return PublicCliResult(exit_code, stdout.getvalue(), stderr.getvalue())

    return invoke
