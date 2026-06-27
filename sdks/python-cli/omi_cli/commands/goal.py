"""``omi goal`` — tracked progress metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.errors import UsageError
from omi_cli.models import GoalType
from omi_cli.output import shorten

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


_LIST_COLUMNS = ["id", "title", "goal_type", "current_value", "target_value", "unit", "is_active"]


@app.command("list", help="List goals.")
def list_goals(
    typer_ctx: typer.Context,
    limit: int = typer.Option(10, "--limit", min=1, max=100),
    include_inactive: bool = typer.Option(False, "--include-inactive", help="Include inactive/completed goals."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        items = client.get(
            "/v1/dev/user/goals",
            params={"limit": limit, "include_inactive": include_inactive},
        )
    if ctx.renderer.json_mode:
        ctx.renderer.emit(items)
        return
    rows = []
    for g in items or []:
        rows.append(
            {
                "id": shorten(g.get("id"), 14),
                "title": shorten(g.get("title"), 40),
                "goal_type": g.get("goal_type"),
                "current_value": g.get("current_value"),
                "target_value": g.get("target_value"),
                "unit": g.get("unit"),
                "is_active": g.get("is_active"),
            }
        )
    ctx.renderer.emit(rows, columns=_LIST_COLUMNS, title="goals")


@app.command("get", help="Fetch a single goal by ID.")
def get_goal(
    typer_ctx: typer.Context,
    goal_id: str = typer.Argument(..., help="Goal ID."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        result = client.get(f"/v1/dev/user/goals/{goal_id}")
    ctx.renderer.emit(result, title="goal")


@app.command("create", help="Create a new goal. Up to 3 active goals per user.")
def create_goal(
    typer_ctx: typer.Context,
    title: str = typer.Argument(..., help="Goal title (1-500 chars)."),
    target_value: float = typer.Option(..., "--target", help="Target value to achieve."),
    goal_type: GoalType = typer.Option(GoalType.scale, "--type", help="boolean, scale, or numeric."),
    current_value: float = typer.Option(0, "--current", help="Current progress value."),
    min_value: float = typer.Option(0, "--min", help="Minimum scale value."),
    max_value: float = typer.Option(10, "--max", help="Maximum scale value."),
    unit: Optional[str] = typer.Option(None, "--unit", help="Unit label (e.g. 'users', 'points')."),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {
        "title": title,
        "goal_type": goal_type.value,
        "target_value": target_value,
        "current_value": current_value,
        "min_value": min_value,
        "max_value": max_value,
    }
    if unit is not None:
        body["unit"] = unit
    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/goals", json_body=body)
    ctx.renderer.success(f"Goal created: [bold]{result.get('id')}[/bold]")
    ctx.renderer.emit(result)


@app.command("update", help="Update a goal's metadata.")
def update_goal(
    typer_ctx: typer.Context,
    goal_id: str = typer.Argument(..., help="Goal ID."),
    title: Optional[str] = typer.Option(None, "--title"),
    target_value: Optional[float] = typer.Option(None, "--target"),
    current_value: Optional[float] = typer.Option(None, "--current"),
    min_value: Optional[float] = typer.Option(None, "--min"),
    max_value: Optional[float] = typer.Option(None, "--max"),
    unit: Optional[str] = typer.Option(None, "--unit"),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {}
    if title is not None:
        body["title"] = title
    if target_value is not None:
        body["target_value"] = target_value
    if current_value is not None:
        body["current_value"] = current_value
    if min_value is not None:
        body["min_value"] = min_value
    if max_value is not None:
        body["max_value"] = max_value
    if unit is not None:
        body["unit"] = unit
    if not body:
        raise UsageError(
            message="No fields to update", detail="Provide one of --title/--target/--current/--min/--max/--unit."
        )
    with ctx.make_client() as client:
        result = client.patch(f"/v1/dev/user/goals/{goal_id}", json_body=body)
    ctx.renderer.success(f"Updated goal [bold]{goal_id}[/bold].")
    ctx.renderer.emit(result)


@app.command("progress", help="Update only the current_value of a goal (shortcut).")
def update_progress(
    typer_ctx: typer.Context,
    goal_id: str = typer.Argument(..., help="Goal ID."),
    current_value: float = typer.Argument(..., help="New progress value."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        # The progress endpoint takes current_value as a query param.
        result = client.patch(f"/v1/dev/user/goals/{goal_id}/progress", params={"current_value": current_value})
    ctx.renderer.success(f"Updated progress on [bold]{goal_id}[/bold] → {current_value}.")
    ctx.renderer.emit(result)


@app.command("history", help="Fetch progress history for a goal.")
def goal_history(
    typer_ctx: typer.Context,
    goal_id: str = typer.Argument(..., help="Goal ID."),
    days: int = typer.Option(30, "--days", min=1, max=365),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        result = client.get(f"/v1/dev/user/goals/{goal_id}/history", params={"days": days})
    ctx.renderer.emit(result, title=f"goal history (last {days}d)")


@app.command("delete", help="Delete a goal by ID.")
def delete_goal(
    typer_ctx: typer.Context,
    goal_id: str = typer.Argument(..., help="Goal ID."),
    confirm: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete goal {goal_id}?", abort=True)
    with ctx.make_client() as client:
        client.delete(f"/v1/dev/user/goals/{goal_id}")
    ctx.renderer.success(f"Deleted goal [bold]{goal_id}[/bold].")
