"""``omi config`` — view and edit configuration / profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from omi_cli import config as cfg
from omi_cli.errors import UsageError

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)
profile_app = typer.Typer(no_args_is_help=True, help="Manage named profiles.")
app.add_typer(profile_app, name="profile")


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


@app.command("show", help="Print the resolved configuration (credentials masked).")
def show(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    config = ctx.load_config()
    profiles = []
    for name, profile in sorted(config.profiles.items()):
        profiles.append(
            {
                "name": name,
                "active": name == config.active_profile,
                "auth_method": profile.auth_method,
                "api_base": profile.api_base,
                "credential": profile.masked_credential(),
            }
        )
    payload = {
        "config_path": str(config.path),
        "active_profile": config.active_profile,
        "profiles": profiles,
    }
    ctx.renderer.emit(payload, title="omi config show")


@app.command("path", help="Print the on-disk config path.")
def path(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    config = ctx.load_config()
    if ctx.renderer.json_mode:
        ctx.renderer.emit({"path": str(config.path)})
    else:
        typer.echo(str(config.path))


_SETTABLE_KEYS = {"api_base"}


@app.command("set", help="Set a per-profile config value. Keys: api_base.")
def set_value(
    typer_ctx: typer.Context,
    key: str = typer.Argument(..., help=f"Config key to set. One of: {sorted(_SETTABLE_KEYS)}"),
    value: str = typer.Argument(..., help="New value."),
) -> None:
    ctx = _ctx(typer_ctx)
    if key not in _SETTABLE_KEYS:
        raise UsageError(
            message=f"Unknown config key '{key}'",
            detail=f"Settable keys: {sorted(_SETTABLE_KEYS)}",
        )
    config = ctx.load_config()
    profile = config.get_profile(ctx.profile_name)
    if key == "api_base":
        profile.api_base = value.rstrip("/")
    config.set_profile(profile)
    cfg.save(config)
    ctx.renderer.success(f"Set [bold]{key}[/bold] = {value} on profile [bold]{profile.name}[/bold].")


@profile_app.command("list", help="List all configured profiles.")
def profile_list(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    config = ctx.load_config()
    rows = []
    for name in config.list_profiles() or [config.active_profile]:
        profile = config.get_profile(name)
        rows.append(
            {
                "name": name,
                "active": name == config.active_profile,
                "auth_method": profile.auth_method or "(none)",
                "api_base": profile.api_base,
                "credential": profile.masked_credential(),
            }
        )
    ctx.renderer.emit(rows, columns=["name", "active", "auth_method", "api_base", "credential"], title="profiles")


@profile_app.command("use", help="Switch the active profile.")
def profile_use(
    typer_ctx: typer.Context,
    name: str = typer.Argument(..., help="Profile name to make active."),
) -> None:
    ctx = _ctx(typer_ctx)
    config = ctx.load_config()
    if name not in config.profiles:
        # Allow switching to a brand-new (yet-unconfigured) profile so users can
        # bootstrap a fresh context: `omi config profile use work && omi auth login`
        config.profiles[name] = cfg.Profile(name=name)
    config.active_profile = name
    cfg.save(config)
    ctx.renderer.success(f"Active profile: [bold]{name}[/bold].")


@profile_app.command("delete", help="Delete a profile and its credentials.")
def profile_delete(
    typer_ctx: typer.Context,
    name: str = typer.Argument(..., help="Profile name to delete."),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    ctx = _ctx(typer_ctx)
    config = ctx.load_config()
    if name not in config.profiles:
        raise UsageError(message=f"No such profile: '{name}'")
    if not confirm:
        typer.confirm(f"Delete profile '{name}'?", abort=True)
    config.delete_profile(name)
    cfg.save(config)
    ctx.renderer.success(f"Deleted profile [bold]{name}[/bold].")
