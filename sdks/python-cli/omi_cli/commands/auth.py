"""``omi auth`` — login (browser or API key), logout, status, refresh."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional

import typer

from omi_cli import config as cfg
from omi_cli.auth import api_key as api_key_auth
from omi_cli.auth import oauth as oauth_auth
from omi_cli.auth.store import clear_credentials
from omi_cli.client import OmiClient
from omi_cli.errors import AuthError, CliError, UsageError

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    """Type-narrowing accessor for the Typer context object."""
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover — defensive; root callback always sets it
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


@app.command("login", help="Authenticate this profile. Prompts for browser or API key if no flag is given.")
def login(
    typer_ctx: typer.Context,
    api_key_arg: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key (skips the prompt). Visible in shell history — prefer the interactive paste.",
    ),
    browser: bool = typer.Option(
        False,
        "--browser",
        help="Force the Firebase OAuth browser flow.",
    ),
    provider: str = typer.Option(
        "google",
        "--provider",
        help="OAuth provider for --browser: google or apple.",
    ),
) -> None:
    ctx = _ctx(typer_ctx)
    renderer = ctx.renderer

    if browser and api_key_arg:
        raise UsageError(
            message="Pick one auth method",
            detail="`--browser` and `--api-key` are mutually exclusive.",
        )

    # Explicit flags win over the picker.
    if browser:
        return _do_browser_login(ctx, provider=provider)

    if api_key_arg is not None:
        return _do_api_key_login(ctx, api_key_arg)

    # Headless / piped contexts: read API key from stdin (e.g. `omi auth login < key.txt`).
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if not piped:
            raise UsageError(
                message="No input on stdin",
                detail="Pipe an API key in, or run `omi auth login` interactively.",
            )
        return _do_api_key_login(ctx, piped)

    # Interactive picker — the new default UX.
    if not ctx.renderer.json_mode:
        renderer.info("How would you like to log in?")
        renderer.info("  [bold]1[/bold]) Browser  — sign in with Google or Apple via OAuth (recommended for humans)")
        renderer.info("  [bold]2[/bold]) API key  — paste a developer key from app.omi.me (recommended for agents/CI)")
    choice = typer.prompt("Choose 1 or 2", default="1").strip()

    if choice in {"1", "browser", "b"}:
        return _do_browser_login(ctx, provider=provider)
    if choice in {"2", "api-key", "key", "k"}:
        api_key_input = typer.prompt("Paste your Omi developer API key", hide_input=True).strip()
        return _do_api_key_login(ctx, api_key_input)
    raise UsageError(
        message=f"Unrecognized choice: {choice!r}",
        detail="Enter 1 (browser) or 2 (API key).",
    )


def _do_browser_login(ctx: "AppContext", *, provider: str) -> None:
    """Run the OAuth browser flow + verify the resulting Firebase token works."""
    api_base = ctx.api_base_override or ctx.get_profile().api_base
    profile = oauth_auth.login_with_browser(ctx.profile_name, api_base=api_base, provider=provider)

    # Verify the freshly-minted Firebase ID token actually authenticates against
    # the Omi API. If it doesn't, roll back so the user isn't left holding a
    # half-broken OAuth profile.
    try:
        with OmiClient(profile, verbose=ctx.verbose) as client:
            client.get("/v1/dev/user/memories", params={"limit": 1})
    except AuthError as exc:
        clear_credentials(ctx.profile_name)
        raise exc
    except CliError as exc:
        # Insufficient scope / 403 also bubbles as AuthError above. Anything
        # else is a transient network blip — keep the credential, just warn.
        ctx.renderer.warn(
            f"Could not verify the new token right now ({exc.message}). It is stored — try again shortly."
        )

    ctx.renderer.success(f"Logged in via [bold]{provider}[/bold] OAuth as profile [bold]{profile.name}[/bold].")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(
            {
                "profile": profile.name,
                "auth_method": profile.auth_method,
                "api_base": profile.api_base,
                "provider": provider,
            }
        )


def _do_api_key_login(ctx: "AppContext", api_key: str) -> None:
    """Validate, persist, and verify a dev API key."""
    profile = api_key_auth.login_with_api_key(ctx.profile_name, api_key, api_base=ctx.api_base_override)

    # Sanity check on a tolerant endpoint — see the original launch PR's
    # rationale. AuthError → roll back; other CliError → warn and keep.
    try:
        with OmiClient(profile, verbose=ctx.verbose) as client:
            client.get("/v1/dev/user/memories", params={"limit": 1})
    except AuthError as exc:
        clear_credentials(ctx.profile_name)
        raise exc
    except CliError as exc:
        ctx.renderer.warn(f"Could not verify the key right now ({exc.message}). It is stored — try again shortly.")

    ctx.renderer.success(f"Logged in as profile [bold]{profile.name}[/bold] ({profile.masked_credential()}).")
    if ctx.renderer.json_mode:
        ctx.renderer.emit({"profile": profile.name, "auth_method": profile.auth_method, "api_base": profile.api_base})


@app.command("logout", help="Clear credentials for the active profile.")
def logout(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    cleared = clear_credentials(ctx.profile_name)
    if cleared:
        ctx.renderer.success(f"Cleared credentials for profile [bold]{ctx.profile_name}[/bold].")
    else:
        ctx.renderer.warn(f"Profile [bold]{ctx.profile_name}[/bold] was not authenticated.")
    if ctx.renderer.json_mode:
        ctx.renderer.emit({"profile": ctx.profile_name, "logged_out": cleared})


@app.command("status", help="Show the auth state of the active profile.")
def status(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    profile = ctx.get_profile()
    payload: dict[str, object] = {
        "profile": profile.name,
        "authenticated": profile.is_authenticated(),
        "auth_method": profile.auth_method,
        "api_base": profile.api_base,
        "credential": profile.masked_credential(),
    }
    if profile.auth_method == "oauth" and profile.id_token_expires_at:
        # Surface expiry so users can tell if the auto-refresh has been keeping up.
        payload["id_token_expires_at"] = profile.id_token_expires_at
    ctx.renderer.emit(payload, title="omi auth status")


@app.command("whoami", help="Resolve the current credential against the API and display identity info.")
def whoami(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    # The public dev surface doesn't expose a /me endpoint, but a memories list
    # round-trip with the credential confirms the credential is alive and
    # identifies the user implicitly (the count belongs to *this* user).
    with ctx.make_client() as client:
        memories = client.get("/v1/dev/user/memories", params={"limit": 1})
    payload = {
        "profile": ctx.profile_name,
        "credential": ctx.get_profile().masked_credential(),
        "auth_method": ctx.get_profile().auth_method,
        "api_base": ctx.get_profile().api_base,
        "owns_memories": isinstance(memories, list),
    }
    ctx.renderer.emit(payload, title="omi whoami")


@app.command("refresh", help="Force-refresh the OAuth ID token (no-op for API-key profiles).")
def refresh(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    profile = ctx.get_profile()
    if profile.auth_method != "oauth":
        raise UsageError(
            message="Nothing to refresh",
            detail=(
                f"Profile '{profile.name}' uses API-key auth — there is no token to refresh. "
                "Rotate keys in the Omi web app if needed."
            ),
        )
    oauth_auth.refresh_id_token(profile.name)
    ctx.renderer.success(f"Refreshed Firebase ID token for profile [bold]{profile.name}[/bold].")


def _ensure_authenticated(profile: cfg.Profile) -> None:  # pragma: no cover — utility for sibling commands
    if not profile.is_authenticated():
        raise UsageError(
            message="Not authenticated",
            detail=f"Profile '{profile.name}' has no credentials. Run `omi auth login`.",
        )
