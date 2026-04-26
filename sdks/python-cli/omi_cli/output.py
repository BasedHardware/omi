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
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from rich.console import Console
from rich.table import Table


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

        if isinstance(data, list):
            self._emit_table(data, columns=columns, title=title)
        elif isinstance(data, Mapping):
            self._emit_mapping(data, title=title)
        else:
            # Scalars or anything else — just print.
            self._stdout.print(data)

    def _emit_json(self, data: Any) -> None:
        # Use sys.stdout directly to avoid Rich coloring/wrapping the JSON.
        sys.stdout.write(json.dumps(data, default=_json_default, indent=2, sort_keys=False))
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _emit_table(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        columns: Optional[Sequence[str]],
        title: Optional[str],
    ) -> None:
        if not rows:
            self._stdout.print("[dim](no results)[/dim]")
            return

        # Pick columns. Caller-supplied wins; otherwise use the keys of the first row.
        cols = list(columns) if columns else list(rows[0].keys())

        table = Table(title=title, show_lines=False, header_style="bold")
        for col in cols:
            table.add_column(col)
        for row in rows:
            table.add_row(*[_stringify(row.get(c)) for c in cols])
        self._stdout.print(table)

    def _emit_mapping(self, mapping: Mapping[str, Any], *, title: Optional[str]) -> None:
        table = Table(title=title, show_header=False, show_lines=False, box=None)
        table.add_column("field", style="bold")
        table.add_column("value")
        for k, v in mapping.items():
            table.add_row(k, _stringify(v))
        self._stdout.print(table)

    # ------------------------------------------------------------------
    # Stderr (status/messages)
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:
        if self.json_mode:
            return  # silence in JSON mode — keep stderr clean for piping
        self._stderr.print(message)

    def success(self, message: str) -> None:
        if self.json_mode:
            return
        self._stderr.print(f"[green]✓[/green] {message}")

    def warn(self, message: str) -> None:
        if self.json_mode:
            return
        self._stderr.print(f"[yellow]![/yellow] {message}")

    def error(self, message: str, *, detail: Optional[str] = None) -> None:
        # Errors are emitted in BOTH modes — JSON mode keeps stdout pristine,
        # but error messages still need to reach the user via stderr.
        if self.json_mode:
            payload: dict[str, Any] = {"error": message}
            if detail:
                payload["detail"] = detail
            self._stderr.print(json.dumps(payload))
        else:
            line = f"[red]✗[/red] {message}"
            if detail:
                line += f"\n  [dim]{detail}[/dim]"
            self._stderr.print(line)

    def debug(self, message: str) -> None:
        if not self.verbose:
            return
        self._stderr.print(f"[dim][debug][/dim] {message}")


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
