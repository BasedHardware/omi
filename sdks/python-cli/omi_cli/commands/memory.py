"""``omi memory`` — facts and learnings about the user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

import typer
from rich.markup import escape

from omi_cli.client import path_segment
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

_MAX_CONTENT_LENGTH = 500


def _validate_content(content: str) -> str:
    """Return stripped content, rejecting oversized or blank input before any HTTP call.

    The backend caps the raw string at 500 characters, so the length check runs
    before stripping to keep the friendly CLI error aligned with the server's
    422 rather than letting a wrapped-in-whitespace payload round-trip.
    """
    if len(content) > _MAX_CONTENT_LENGTH:
        raise UsageError(
            message=f"Memory content must be at most {_MAX_CONTENT_LENGTH} characters (got {len(content)})",
            detail="Shorten the content and try again.",
        )
    cleaned = content.strip()
    if not cleaned:
        raise UsageError(
            message="Memory content cannot be empty",
            detail="Provide 1-500 characters of non-whitespace content.",
        )
    return cleaned


def _validate_tags(tags: Iterable[str]) -> list[str]:
    """Return stripped tags, rejecting blank entries before any HTTP call."""
    cleaned = [tag.strip() for tag in tags]
    if any(not tag for tag in cleaned):
        raise UsageError(
            message="Memory tags cannot be empty",
            detail="Remove blank --tag values or pass non-whitespace tags.",
        )
    return cleaned


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
    ctx = _ctx(typer_ctx)
    content = _validate_content(content)
    clean_tags = _validate_tags(tag)
    body: dict[str, object] = {"content": content, "visibility": visibility.value, "tags": clean_tags}
    if category is not None:
        body["category"] = category.value
    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/memories", json_body=body)
    ctx.renderer.success(f"Memory created: [bold]{escape(str(result.get('id')))}[/bold]")
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
        body["content"] = _validate_content(content)
    if category is not None:
        body["category"] = category.value
    if visibility is not None:
        body["visibility"] = visibility.value
    if tag is not None:
        body["tags"] = _validate_tags(tag)
    if not body:
        raise UsageError(
            message="No fields to update", detail="Provide at least one of --content/--category/--visibility/--tag."
        )
    with ctx.make_client() as client:
        result = client.patch(f"/v1/dev/user/memories/{path_segment(memory_id)}", json_body=body)
    ctx.renderer.success(f"Memory updated: [bold]{escape(memory_id)}[/bold]")
    ctx.renderer.emit(result, title="memory")


@app.command("delete", help="Delete a memory by ID.")
def delete_memory(
    typer_ctx: typer.Context,
    memory_id: str = typer.Argument(..., help="Memory ID."),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete memory {memory_id}?", abort=True, err=ctx.renderer.json_mode)
    with ctx.make_client() as client:
        result = client.delete(f"/v1/dev/user/memories/{path_segment(memory_id)}")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
    ctx.renderer.success(f"Deleted memory [bold]{escape(memory_id)}[/bold].")
