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
from typer.main import get_command

from omi_cli import __version__
from omi_cli import config as cfg
from omi_cli.auth.api_key import validate_api_key_format
from omi_cli.client import OmiClient
from omi_cli.commands import action_item as action_item_cmd
from omi_cli.commands import auth as auth_cmd
from omi_cli.commands import config as config_cmd
from omi_cli.commands import conversation as conversation_cmd
from omi_cli.commands import goal as goal_cmd
from omi_cli.commands import local as local_cmd
from omi_cli.commands import memory as memory_cmd
from omi_cli.errors import EXIT_USAGE, CliError
from omi_cli.local_client import LocalOmiClient
from omi_cli.output import Renderer, current_renderer


@click.pass_context
def _finish_output(ctx: click.Context, /, result: object, **options: object) -> object:
    """Every successfully completed command owes JSON callers one result."""
    if not isinstance(result, int) or result == 0:
        ctx.obj.renderer.finish()
    return result


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
    result_callback=_finish_output,
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

    def make_local_client(self) -> LocalOmiClient:
        profile = self.get_profile()
        local_api_url = os.environ.get(cfg.ENV_LOCAL_API_URL) or profile.local_api_url
        local_token = os.environ.get(cfg.ENV_LOCAL_TOKEN) or profile.local_token
        return LocalOmiClient(api_url=local_api_url or "", token=local_token or "", verbose=self.verbose)


def _emit_version(renderer: Renderer) -> None:
    renderer.emit({"version": __version__} if renderer.json_mode else f"omi-cli {__version__}")


def _version_callback(ctx: typer.Context, value: bool) -> None:
    if value and not ctx.resilient_parsing:
        _emit_version(current_renderer())
        raise typer.Exit(code=0)


@app.callback()
def _root(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False, "--json", is_eager=True, help="Emit JSON to stdout (machine-readable, agent-friendly)."
    ),
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
    renderer = (
        ctx.obj
        if isinstance(ctx.obj, Renderer)
        else Renderer(json_mode=json_output, no_color=no_color, verbose=verbose)
    )
    config = cfg.load()
    profile_name = cfg.resolve_profile_name(profile, config)

    ctx.obj = AppContext(
        profile_name=profile_name,
        api_base_override=api_base,
        renderer=renderer,
        verbose=verbose,
    )


@app.command(help="Print the omi-cli version.")
def version() -> None:
    _emit_version(current_renderer())


@app.command(help="Ask a natural-language question, answered from your own Omi conversations.")
def ask(
    typer_ctx: typer.Context,
    question: str = typer.Argument(..., help='Your question, e.g. "what did I decide about pricing last week?"'),
    limit: int = typer.Option(5, "--limit", min=1, max=10, help="How many conversations to ground the answer on."),
    timezone: str = typer.Option("UTC", "--timezone", help="IANA timezone for resolving relative dates."),
) -> None:
    ctx: AppContext = typer_ctx.obj
    with ctx.make_client() as client:
        result = client.post(
            "/v1/dev/user/ask",
            json_body={"question": question, "limit": limit, "timezone": timezone},
        )
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
        return
    payload = result or {}
    lines = [payload.get("answer", "")]
    sources = payload.get("sources") or []
    if sources:
        lines.append("\nSources:")
        for s in sources:
            lines.append(f"  - {s.get('title') or 'Untitled'} ({s.get('created_at') or ''})  [{s.get('id')}]")
    ctx.renderer.emit("\n".join(lines))


# ---------------------------------------------------------------------------
# Sub-command registration
# ---------------------------------------------------------------------------

app.add_typer(auth_cmd.app, name="auth", help="Manage authentication: login, logout, status.")
app.add_typer(config_cmd.app, name="config", help="View and modify CLI configuration / profiles.")
app.add_typer(memory_cmd.app, name="memory", help="Memories — facts and learnings about the user.")
app.add_typer(conversation_cmd.app, name="conversation", help="Conversations — captured & processed audio + text.")
app.add_typer(action_item_cmd.app, name="action-item", help="Action items — tasks and follow-ups.")
app.add_typer(goal_cmd.app, name="goal", help="Goals — tracked progress metrics.")
app.add_typer(local_cmd.app, name="local", help="Local Omi Desktop API tools.")


# ---------------------------------------------------------------------------
# Top-level error handler
# ---------------------------------------------------------------------------


def _exit_with_cli_error(error: CliError, renderer: Renderer) -> int:
    renderer.error(error.message, detail=error.detail, extra=error.extra)
    return error.exit_code


def _require_subcommands(command: click.Command) -> None:
    """In JSON mode, incomplete commands are usage errors instead of implicit help."""
    if isinstance(command, click.Group):
        command.no_args_is_help = False
        for child in command.commands.values():
            _require_subcommands(child)


def main() -> None:
    """One public output/error boundary for the console and module entrypoints.

    A resilient parse of the declared global options chooses the output mode
    before normal parsing can fail. It does not invoke commands, load config,
    or run eager actions. Click then performs its normal strict invocation with
    that Renderer, which remains available after Click unwinds its contexts. We
    run Click in non-standalone mode so every exception uses this same boundary.
    """
    renderer = Renderer()
    try:
        command = get_command(app)
        args = sys.argv[1:]
        with command.make_context("omi", list(args), resilient_parsing=True, ignore_unknown_options=True) as ctx:
            renderer = Renderer(
                json_mode=bool(ctx.params.get("json_output", False)),
                no_color=bool(ctx.params.get("no_color", False)),
                verbose=bool(ctx.params.get("verbose", False)),
            )
        if renderer.json_mode:
            _require_subcommands(command)
        result = command.main(prog_name="omi", standalone_mode=False, obj=renderer)
        if isinstance(result, int):
            sys.exit(result)
    except CliError as exc:
        sys.exit(_exit_with_cli_error(exc, renderer))
    except click.ClickException as exc:
        message = exc.format_message()
        if message:
            if isinstance(exc, click.UsageError) and exc.ctx is not None:
                renderer.info(exc.ctx.get_usage())
            renderer.error(message)
        else:
            # Rich may already have printed implicit help. Preserve its text
            # interface and status instead of adding an empty error message.
            sys.exit(exc.exit_code)
        sys.exit(EXIT_USAGE if isinstance(exc, click.UsageError) else exc.exit_code)
    except typer.Exit as exc:
        sys.exit(exc.exit_code)
    except (click.Abort, KeyboardInterrupt, EOFError):
        renderer.error("Aborted.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — last-chance handler
        renderer.error(
            "Unexpected error", detail=f"{type(exc).__name__}. Please report this with your omi-cli version."
        )
        sys.exit(EXIT_USAGE)


if __name__ == "__main__":
    main()
