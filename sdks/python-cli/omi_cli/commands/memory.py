"""``omi memory`` — facts and learnings about the user."""

from __future__ import annotations

import json
from pathlib import Path
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


def _read_utf8_file(path: Path) -> str:
    """Read UTF-8 (BOM-tolerant) text from a file, mapping failures to UsageError."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise UsageError(
            message=f"File not found: {path}",
            detail="Check the path and try again.",
        ) from None
    except IsADirectoryError:
        raise UsageError(message=f"Path is a directory: {path}") from None
    except UnicodeDecodeError:
        raise UsageError(
            message=f"File is not valid UTF-8: {path}",
            detail="Encode the file as UTF-8 and try again.",
        ) from None
    except OSError:
        raise UsageError(
            message=f"Cannot read file: {path}",
            detail="Check permissions and try again.",
        ) from None
    return content


def _read_batch_memories(file_path: Path) -> list[dict[str, object]]:
    """Validate a batch memory JSON file and map it to request entries.

    Accepts a JSON array of memory objects, or an object with a ``memories``
    array. Each entry must be an object with non-empty ``content``; ``category``
    and ``visibility`` are validated against the CLI enums, and ``tags`` must be
    a list of strings.
    """
    try:
        payload = json.loads(_read_utf8_file(file_path))
    except json.JSONDecodeError as exc:
        raise UsageError(
            message=f"Memory file is not valid JSON: {file_path}",
            detail=f"Parse error at line {exc.lineno} column {exc.colno}.",
        ) from None

    if isinstance(payload, dict) and isinstance(payload.get("memories"), list):
        payload = payload["memories"]
    if not isinstance(payload, list):
        raise UsageError(
            message="Memory file must contain a JSON array of memories",
            detail="Provide an array like [{\"content\": \"...\"}] or {\"memories\": [...]}.",
        )
    if not payload:
        raise UsageError(
            message="Memory file contains no memories",
            detail="Provide at least one memory entry.",
        )
    if len(payload) > 25:
        raise UsageError(
            message=f"Maximum 25 memories per batch request, got {len(payload)}",
            detail="Split the file into batches of 25 or fewer entries.",
        )

    entries: list[dict[str, object]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise UsageError(
                message=f"Memory entry {index} is not an object",
                detail="Every entry must be a JSON object.",
            )
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise UsageError(
                message=f"Memory entry {index} has empty content",
                detail="Every entry needs non-empty string content.",
            )
        if len(content.strip()) > 500:
            raise UsageError(
                message=f"Memory entry {index} exceeds 500 characters",
                detail="The batch endpoint rejects content longer than 500 characters.",
            )
        entry: dict[str, object] = {"content": content.strip()}
        visibility = item.get("visibility", MemoryVisibility.private.value)
        if not isinstance(visibility, str) or visibility not in MemoryVisibility._value2member_map_:
            raise UsageError(
                message=f"Memory entry {index} has invalid visibility: {visibility}",
                detail="Use 'public' or 'private'.",
            )
        entry["visibility"] = visibility
        tags = item.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise UsageError(
                message=f"Memory entry {index} has invalid tags",
                detail="'tags' must be a list of strings.",
            )
        entry["tags"] = list(tags)
        category = item.get("category")
        if category is not None:
            if not isinstance(category, str) or category not in MemoryCategory._value2member_map_:
                raise UsageError(
                    message=f"Memory entry {index} has invalid category: {category}",
                    detail="Use a known memory category (e.g. work, skills, personal).",
                )
            entry["category"] = category
        entries.append(entry)
    return entries


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


@app.command("create-batch", help="Create up to 25 memories from a UTF-8 JSON file.")
def create_memories_batch(
    typer_ctx: typer.Context,
    file_path: Path = typer.Argument(..., help="Path to a UTF-8 JSON file with a 'memories' array."),
) -> None:
    ctx = _ctx(typer_ctx)
    entries = _read_batch_memories(file_path)
    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/memories/batch", json_body={"memories": entries})
    created_count = result.get("created_count", 0)
    ctx.renderer.success(f"Created [bold]{created_count}[/bold] memories")
    ctx.renderer.emit(result, title="memories")


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
        result = client.delete(f"/v1/dev/user/memories/{memory_id}")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
    ctx.renderer.success(f"Deleted memory [bold]{memory_id}[/bold].")
