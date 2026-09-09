"""``omi folder`` — organize conversations into groups."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.output import shorten

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


_LIST_COLUMNS = ["id", "name", "conversation_count", "color", "icon", "is_system"]


@app.command("list", help="List existing conversation folders.")
def list_folders(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        folders = client.get("/v1/dev/user/folders")

    if ctx.renderer.json_mode:
        ctx.renderer.emit(folders)
        return

    rows = []
    for f in folders or []:
        rows.append(
            {
                "id": shorten(f.get("id"), 14),
                "name": shorten(f.get("name"), 30),
                "conversation_count": f.get("conversation_count", 0),
                "color": f.get("color", ""),
                "icon": f.get("icon", ""),
                "is_system": f.get("is_system", False),
            }
        )
    ctx.renderer.emit(rows, columns=_LIST_COLUMNS, title="folders")
