"""``omi memory`` — facts and learnings about the user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.errors import NotFoundError, UsageError
from omi_cli.models import MemoryCategory, MemoryVisibility
from omi_cli.output import shorten

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


_LIST_COLUMNS = ["id", "category", "visibility", "content", "tags", "created_at"]


@app.command("list", help="List memories.")
def list_memories(
    typer_ctx: typer.Context,
    limit: int = typer.Option(25, "--limit", min=1, max=200, help="Max items to return."),
    offset: int = typer.Option(0, "--offset", min=0, help="Pagination offset."),
    categories: Optional[str] = typer.Option(
        None,
        "--categories",
        help="Comma-separated category filter (e.g. 'work,skills').",
    ),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        items = client.get(
            "/v1/dev/user/memories",
            params={"limit": limit, "offset": offset, "categories": categories},
        )
    if ctx.renderer.json_mode:
        ctx.renderer.emit(items)
        return
    rows = []
    for m in items or []:
        rows.append(
            {
                "id": shorten(m.get("id"), 14),
                "category": m.get("category"),
                "visibility": m.get("visibility"),
                "content": shorten(m.get("content"), 60),
                "tags": ", ".join(m.get("tags") or []),
                "created_at": m.get("created_at"),
            }
        )
    ctx.renderer.emit(rows, columns=_LIST_COLUMNS, title=f"memories (limit={limit})")


@app.command("get", help="Fetch a single memory by ID.")
def get_memory(
    typer_ctx: typer.Context,
    memory_id: str = typer.Argument(..., help="Memory ID."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        # The dev API exposes list+search but no single-resource read for memories;
        # implement get-by-id by listing with a filter and matching client-side.
        # We page in chunks until we find it or exhaust the user's memories.
        page_size = 100
        offset = 0
        while True:
            page = client.get("/v1/dev/user/memories", params={"limit": page_size, "offset": offset})
            if not page:
                # Exit code 5 — preserves the documented "not found" agent contract
                # whether the resource is missing server-side (HTTP 404) or absent
                # from the client-side scan we do here.
                raise NotFoundError(message=f"Memory not found: {memory_id}")
            for item in page:
                if item.get("id") == memory_id:
                    ctx.renderer.emit(item, title="memory")
                    return
            if len(page) < page_size:
                raise NotFoundError(message=f"Memory not found: {memory_id}")
            offset += page_size


@app.command("create", help="Create a new memory.")
def create_memory(
    typer_ctx: typer.Context,
    content: str = typer.Argument(..., help="Memory content (1-500 chars)."),
    category: Optional[MemoryCategory] = typer.Option(None, "--category", help="Category. Auto-detected if omitted."),
    visibility: MemoryVisibility = typer.Option(MemoryVisibility.private, "--visibility", help="public or private."),
    tag: list[str] = typer.Option([], "--tag", help="Tag (repeat for multiple)."),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {"content": content, "visibility": visibility.value, "tags": tag}
    if category is not None:
        body["category"] = category.value
    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/memories", json_body=body)
    ctx.renderer.success(f"Memory created: [bold]{result.get('id')}[/bold]")
    ctx.renderer.emit(result, title="memory")


@app.command("update", help="Update an existing memory.")
def update_memory(
    typer_ctx: typer.Context,
    memory_id: str = typer.Argument(..., help="Memory ID."),
    content: Optional[str] = typer.Option(None, "--content", help="New content."),
    category: Optional[MemoryCategory] = typer.Option(None, "--category", help="New category."),
    visibility: Optional[MemoryVisibility] = typer.Option(None, "--visibility", help="public or private."),
    tag: Optional[list[str]] = typer.Option(None, "--tag", help="Replace tags (repeat for multiple)."),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {}
    if content is not None:
        body["content"] = content
    if category is not None:
        body["category"] = category.value
    if visibility is not None:
        body["visibility"] = visibility.value
    if tag is not None:
        body["tags"] = list(tag)
    if not body:
        raise UsageError(
            message="No fields to update", detail="Provide at least one of --content/--category/--visibility/--tag."
        )
    with ctx.make_client() as client:
        result = client.patch(f"/v1/dev/user/memories/{memory_id}", json_body=body)
    ctx.renderer.success(f"Memory updated: [bold]{memory_id}[/bold]")
    ctx.renderer.emit(result, title="memory")


@app.command("delete", help="Delete a memory by ID.")
def delete_memory(
    typer_ctx: typer.Context,
    memory_id: str = typer.Argument(..., help="Memory ID."),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete memory {memory_id}?", abort=True)
    with ctx.make_client() as client:
        client.delete(f"/v1/dev/user/memories/{memory_id}")
    ctx.renderer.success(f"Deleted memory [bold]{memory_id}[/bold].")
