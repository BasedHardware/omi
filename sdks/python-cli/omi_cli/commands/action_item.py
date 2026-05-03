"""``omi action-item`` — tasks and follow-ups."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.errors import NotFoundError, UsageError
from omi_cli.output import shorten

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


_LIST_COLUMNS = ["id", "completed", "description", "due_at", "created_at"]


@app.command("list", help="List action items.")
def list_action_items(
    typer_ctx: typer.Context,
    completed: Optional[bool] = typer.Option(None, "--completed/--open", help="Filter by completion."),
    conversation_id: Optional[str] = typer.Option(None, "--conversation-id"),
    start_date: Optional[datetime] = typer.Option(None, "--start-date"),
    end_date: Optional[datetime] = typer.Option(None, "--end-date"),
    limit: int = typer.Option(100, "--limit", min=1, max=500),
    offset: int = typer.Option(0, "--offset", min=0),
) -> None:
    ctx = _ctx(typer_ctx)
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if completed is not None:
        params["completed"] = completed
    if conversation_id is not None:
        params["conversation_id"] = conversation_id
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()

    with ctx.make_client() as client:
        items = client.get("/v1/dev/user/action-items", params=params)

    if ctx.renderer.json_mode:
        ctx.renderer.emit(items)
        return
    rows = []
    for it in items or []:
        rows.append(
            {
                "id": shorten(it.get("id"), 14),
                "completed": it.get("completed"),
                "description": shorten(it.get("description"), 60),
                "due_at": it.get("due_at"),
                "created_at": it.get("created_at"),
            }
        )
    ctx.renderer.emit(rows, columns=_LIST_COLUMNS, title=f"action items (limit={limit})")


@app.command("get", help="Fetch a single action item by ID. (Not directly exposed by the dev API; uses list scan.)")
def get_action_item(
    typer_ctx: typer.Context,
    action_item_id: str = typer.Argument(..., help="Action item ID."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        # Like memories, the dev API has no single-resource GET for action items.
        # Page through up to 5 pages of 200 to find it; beyond that the user
        # probably wants `omi action-item list` directly.
        for offset in range(0, 1000, 200):
            page = client.get("/v1/dev/user/action-items", params={"limit": 200, "offset": offset})
            if not page:
                break
            for item in page:
                if item.get("id") == action_item_id:
                    ctx.renderer.emit(item, title="action item")
                    return
            if len(page) < 200:
                break
    # Exit code 5 (NotFoundError) — same contract as a server-side 404,
    # whether or not the dev API exposed a direct GET for this noun.
    raise NotFoundError(message=f"Action item not found: {action_item_id}")


@app.command("create", help="Create a new action item.")
def create_action_item(
    typer_ctx: typer.Context,
    description: str = typer.Argument(..., help="Action item description (1-500 chars)."),
    completed: bool = typer.Option(False, "--completed/--open"),
    due_at: Optional[datetime] = typer.Option(None, "--due-at", help="ISO datetime."),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {"description": description, "completed": completed}
    if due_at is not None:
        body["due_at"] = due_at.isoformat()
    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/action-items", json_body=body)
    ctx.renderer.success(f"Action item created: [bold]{result.get('id')}[/bold]")
    ctx.renderer.emit(result)


@app.command("update", help="Update an existing action item.")
def update_action_item(
    typer_ctx: typer.Context,
    action_item_id: str = typer.Argument(..., help="Action item ID."),
    description: Optional[str] = typer.Option(None, "--description"),
    completed: Optional[bool] = typer.Option(None, "--completed/--open"),
    due_at: Optional[datetime] = typer.Option(None, "--due-at"),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {}
    if description is not None:
        body["description"] = description
    if completed is not None:
        body["completed"] = completed
    if due_at is not None:
        body["due_at"] = due_at.isoformat()
    if not body:
        raise UsageError(
            message="No fields to update", detail="Provide --description, --completed/--open, or --due-at."
        )
    with ctx.make_client() as client:
        result = client.patch(f"/v1/dev/user/action-items/{action_item_id}", json_body=body)
    ctx.renderer.success(f"Updated action item [bold]{action_item_id}[/bold].")
    ctx.renderer.emit(result)


@app.command("complete", help="Mark an action item as completed (shortcut for `update --completed`).")
def complete_action_item(
    typer_ctx: typer.Context,
    action_item_id: str = typer.Argument(..., help="Action item ID."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        result = client.patch(f"/v1/dev/user/action-items/{action_item_id}", json_body={"completed": True})
    ctx.renderer.success(f"Completed action item [bold]{action_item_id}[/bold].")
    ctx.renderer.emit(result)


@app.command("delete", help="Delete an action item by ID.")
def delete_action_item(
    typer_ctx: typer.Context,
    action_item_id: str = typer.Argument(..., help="Action item ID."),
    confirm: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete action item {action_item_id}?", abort=True)
    with ctx.make_client() as client:
        client.delete(f"/v1/dev/user/action-items/{action_item_id}")
    ctx.renderer.success(f"Deleted action item [bold]{action_item_id}[/bold].")
