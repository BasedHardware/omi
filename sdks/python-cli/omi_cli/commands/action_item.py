"""``omi action-item`` — tasks and follow-ups."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.datetime_options import ISO_DATETIME_FORMATS
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
    start_date: Optional[datetime] = typer.Option(None, "--start-date", formats=ISO_DATETIME_FORMATS),
    end_date: Optional[datetime] = typer.Option(None, "--end-date", formats=ISO_DATETIME_FORMATS),
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
        # Search until the item is found or the API exhausts the result set.
        # A fixed page cap would report existing older items as not found.
        page_size = 200
        offset = 0
        while True:
            page = client.get("/v1/dev/user/action-items", params={"limit": page_size, "offset": offset})
            if not page:
                break
            for item in page:
                if item.get("id") == action_item_id:
                    ctx.renderer.emit(item, title="action item")
                    return
            if len(page) < page_size:
                break
            offset += page_size
    # Exit code 5 (NotFoundError) — same contract as a server-side 404,
    # whether or not the dev API exposed a direct GET for this noun.
    raise NotFoundError(message=f"Action item not found: {action_item_id}")


@app.command("create", help="Create a new action item.")
def create_action_item(
    typer_ctx: typer.Context,
    description: str = typer.Argument(..., help="Action item description (1-500 chars)."),
    completed: bool = typer.Option(False, "--completed/--open"),
    due_at: Optional[datetime] = typer.Option(None, "--due-at", formats=ISO_DATETIME_FORMATS, help="ISO datetime."),
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
    due_at: Optional[datetime] = typer.Option(None, "--due-at", formats=ISO_DATETIME_FORMATS),
    clear_due_at: bool = typer.Option(False, "--clear-due-at", help="Remove the due date."),
) -> None:
    ctx = _ctx(typer_ctx)
    if clear_due_at and due_at is not None:
        raise UsageError(message="Conflicting options", detail="--due-at and --clear-due-at are mutually exclusive.")
    body: dict[str, object] = {}
    if description is not None:
        body["description"] = description
    if completed is not None:
        body["completed"] = completed
    if clear_due_at:
        body["due_at"] = None
    elif due_at is not None:
        body["due_at"] = due_at.isoformat()
    if not body:
        raise UsageError(
            message="No fields to update",
            detail="Provide --description, --completed/--open, or --due-at/--clear-due-at.",
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
        result = client.delete(f"/v1/dev/user/action-items/{action_item_id}")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
    ctx.renderer.success(f"Deleted action item [bold]{action_item_id}[/bold].")
