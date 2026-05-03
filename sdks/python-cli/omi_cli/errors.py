"""Exception hierarchy and exit-code mapping for omi-cli.

Exit code contract (stable for agent use):

    0  success
    1  usage error (bad flags, missing args, validation)
    2  auth error (no creds, expired token, insufficient scope)
    3  server error (5xx, connection failure)
    4  rate limited (429)
    5  not found (404)

Implementation note: :class:`CliError` extends :class:`click.ClickException` so
Click's runner (and Typer's CliRunner used in tests) handles propagation of the
custom ``exit_code`` natively. Subclasses override :meth:`show` to render via
the active :class:`omi_cli.output.Renderer` when one is reachable on the
current Click context — falling back to plain stderr otherwise.
"""

from __future__ import annotations

import sys
from typing import Optional

import click

# Exit codes — stable contract for scripts and agents.
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_AUTH = 2
EXIT_SERVER = 3
EXIT_RATE_LIMITED = 4
EXIT_NOT_FOUND = 5


class CliError(click.ClickException):
    """Base error raised by omi-cli. Maps to a stable exit code.

    Subclasses set ``exit_code`` to one of the EXIT_* constants. Click's
    runtime reads ``exit_code`` natively when bubbling an exception out of a
    command — no extra wiring needed.
    """

    exit_code: int = EXIT_USAGE

    def __init__(
        self,
        message: str,
        exit_code: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code
        self.detail = detail

    # ``self.message`` is set by ClickException.__init__ — we don't override it
    # because ClickException assigns to ``self.message`` directly.

    def show(self, file: Optional[object] = None) -> None:
        """Render via the AppContext's Renderer when available; else plain stderr."""
        ctx = click.get_current_context(silent=True)
        renderer = getattr(ctx.obj, "renderer", None) if ctx is not None and ctx.obj is not None else None
        if renderer is not None:
            renderer.error(self.message, detail=self.detail)
            return
        # Fallback path — covers the rare case where the error fires before the
        # root callback finished initializing the Renderer.
        target = file if file is not None else sys.stderr
        line = f"omi: {self.message}\n"
        if self.detail:
            line += f"  {self.detail}\n"
        target.write(line)  # type: ignore[union-attr]

    def __str__(self) -> str:
        if self.detail:
            return f"{self.message}: {self.detail}"
        return self.message


class UsageError(CliError):
    exit_code = EXIT_USAGE


class AuthError(CliError):
    exit_code = EXIT_AUTH


class ServerError(CliError):
    exit_code = EXIT_SERVER


class NotFoundError(CliError):
    exit_code = EXIT_NOT_FOUND


class RateLimitError(CliError):
    exit_code = EXIT_RATE_LIMITED

    def __init__(
        self,
        message: str,
        *,
        detail: Optional[str] = None,
        retry_after_seconds: Optional[float] = None,
        policy: Optional[str] = None,
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.retry_after_seconds = retry_after_seconds
        self.policy = policy


def from_status(
    status: int,
    *,
    detail: Optional[str] = None,
    retry_after: Optional[float] = None,
    policy: Optional[str] = None,
) -> CliError:
    """Map an HTTP status code to the appropriate CliError subclass.

    ``detail`` is the server's error message (already extracted from the response
    body). ``retry_after`` and ``policy`` are populated for 429s to give users a
    useful "wait Ns" message.
    """
    if status == 401:
        return AuthError(
            "Authentication failed",
            detail=detail or "Token rejected. Run `omi auth login` to re-authenticate.",
        )
    if status == 403:
        return AuthError(
            "Insufficient permissions",
            detail=detail or "Your API key does not have the required scope for this operation.",
        )
    if status == 404:
        return NotFoundError("Not found", detail=detail)
    if status == 429:
        msg = "Rate limited"
        if policy:
            msg = f"Rate limited ({policy})"
        return RateLimitError(
            msg,
            detail=detail or "Slow down and retry shortly.",
            retry_after_seconds=retry_after,
            policy=policy,
        )
    if 500 <= status < 600:
        return ServerError(
            f"Server error ({status})",
            detail=detail or "The Omi API returned an error. Try again or check status.omi.me.",
        )
    return CliError(f"HTTP {status}", detail=detail, exit_code=EXIT_USAGE)
