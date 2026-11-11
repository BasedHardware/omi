"""Regression tests for literal Rich status output in ``omi config``."""

from __future__ import annotations

from pathlib import Path

from omi_cli import config as cfg
from omi_cli.main import app


def test_config_profile_status_renders_user_markup_literally(config_path: Path, cli_runner) -> None:
    name = "[/bold]"

    use_result = cli_runner.invoke(app, ["config", "profile", "use", name])
    assert use_result.exit_code == 0, use_result.output
    assert name in use_result.stderr
    assert cfg.load().active_profile == name

    value = "https://example.test/[/bold]"
    set_result = cli_runner.invoke(app, ["config", "set", "api_base", value])
    assert set_result.exit_code == 0, set_result.output
    assert value in set_result.stderr
    assert cfg.load().get_profile(name).api_base == value

    delete_result = cli_runner.invoke(app, ["config", "profile", "delete", name, "--yes"])
    assert delete_result.exit_code == 0, delete_result.output
    assert name in delete_result.stderr
    assert name not in cfg.load().profiles


def test_config_status_preserves_matched_rich_tags_as_literal_text(config_path: Path, cli_runner) -> None:
    name = "[bold]literal[/bold]"

    result = cli_runner.invoke(app, ["config", "profile", "use", name])

    assert result.exit_code == 0, result.output
    assert name in result.stderr
    assert cfg.load().active_profile == name
