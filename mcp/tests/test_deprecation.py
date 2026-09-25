"""Deprecation notice, version, and example-syntax checks."""

from __future__ import annotations

import logging
import py_compile
from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_server_omi import main
from mcp_server_omi.__about__ import __version__


def test_version_is_0_2_0() -> None:
    assert __version__ == "0.2.0"


def test_cli_logs_one_deprecation_warning_to_stderr_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stdio server warns once on stderr (never stdout) then serves.

    ``serve`` is stubbed so the CLI entrypoint completes without any network or
    stdio work; the real ``asyncio.run`` still drives it. Root handlers are
    cleared for the duration so ``basicConfig(stream=sys.stderr)`` inside the
    CLI actually binds the runner's stderr — proving the warning really lands
    on the stderr stream, not just on the root logger.
    """
    served: list[bool] = []

    async def fake_serve(_uid: object) -> None:
        served.append(True)

    monkeypatch.setattr("mcp_server_omi.serve", fake_serve)
    monkeypatch.setattr(logging.root, "handlers", [])
    runner = CliRunner()
    result = runner.invoke(main)

    assert result.exit_code == 0
    assert served == [True]
    assert result.stderr.count("deprecated") == 1
    assert "https://api.omi.me/v1/mcp" in result.stderr
    # stdio protocol: nothing may be written to stdout.
    assert result.stdout == ""


def test_example_scripts_compile() -> None:
    examples_dir = Path(__file__).resolve().parent.parent / "examples"
    scripts = sorted(examples_dir.glob("*.py"))
    assert scripts, "expected example scripts to exist"
    for script in scripts:
        py_compile.compile(str(script), doraise=True)
