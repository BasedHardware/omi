"""``omi conversation`` — captured & processed audio/text conversations."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer

from omi_cli.errors import UsageError
from omi_cli.models import ConversationTextSource
from omi_cli.output import shorten

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


_LIST_COLUMNS = ["id", "title", "category", "started_at", "source"]


@app.command("list", help="List conversations.")
def list_conversations(
    typer_ctx: typer.Context,
    limit: int = typer.Option(25, "--limit", min=1, max=200),
    offset: int = typer.Option(0, "--offset", min=0),
    start_date: Optional[datetime] = typer.Option(None, "--start-date", help="ISO datetime lower bound."),
    end_date: Optional[datetime] = typer.Option(None, "--end-date", help="ISO datetime upper bound."),
    categories: Optional[str] = typer.Option(None, "--categories", help="Comma-separated category filter."),
    include_transcript: bool = typer.Option(False, "--include-transcript", help="Include transcript_segments."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        items = client.get(
            "/v1/dev/user/conversations",
            params={
                "limit": limit,
                "offset": offset,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "categories": categories,
                "include_transcript": include_transcript,
            },
        )
    if ctx.renderer.json_mode:
        ctx.renderer.emit(items)
        return
    rows = []
    for c in items or []:
        structured = c.get("structured") or {}
        rows.append(
            {
                "id": shorten(c.get("id"), 14),
                "title": shorten(structured.get("title"), 50),
                "category": structured.get("category"),
                "started_at": c.get("started_at"),
                "source": c.get("source"),
            }
        )
    ctx.renderer.emit(rows, columns=_LIST_COLUMNS, title=f"conversations (limit={limit})")


@app.command("get", help="Fetch a single conversation by ID.")
def get_conversation(
    typer_ctx: typer.Context,
    conversation_id: str = typer.Argument(..., help="Conversation ID."),
    include_transcript: bool = typer.Option(False, "--include-transcript"),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_client() as client:
        result = client.get(
            f"/v1/dev/user/conversations/{conversation_id}",
            params={"include_transcript": include_transcript},
        )
    ctx.renderer.emit(result, title="conversation")


@app.command("create", help="Create a conversation from raw text.")
def create_conversation(
    typer_ctx: typer.Context,
    text: Optional[str] = typer.Option(None, "--text", help="Text body. Use '-' to read from stdin."),
    text_source: ConversationTextSource = typer.Option(
        ConversationTextSource.other_text,
        "--text-source",
        help="Source type. One of audio_transcript, message, other_text.",
    ),
    text_source_spec: Optional[str] = typer.Option(None, "--text-source-spec", help="e.g. 'email', 'slack'."),
    started_at: Optional[datetime] = typer.Option(None, "--started-at", help="ISO datetime."),
    finished_at: Optional[datetime] = typer.Option(None, "--finished-at", help="ISO datetime."),
    language: str = typer.Option("en", "--language", help="ISO 639-1 code."),
) -> None:
    ctx = _ctx(typer_ctx)

    if text is None or text == "-":
        if sys.stdin.isatty():
            raise UsageError(
                message="No --text provided",
                detail="Pass --text 'your text' or pipe content via stdin and use --text -.",
            )
        text = sys.stdin.read()

    body: dict[str, object] = {
        "text": text,
        "text_source": text_source.value,
        "language": language,
    }
    if text_source_spec is not None:
        body["text_source_spec"] = text_source_spec
    if started_at is not None:
        body["started_at"] = started_at.isoformat()
    if finished_at is not None:
        body["finished_at"] = finished_at.isoformat()

    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/conversations", json_body=body)
    ctx.renderer.success(f"Conversation queued: [bold]{result.get('id')}[/bold] (status={result.get('status')})")
    ctx.renderer.emit(result)


@app.command("from-segments", help="Create a conversation from structured transcript segments (JSON file).")
def from_segments(
    typer_ctx: typer.Context,
    segments_file: Path = typer.Argument(..., help="Path to a JSON file containing 'transcript_segments'."),
    source: Optional[str] = typer.Option(None, "--source", help="Conversation source (e.g. omi, friend, phone)."),
    started_at: Optional[datetime] = typer.Option(None, "--started-at"),
    finished_at: Optional[datetime] = typer.Option(None, "--finished-at"),
    language: str = typer.Option("en", "--language"),
) -> None:
    ctx = _ctx(typer_ctx)
    if not segments_file.exists():
        raise UsageError(message=f"File not found: {segments_file}")
    try:
        payload = json.loads(segments_file.read_text())
    except json.JSONDecodeError as exc:
        raise UsageError(message=f"Invalid JSON in {segments_file}", detail=str(exc))

    segments = payload.get("transcript_segments") if isinstance(payload, dict) else payload
    if not isinstance(segments, list):
        raise UsageError(
            message="JSON must be a list, or an object with 'transcript_segments' key",
            detail="Each segment needs at least 'text', 'start', 'end'.",
        )

    body: dict[str, object] = {"transcript_segments": segments, "language": language}
    if source is not None:
        body["source"] = source
    if started_at is not None:
        body["started_at"] = started_at.isoformat()
    if finished_at is not None:
        body["finished_at"] = finished_at.isoformat()

    with ctx.make_client() as client:
        result = client.post("/v1/dev/user/conversations/from-segments", json_body=body)
    ctx.renderer.success(f"Conversation queued: [bold]{result.get('id')}[/bold]")
    ctx.renderer.emit(result)


@app.command("update", help="Update conversation title or discard status.")
def update_conversation(
    typer_ctx: typer.Context,
    conversation_id: str = typer.Argument(..., help="Conversation ID."),
    title: Optional[str] = typer.Option(None, "--title"),
    discarded: Optional[bool] = typer.Option(None, "--discarded/--no-discarded"),
) -> None:
    ctx = _ctx(typer_ctx)
    body: dict[str, object] = {}
    if title is not None:
        body["title"] = title
    if discarded is not None:
        body["discarded"] = discarded
    if not body:
        raise UsageError(message="No fields to update", detail="Provide --title or --discarded/--no-discarded.")
    with ctx.make_client() as client:
        result = client.patch(f"/v1/dev/user/conversations/{conversation_id}", json_body=body)
    ctx.renderer.success(f"Updated conversation [bold]{conversation_id}[/bold].")
    ctx.renderer.emit(result)


@app.command("delete", help="Delete a conversation by ID.")
def delete_conversation(
    typer_ctx: typer.Context,
    conversation_id: str = typer.Argument(..., help="Conversation ID."),
    confirm: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete conversation {conversation_id}?", abort=True)
    with ctx.make_client() as client:
        client.delete(f"/v1/dev/user/conversations/{conversation_id}")
    ctx.renderer.success(f"Deleted conversation [bold]{conversation_id}[/bold].")
