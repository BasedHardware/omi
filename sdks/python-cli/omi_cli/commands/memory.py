"""``omi memory`` — facts and learnings about the user."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List

import typer

from omi_cli.errors import NotFoundError, UsageError, CliError
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
    """
    List memories for the current user.

    Supports pagination via limit and offset, and filtering by memory categories.
    """
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
                "id": m.get("id"),
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
    """
    Fetch a single memory by its unique identifier.

    Since the dev API lacks a direct get-by-id endpoint, this implements
    client-side filtering by paging through the user's memories.
    """
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
            # The API validates records after applying its database offset, so
            # malformed historical rows can make a non-final page short.
            # Keep scanning at the next database offset in that case.
            offset += page_size


@app.command("create", help="Create a new memory.")
def create_memory(
    typer_ctx: typer.Context,
    content: str = typer.Argument(..., help="Memory content (1-500 chars)."),
    category: Optional[MemoryCategory] = typer.Option(None, "--category", help="Category. Auto-detected if omitted."),
    visibility: MemoryVisibility = typer.Option(MemoryVisibility.private, "--visibility", help="public or private."),
    tag: list[str] = typer.Option([], "--tag", help="Tag (repeat for multiple)."),
) -> None:
    """
    Create a new memory for the user.

    Content is required. Category, visibility, and tags are optional.
    """
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
    """
    Update fields of an existing memory.

    At least one field must be provided for update.
    """
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
    """
    Delete a specific memory by its ID.

    Requires confirmation unless the --yes flag is used.
    """
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete memory {memory_id}?", abort=True)
    with ctx.make_client() as client:
        result = client.delete(f"/v1/dev/user/memories/{memory_id}")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
    ctx.renderer.success(f"Deleted memory [bold]{memory_id}[/bold].")


@app.command("export", help="Export memories to a JSON file. Warning: uses offset pagination, so it's not a point-in-time snapshot; changes during export may cause duplicates or missing items.")
def export_memories(
    typer_ctx: typer.Context,
    output: Path = typer.Option(Path("memories_export.json"), "--output", "-o", help="Output file path."),
    categories: Optional[List[str]] = typer.Option(None, "--categories", "-c", help="Filter export by one or more categories."),
) -> None:
    """
    Export user memories to a JSON file.
    
    Fetches memories using pagination and streams them directly to the
    output file to prevent memory exhaustion for large datasets.
    """
    ctx = _ctx(typer_ctx)
    limit = 100
    offset = 0

    # Atomic write: write to temp file first, then rename to target.
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile("w", dir=output.parent, delete=False, encoding="utf-8")
    
    try:
        with ctx.make_client() as client:
            temp_file.write("[")
            first_item = True
            
            while True:
                # Pass categories to API if provided (backend might ignore, but it's the correct interface)
                params = {"limit": limit, "offset": offset}
                if categories:
                    params["categories"] = ",".join(categories)

                page = client.get("/v1/dev/user/memories", params=params)

                # Fail-fast: if API returns None but we expected a page, stop and fail.
                if page is None:
                    if offset == 0:
                        break
                    raise RuntimeError(
                        f"API returned None unexpectedly at offset {offset}. Export aborted to prevent partial write."
                    )

                for item in page:
                    # Client-side filter: ensure we only export requested categories
                    if categories and item.get("category") not in categories:
                        continue
                        
                    if not first_item:
                        temp_file.write(",")
                    json.dump(item, temp_file, ensure_ascii=False)
                    first_item = False
                
                if not page:
                    break
                
                offset += limit

            temp_file.write("]")
            temp_file.close()
            os.replace(temp_file.name, output)
    except Exception:
        temp_file.close()
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)
        raise

    ctx.renderer.success(f"Exported memories to [bold]{output}[/bold] via streaming.")
