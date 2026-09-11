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


@app.command(
    "create", help="Create a new goal. Up to 3 active goals per user. Omit all metric options for a qualitative goal."
)
def create_goal(
    typer_ctx: typer.Context,
    title: str = typer.Argument(..., help="Goal title (1-500 chars)."),
    target_value: Optional[float] = typer.Option(
        None, "--target", help="Target value to achieve. Omit for qualitative goals."
    ),
    goal_type: Optional[GoalType] = typer.Option(
        None, "--type", help="boolean, scale, or numeric. Omit for qualitative goals."
    ),
    current_value: Optional[float] = typer.Option(None, "--current", help="Current progress value."),
    min_value: Optional[float] = typer.Option(None, "--min", help="Minimum scale value."),
    max_value: Optional[float] = typer.Option(None, "--max", help="Maximum scale value."),
    unit: Optional[str] = typer.Option(
        None, "--unit", help="Unit label (e.g. 'users', 'points'). Requires a metric option such as --target."
    ),
) -> None:
    ctx = _ctx(typer_ctx)
    has_metrics = any(value is not None for value in (target_value, goal_type, current_value, min_value, max_value))
    if unit is not None and not has_metrics:
        # The backend only persists ``unit`` on metric-backed goals; sending it on a
        # qualitative goal would silently drop it, so reject the combination instead.
        raise UsageError(
            message="--unit requires a metric goal",
            detail="Add a metric option such as --target, or drop --unit to create a qualitative goal.",
        )
    if has_metrics and target_value is None:
        # ``--target`` was historically required for every metric goal. Partial metric
        # invocations must not fabricate a target-less scale goal, so keep rejecting them.
        raise UsageError(
            message="--target is required when using metric options",
            detail="Pass --target, or omit --type/--current/--min/--max/--unit to create a qualitative goal.",
        )
    body: dict[str, object] = {"title": title}
    if unit is not None:
        body["unit"] = unit
    if has_metrics:
        # Metric goal: keep the historical defaults for options the caller did not set.
        body["goal_type"] = (goal_type if goal_type is not None else GoalType.scale).value
        body["target_value"] = target_value
        body["current_value"] = current_value if current_value is not None else 0
        body["min_value"] = min_value if min_value is not None else 0
        body["max_value"] = max_value if max_value is not None else 10
    # No metric options given: send a qualitative goal (the API supports omitting all metric fields).
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
    clear_unit: bool = typer.Option(False, "--clear-unit", help="Remove the existing unit label."),
    clear_min: bool = typer.Option(False, "--clear-min", help="Remove the existing minimum bound."),
    clear_max: bool = typer.Option(False, "--clear-max", help="Remove the existing maximum bound."),
) -> None:
    ctx = _ctx(typer_ctx)
    if clear_unit and unit is not None:
        raise UsageError(message="Conflicting options", detail="--unit and --clear-unit are mutually exclusive.")
    if clear_min and min_value is not None:
        raise UsageError(message="Conflicting options", detail="--min and --clear-min are mutually exclusive.")
    if clear_max and max_value is not None:
        raise UsageError(message="Conflicting options", detail="--max and --clear-max are mutually exclusive.")
    body: dict[str, object] = {}
    if title is not None:
        body["title"] = title
    if target_value is not None:
        body["target_value"] = target_value
    if current_value is not None:
        body["current_value"] = current_value
    if clear_min:
        body["min_value"] = None
    elif min_value is not None:
        body["min_value"] = min_value
    if clear_max:
        body["max_value"] = None
    elif max_value is not None:
        body["max_value"] = max_value
    if clear_unit:
        body["unit"] = None
    elif unit is not None:
        body["unit"] = unit
    if not body:
        raise UsageError(
            message="No fields to update",
            detail=(
                "Provide one of --title/--target/--current/--min/--max/--unit/"
                "--clear-unit/--clear-min/--clear-max."
            ),
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
        result = client.delete(f"/v1/dev/user/goals/{goal_id}")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
    ctx.renderer.success(f"Deleted goal [bold]{goal_id}[/bold].")
