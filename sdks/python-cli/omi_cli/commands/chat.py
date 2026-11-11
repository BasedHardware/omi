"""Terminal chat on the current default Omi cloud chat thread."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

import typer

from omi_cli import config as cfg
from omi_cli.client import OmiClient, path_segment
from omi_cli.errors import CliError, UsageError

if TYPE_CHECKING:
    from omi_cli.main import AppContext


_CHAT_PATH = "/v2/messages"
_STREAM_HEADERS = {"Accept": "text/event-stream", "X-Omi-Chat-Failure-Protocol": "1"}
_HELP = "Commands: /history, /clear, /tasks, /task add TEXT, /task done ID, /help, /quit"


def run(
    ctx: "AppContext",
    *,
    prompt: Optional[str],
    history: bool,
    clear: bool,
    yes: bool,
    limit: int,
) -> None:
    if sum((prompt is not None, history, clear)) > 1:
        raise UsageError(message="Choose a prompt, --history, or --clear")
    if yes and not clear:
        raise UsageError(message="--yes requires --clear")
    if prompt is None and not history and not clear and ctx.renderer.json_mode:
        raise UsageError(message="Interactive chat does not support --json", detail="Pass a prompt or --history.")

    # /v2/messages uses the signed-in user's Firebase identity. Developer API
    # keys have their own scoped endpoints and cannot authenticate this route.
    profile = ctx.get_profile()
    if profile.auth_method != "oauth" or os.environ.get(cfg.ENV_API_KEY):
        raise UsageError(
            message="Chat requires browser sign-in",
            detail="Run `omi auth login --browser`, then try `omi chat` again. Developer API keys cannot access chat.",
        )

    if history:
        _show_history(ctx, limit)
    elif clear:
        _clear(ctx, confirmed=yes)
    elif prompt is not None:
        _ask(ctx, prompt)
    else:
        _repl(ctx, limit)


def _repl(ctx: "AppContext", limit: int) -> None:
    typer.echo("Omi chat uses your shared cloud chat history. /clear deletes that history across clients.")
    typer.echo(_HELP)
    while True:
        try:
            line = typer.prompt("You").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            return
        if not line:
            continue
        if line in {"/quit", "/exit"}:
            return
        if line == "/help":
            typer.echo(_HELP)
            continue
        try:
            if line == "/history":
                _show_history(ctx, limit)
            elif line == "/clear":
                _clear(ctx, confirmed=False)
            elif line == "/tasks":
                _show_tasks(ctx)
            elif line.startswith("/task add "):
                _add_task(ctx, line.removeprefix("/task add ").strip())
            elif line.startswith("/task done "):
                _complete_task(ctx, line.removeprefix("/task done ").strip())
            elif line.startswith("/"):
                typer.echo("Unknown command. " + _HELP)
            else:
                _ask(ctx, line)
        except CliError as exc:
            ctx.renderer.error(exc.message, detail=exc.detail, extra=exc.extra)


def _ask(ctx: "AppContext", prompt: str) -> None:
    if not prompt.strip():
        raise UsageError(message="Chat message cannot be empty")
    streamed: list[str] = []

    def show_chunk(chunk: str) -> None:
        if ctx.renderer.json_mode:
            return
        if not streamed:
            sys.stdout.write("Omi: ")
        streamed.append(chunk)
        sys.stdout.write(chunk)
        sys.stdout.flush()

    with ctx.make_client() as client:
        try:
            result = _send_stream(client, prompt, show_chunk)
        except CliError:
            if streamed:
                typer.echo()
            raise
    if ctx.renderer.json_mode:
        ctx.renderer.emit(result)
        return
    final = result["text"]
    partial = "".join(streamed)
    if streamed:
        typer.echo()
        # The server can revise the provisional text (e.g. citation cleanup).
        # Show the canonical persisted answer if it differs from the stream.
        if final != partial:
            typer.echo(f"Final: {final}")
    else:
        typer.echo(f"Omi: {final}")


def _send_stream(client: OmiClient, prompt: str, on_chunk: Callable[[str], None]) -> Mapping[str, Any]:
    error: Optional[str] = None
    done: Optional[Mapping[str, Any]] = None
    for line in client.stream_post_lines(_CHAT_PATH, json_body={"text": prompt}, headers=_STREAM_HEADERS):
        if not line or line.startswith(":"):
            continue
        if line.startswith("data: "):
            if not error:
                on_chunk(line[6:].replace("__CRLF__", "\n"))
        elif line.startswith("done: "):
            try:
                decoded = base64.b64decode(line[6:], validate=True)
                payload = json.loads(decoded)
            except (ValueError, UnicodeError, binascii.Error) as exc:
                raise CliError(
                    message="Invalid chat response", detail="The server sent a malformed final message."
                ) from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise CliError(message="Invalid chat response", detail="The final message has no text.")
            done = payload
            break
        elif line.startswith("error:402:"):
            error = "Chat quota exceeded"
        elif line.startswith("error: "):
            try:
                payload = json.loads(line[7:])
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                code = payload.get("error")
                error = _friendly_stream_error(code)
            else:
                error = "Chat failed"
        elif line.startswith(("message: ", "think: ", "memory: ")):
            continue
        else:
            raise CliError(message="Invalid chat response", detail="The server sent an unknown stream frame.")
    if error:
        raise CliError(
            message=error, detail="Check `omi chat --history` before resending; the turn may have been saved."
        )
    if done is None:
        raise CliError(
            message="Chat stream ended early",
            detail="The turn may have been saved. Check `omi chat --history` before sending it again.",
        )
    return done


def _friendly_stream_error(code: Any) -> str:
    if code == "quota_exceeded":
        return "Chat quota exceeded"
    if code == "timeout":
        return "Chat timed out"
    return "Chat failed"


def _show_history(ctx: "AppContext", limit: int) -> None:
    with ctx.make_client() as client:
        messages = client.get(_CHAT_PATH, params={"limit": limit})
    if not isinstance(messages, list):
        raise CliError(message="Invalid chat history", detail="Expected a list of messages from Omi.")
    if ctx.renderer.json_mode:
        ctx.renderer.emit(messages)
        return
    if not messages:
        typer.echo("No chat history yet.")
        return
    # The API pages newest-first; render the selected page in reading order.
    for message in reversed(messages):
        if not isinstance(message, Mapping):
            continue
        sender = "You" if message.get("sender") == "human" else "Omi"
        text = message.get("text")
        if isinstance(text, str) and text.strip():
            typer.echo(f"{sender}: {text}")


def _clear(ctx: "AppContext", *, confirmed: bool) -> None:
    if not confirmed and not typer.confirm(
        "Delete shared Omi chat history across clients?", default=False, err=ctx.renderer.json_mode
    ):
        if ctx.renderer.json_mode:
            ctx.renderer.emit({"cleared": False})
        else:
            typer.echo("Kept chat history.")
        return
    with ctx.make_client() as client:
        client.delete(_CHAT_PATH)
    if ctx.renderer.json_mode:
        ctx.renderer.emit({"cleared": True})
    else:
        typer.echo("Shared chat history cleared.")


def _show_tasks(ctx: "AppContext") -> None:
    with ctx.make_client() as client:
        payload = client.get("/v1/action-items", params={"completed": False, "limit": 20})
    if not isinstance(payload, Mapping) or not isinstance(payload.get("action_items"), list):
        raise CliError(message="Invalid task list")
    items = payload["action_items"]
    if not items:
        typer.echo("No open tasks.")
        return
    for item in items:
        if isinstance(item, Mapping):
            typer.echo(f"{item.get('id', '?')}  {item.get('description', '')}")
    if payload.get("has_more"):
        typer.echo("Showing the first 20 open tasks.")


def _add_task(ctx: "AppContext", description: str) -> None:
    if not description:
        raise UsageError(message="Usage: /task add DESCRIPTION")
    with ctx.make_client() as client:
        item = client.post("/v1/action-items", json_body={"description": description})
    if not isinstance(item, Mapping):
        raise CliError(message="Invalid task response")
    typer.echo(f"Task added: {item.get('id', '?')}  {item.get('description', description)}")


def _complete_task(ctx: "AppContext", task_id: str) -> None:
    if not task_id:
        raise UsageError(message="Usage: /task done ID")
    with ctx.make_client() as client:
        item = client.patch(f"/v1/action-items/{path_segment(task_id)}/completed", params={"completed": True})
    if not isinstance(item, Mapping):
        raise CliError(message="Invalid task response")
    typer.echo(f"Task completed: {item.get('description', task_id)}")
