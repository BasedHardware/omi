"""``omi memory`` — facts and learnings about the user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import typer
from rich.markup import escape
from omi_cli.client import path_segment
from omi_cli.errors import NotFoundError, UsageError
from omi_cli.models import MemoryCategory, MemoryVisibility
from omi_cli.output import shorten

if TYPE_CHECKING:
        from omi_cli.main import AppContext

app = typer.Typer(no_args_is_help=True)
_LIST_COLUMNS = ["id", "category", "visibility", "content", "tags", "created_at"]


@app.command("get", help="Fetch a single memory by ID.")
def _memory(
        memory_id: str = typer.Argument(...),
        _ctx: typer.Context,
) -> None:
        client = _ctx.make_client()
        page_size = 100
        offset = 0
        max_offset = 10000
        while offset < max_offset:
                    page = client.get("/v1/dev/user/memories", params={"limit": page_size, "offset": offset})
                    if not page:
                                    raise NotFoundError(message=f"Memory not found: {memory_id}")
                                for item in page:
                                                if item.get("id") == memory_id:
                                                                    ctx.renderer.emit(item, title="memory")
                                                                    return
                                                            if len(page) < page_size:
                                                                            raise NotFoundError(message=f"Memory not found: {memory_id}")
                                                                        offset += page_size
                                        raise NotFoundError(message=f"Memory not found: {memory_id}")
            
