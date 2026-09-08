"""Output rendering for omi-cli.

Two modes:

* **Pretty (default):** Rich tables on a TTY; respects ``NO_COLOR`` env var and
  ``--no-color`` flag. Errors go to stderr.
* **JSON (`--json`):** machine-readable JSON to stdout. Nothing else writes to
  stdout in JSON mode — this is the agent contract.

The :class:`Renderer` carries the active mode through the call tree.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text


def _no_color_env() -> bool:
    """Return True if NO_COLOR or NOMI_NO_COLOR is set in the environment.

    Standard ``NO_COLOR`` (https://no-color.org) takes precedence; the
    ``OMI_NO_COLOR`` form is provided as an Omi-specific override.
    """
    if os.environ.get("NO_COLOR"):
        return True
    if os.environ.get("OMI_NO_COLOR"):
        return True
    return False


@dataclass
class Renderer:
    """Stateful output sink. One instance per CLI invocation, attached to the Typer context."""

    json_mode: bool = False
    no_color: bool = False
    verbose: bool = False
    _has_json_result: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        # stderr console for messages and errors. In JSON mode, this is the only console
        # we ever write to (stdout is reserved for the JSON payload).
        force_terminal = None if not self.no_color else False
        self._stderr = Console(
            stderr=True,
            no_color=self.no_color or _no_color_env(),
            force_terminal=force_terminal,
            highlight=False,
        )
        self._stdout = Console(
            no_color=self.no_color or _no_color_env(),
            force_terminal=force_terminal,
            highlight=False,
        )

    # ------------------------------------------------------------------
    # Stdout (data path)
    # ------------------------------------------------------------------

    def emit(self, data: Any, *, columns: Optional[Sequence[str]] = None, title: Optional[str] = None) -> None:
        """Render an API result. JSON mode → JSON to stdout. Pretty mode → Rich table."""
        if self.json_mode:
            self._emit_json(data)
            return

        if isinstance(data, list) and all(isinstance(row, Mapping) for row in data):
            self._emit_table(data, columns=columns, title=title)
        elif isinstance(data, Mapping):
            self._emit_mapping(data, title=title)
        else:
            # Scalars or anything else — print as literal text, not markup.
            self._stdout.print(Text(_stringify(data)), soft_wrap=True)

    def _emit_json(self, data: Any) -> None:
        # Use sys.stdout directly to avoid Rich coloring/wrapping the JSON.
        sys.stdout.write(json.dumps(data, default=_json_default, indent=2, sort_keys=False))
        sys.stdout.write("\n")
        sys.stdout.flush()
        self._has_json_result = True

    def finish(self) -> None:
        """Complete a successful invocation, including commands with no result body."""
        if self.json_mode and not self._has_json_result:
            self._emit_json(None)

    def complete(self, data: Any, *, message: str) -> None:
        """Emit a completed command's JSON result or its human success message."""
        if self.json_mode:
            self._emit_json(data)
        else:
            self.success(message)

    def _emit_table(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        columns: Optional[Sequence[str]],
        title: Optional[str],
    ) -> None:
        if not rows:
            self._stdout.print(Text("(no results)", style="dim"))
            return

        # Pick columns. Caller-supplied wins; otherwise use the keys of the first row.
        cols = list(columns) if columns else list(rows[0].keys())

        table = Table(title=Text(title) if title is not None else None, show_lines=False, header_style="bold")
        for col in cols:
            table.add_column(Text(str(col)))
        for row in rows:
            table.add_row(*[Text(_stringify(row.get(c))) for c in cols])
        self._stdout.print(table)

    def _emit_mapping(self, mapping: Mapping[str, Any], *, title: Optional[str]) -> None:
        table = Table(title=Text(title) if title is not None else None, show_header=False, show_lines=False, box=None)
        table.add_column("field", style="bold")
        table.add_column("value")
        for k, v in mapping.items():
            table.add_row(Text(str(k)), Text(_stringify(v)))
        self._stdout.print(table)

    # ------------------------------------------------------------------
    # Stderr (status/messages)
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:
        if self.json_mode:
            return  # silence in JSON mode — keep stderr clean for piping
        self._stderr.print(Text(message), soft_wrap=True)

    def success(self, message: str) -> None:
        if self.json_mode:
            return
        self._stderr.print(Text.assemble(("✓", "green"), f" {message}"), soft_wrap=True)

    def warn(self, message: str) -> None:
        if self.json_mode:
            return
        self._stderr.print(Text.assemble(("!", "yellow"), f" {message}"), soft_wrap=True)

    def error(self, message: str, *, detail: Optional[str] = None, extra: Optional[Mapping[str, Any]] = None) -> None:
        # Errors are emitted in BOTH modes — JSON mode keeps stdout pristine,
        # but error messages still need to reach the user via stderr.
        if self.json_mode:
            payload: dict[str, Any] = {"error": message}
            if detail:
                payload["detail"] = detail
            if extra:
                payload.update(dict(extra))
            self._emit_diagnostic(payload)
        else:
            # Error text can include server responses and user input. Apply
            # our decoration to Text spans, without parsing that data as markup.
            line = Text()
            line.append("✗", style="red")
            line.append(f" {message}")
            if detail:
                line.append(f"\n  {detail}", style="dim")
            if extra:
                for key, value in extra.items():
                    line.append(f"\n  {key}: {_stringify(value)}", style="dim")
            self._stderr.print(line, soft_wrap=True)

    def debug(self, message: str) -> None:
        if not self.verbose:
            return
        if self.json_mode:
            self._emit_diagnostic({"debug": message})
        else:
            self._stderr.print(Text.assemble(("[debug]", "dim"), f" {message}"), soft_wrap=True)

    def _emit_diagnostic(self, payload: Mapping[str, Any]) -> None:
        sys.stderr.write(json.dumps(payload, default=_json_default) + "\n")
        sys.stderr.flush()

    def confirm(self, message: str, *, yes: bool = False) -> None:
        """Keep interactive prompts out of machine output and require explicit consent."""
        if yes:
            return
        from omi_cli.errors import UsageError

        if self.json_mode:
            raise UsageError(
                message="Confirmation required",
                detail="Pass --yes to confirm this operation in JSON mode.",
            )
        if not click.confirm(message, err=True):
            raise UsageError(message="Cancelled")


def current_renderer(*, verbose: bool = False) -> Renderer:
    """Use the invocation's output sink, including before the root callback runs.

    Helpers such as HTTP diagnostics and browser-login progress use this same
    boundary. Calls outside the CLI retain human output by default.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is not None:
        if isinstance(ctx.obj, Renderer):
            return ctx.obj
        renderer = getattr(ctx.obj, "renderer", None)
        if isinstance(renderer, Renderer):
            return renderer
        params = ctx.find_root().params
        return Renderer(
            json_mode=bool(params.get("json_output", False)),
            no_color=bool(params.get("no_color", False)),
            verbose=bool(params.get("verbose", verbose)),
        )
    return Renderer(verbose=verbose)


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, (datetime,)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return ", ".join(_stringify(x) for x in v)
    if isinstance(v, Mapping):
        return json.dumps(v, default=_json_default, sort_keys=False)
    return str(v)


def _json_default(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "model_dump"):  # pydantic v2
        return v.model_dump()
    if hasattr(v, "dict"):  # pydantic v1 fallback
        return v.dict()
    raise TypeError(f"Object of type {type(v).__name__} is not JSON serializable")


def shorten(value: Optional[str], width: int = 60) -> str:
    """Truncate a string to ``width`` chars with an ellipsis. Used for table cells."""
    if not value:
        return ""
    s = str(value)
    if len(s) <= width:
        return s
    return s[: max(width - 1, 1)] + "…"


def coalesce_rows(items: Iterable[Any]) -> list[dict[str, Any]]:
    """Coerce a list of pydantic models or dicts into a list of dicts. Convenience for renderers."""
    out: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif isinstance(item, Mapping):
            out.append(dict(item))
        else:
            out.append({"value": item})
    return out
