"""``omi daily-summary`` — stored daily recaps."""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.errors import UsageError
from omi_cli.output import shorten

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> AppContext:
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


def _validate_date(value: str, flag: str) -> None:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise UsageError(
            message="Invalid date format",
            detail=f"{flag} must be in YYYY-MM-DD format (got '{value}').",
        )
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise UsageError(
            message="Invalid calendar date",
            detail=f"{flag} is not a valid calendar date: {exc}",
        ) from exc


_LIST_COLUMNS = ["id", "date", "day_emoji", "headline", "created_at"]


@app.command("list", help="List stored daily summaries.")
def list_daily_summaries(
    typer_ctx: typer.Context,
    limit: int = typer.Option(30, "--limit", min=1, max=100, help="Number of daily summaries to return (1-100)."),
    offset: int = typer.Option(0, "--offset", min=0, help="Number of daily summaries to skip (>=0)."),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="Filter summaries on or after date (YYYY-MM-DD)."),
    end_date: Optional[str] = typer.Option(None, "--end-date", help="Filter summaries on or before date (YYYY-MM-DD)."),
) -> None:
    ctx = _ctx(typer_ctx)
    if start_date is not None:
        _validate_date(start_date, "--start-date")
    if end_date is not None:
        _validate_date(end_date, "--end-date")

    params: dict[str, object] = {"limit": limit, "offset": offset}
    if start_date is not None:
        params["start_date"] = start_date
    if end_date is not None:
        params["end_date"] = end_date

    with ctx.make_client() as client:
        data = client.get("/v1/dev/user/daily-summaries", params=params)

    if ctx.renderer.json_mode:
        ctx.renderer.emit(data)
        return

    items = data.get("summaries", []) if isinstance(data, dict) else (data or [])
    rows = []
    for s in items:
        rows.append(
            {
                "id": shorten(s.get("id"), 14),
                "date": s.get("date") or "",
                "day_emoji": s.get("day_emoji") or "",
                "headline": shorten(s.get("headline") or s.get("overview") or "", 45),
                "created_at": shorten(str(s.get("created_at") or ""), 19),
            }
        )
    ctx.renderer.emit(rows, columns=_LIST_COLUMNS, title="daily summaries")


@app.command("get", help="Fetch a single stored daily summary by ID.")
def get_daily_summary(
    typer_ctx: typer.Context,
    summary_id: str = typer.Argument(..., help="Daily summary ID."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        result = client.get(f"/v1/dev/user/daily-summaries/{summary_id}")
    ctx.renderer.emit(result, title="daily summary")
