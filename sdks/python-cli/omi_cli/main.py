"""Typer entry point for omi-cli.

This is the root app — sub-commands are registered from :mod:`omi_cli.commands`.
The root callback parses global flags and stashes a request-scoped object on
``ctx.obj`` for sub-commands to consume.

Global flags:

* ``--json``         Emit machine-readable JSON to stdout. The agent contract.
* ``--profile NAME`` Use a specific profile from ``~/.omi/config.toml``.
* ``--api-base URL`` Override the API base URL (handy for staging/local).
* ``-v/--verbose``   Log HTTP traffic to stderr.
* ``--no-color``     Disable colored output (also honors ``NO_COLOR`` env var).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import click
import typer

from omi_cli import __version__
from omi_cli import config as cfg
from omi_cli.auth.api_key import validate_api_key_format
from omi_cli.client import OmiClient
from omi_cli.commands import action_item as action_item_cmd
from omi_cli.commands import auth as auth_cmd
from omi_cli.commands import config as config_cmd
from omi_cli.commands import conversation as conversation_cmd
from omi_cli.commands import goal as goal_cmd
from omi_cli.commands import memory as memory_cmd
from omi_cli.errors import CliError
from omi_cli.output import Renderer

app = typer.Typer(
    name="omi",
    help=(
        "Omi command-line interface — talk to memories, conversations, "
        "action items, and goals from your terminal. Designed for humans and "
        "agents alike. See https://github.com/BasedHardware/omi for the source."
    ),
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
)


@dataclass
class AppContext:
    """Per-invocation state attached to the Typer context (``ctx.obj``)."""

    profile_name: str
    api_base_override: Optional[str]
    renderer: Renderer
    verbose: bool
    _config: Optional[cfg.Config] = field(default=None, init=False)

    def load_config(self) -> cfg.Config:
        if self._config is None:
            self._config = cfg.load()
        return self._config

    def reload_config(self) -> cfg.Config:
        self._config = cfg.load()
        return self._config

    def get_profile(self) -> cfg.Profile:
        config = self.load_config()
        profile = config.get_profile(self.profile_name)
        if self.api_base_override:
            profile.api_base = self.api_base_override
        # Allow OMI_API_KEY to take effect even if the on-disk profile has no key.
        # Validate the prefix here so an obviously-bad env value fails fast with the
        # same friendly UsageError the paste flow uses, instead of bouncing off the
        # API as a cryptic 401.
        env_key = os.environ.get(cfg.ENV_API_KEY)
        if env_key and not profile.api_key:
            profile.auth_method = "api_key"
            profile.api_key = validate_api_key_format(env_key)
        env_base = os.environ.get(cfg.ENV_API_BASE)
        if env_base and not self.api_base_override:
            profile.api_base = env_base
        return profile

    def make_client(self) -> OmiClient:
        return OmiClient(self.get_profile(), verbose=self.verbose)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"omi-cli {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def _root(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON to stdout (machine-readable, agent-friendly)."),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile to use from ~/.omi/config.toml. Falls back to $OMI_PROFILE then 'default'.",
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
        help="Override the API base URL (default: https://api.omi.me).",
        envvar=cfg.ENV_API_BASE,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Log HTTP traffic to stderr."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output (also honors $NO_COLOR)."),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show omi-cli version and exit.",
    ),
) -> None:
    """Root callback: parse global flags, build per-invocation context."""
    config = cfg.load()
    profile_name = cfg.resolve_profile_name(profile, config)

    renderer = Renderer(json_mode=json_output, no_color=no_color, verbose=verbose)
    ctx.obj = AppContext(
        profile_name=profile_name,
        api_base_override=api_base,
        renderer=renderer,
        verbose=verbose,
    )


@app.command(help="Print the omi-cli version.")
def version() -> None:
    typer.echo(f"omi-cli {__version__}")


# ---------------------------------------------------------------------------
# Sub-command registration
# ---------------------------------------------------------------------------

app.add_typer(auth_cmd.app, name="auth", help="Manage authentication: login, logout, status.")
app.add_typer(config_cmd.app, name="config", help="View and modify CLI configuration / profiles.")
app.add_typer(memory_cmd.app, name="memory", help="Memories — facts and learnings about the user.")
app.add_typer(conversation_cmd.app, name="conversation", help="Conversations — captured & processed audio + text.")
app.add_typer(action_item_cmd.app, name="action-item", help="Action items — tasks and follow-ups.")
app.add_typer(goal_cmd.app, name="goal", help="Goals — tracked progress metrics.")


# ---------------------------------------------------------------------------
# Top-level error handler
# ---------------------------------------------------------------------------


def _exit_with_cli_error(error: CliError, renderer: Renderer) -> int:
    renderer.error(error.message, detail=error.detail)
    return error.exit_code


def main() -> None:
    """Module-level entry point that converts CliError into stable exit codes.

    We run Click in non-standalone mode so we can shape the exit codes ourselves.
    The exception ladder, in order of specificity:

    * :class:`CliError` (our own, subclass of ClickException) — already knows how
      to render via the active Renderer; just call ``show()`` and exit with its
      ``exit_code``.
    * Other :class:`click.ClickException` (e.g. ``NoSuchOption`` for a typo'd
      flag) — let Click's default ``show()`` print the friendly usage message,
      then exit with its built-in ``exit_code`` (typically 2 for Click usage).
    * :class:`typer.Exit` — Typer's "clean exit at this code", e.g. from
      ``--version``. Pass through.
    * KeyboardInterrupt / EOFError — Ctrl-C / Ctrl-D. Conventional 130.
    * Anything else — last-chance handler. Print a clean line, exit 1.
    """
    try:
        app(standalone_mode=False)
    except CliError as exc:
        # If the error happens before the root callback ran, ``ctx.obj`` might
        # not exist — fall back to a default Renderer reading the env.
        renderer = Renderer(json_mode=False)
        sys.exit(_exit_with_cli_error(exc, renderer))
    except click.ClickException as exc:
        # Click's own usage errors (unknown flag, missing argument, etc.).
        # Let Click format it the way users expect; honor its exit_code.
        exc.show()
        sys.exit(exc.exit_code)
    except typer.Exit as exc:
        sys.exit(exc.exit_code)
    except (KeyboardInterrupt, EOFError):
        sys.stderr.write("\nAborted.\n")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — last-chance handler
        sys.stderr.write(f"omi: unexpected error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
