"""``omi local`` — local Omi Desktop API tools."""

from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

import typer

from omi_cli import config as cfg
from omi_cli.errors import UsageError
from omi_cli.local_client import existing_path

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)
task_app = typer.Typer(no_args_is_help=True, help="Search and mutate local Omi tasks.")
app.add_typer(task_app, name="task")


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


def _local_settings(ctx: "AppContext") -> tuple[str, str, str]:
    profile = ctx.get_profile()
    env_url = os.environ.get(cfg.ENV_LOCAL_API_URL)
    env_token = os.environ.get(cfg.ENV_LOCAL_TOKEN)
    url = env_url or profile.local_api_url or ""
    token = env_token or profile.local_token or ""
    source = "env" if env_url or env_token else "profile"
    return url, token, source


@app.command("configure", help="Store local Omi Desktop API settings on the active profile.")
def configure(
    typer_ctx: typer.Context,
    url: str = typer.Option(..., "--url", help="Local Omi Desktop API URL."),
    token: str = typer.Option(..., "--token", help="Bearer token for the local Omi Desktop API."),
) -> None:
    ctx = _ctx(typer_ctx)
    config = ctx.load_config()
    profile = config.get_profile(ctx.profile_name)
    profile.local_api_url = url.rstrip("/")
    profile.local_token = token
    config.set_profile(profile)
    cfg.save(config)
    ctx.reload_config()
    payload = {
        "profile": profile.name,
        "local_api_url": profile.local_api_url,
        "local_token": _mask_token(profile.local_token),
    }
    ctx.renderer.success(f"Configured local Omi Desktop API for profile [bold]{profile.name}[/bold].")
    ctx.renderer.emit(payload, title="local configuration")


@app.command("status", help="Show local API configuration and probe Omi Desktop when configured.")
def status(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    url, token, source = _local_settings(ctx)
    payload: dict[str, Any] = {
        "profile": ctx.profile_name,
        "configured": bool(url and token),
        "local_api_url": url or None,
        "local_token": _mask_token(token),
        "source": source,
    }
    if url and token:
        with ctx.make_local_client() as client:
            payload["desktop"] = client.call_tool("get_local_status", {})
    ctx.renderer.emit(payload, title="local status")


@app.command("tools", help="List local Omi Desktop tools available to the CLI.")
def tools(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_local_client() as client:
        result = client.list_tools()
    ctx.renderer.emit(result, title="local tools")


@app.command("call", help="Call a local Omi Desktop tool by name.")
def call(
    typer_ctx: typer.Context,
    tool_name: str = typer.Argument(..., help="Local tool name from `omi local tools`."),
    args_json: str = typer.Option("{}", "--args-json", help="JSON object with tool arguments."),
) -> None:
    ctx = _ctx(typer_ctx)
    try:
        parsed = json.loads(args_json)
    except json.JSONDecodeError as exc:
        raise UsageError(message="--args-json must be valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise UsageError(message="--args-json must be a JSON object")
    _emit_tool(ctx, tool_name, parsed)


@app.command("search-screen", help="Semantic search over local Rewind screen history.")
def search_screen(
    typer_ctx: typer.Context,
    query: str = typer.Argument(..., help="Natural-language screen-history query."),
    days: int = typer.Option(7, "--days", min=1, max=365),
    app_filter: Optional[str] = typer.Option(None, "--app", help="Restrict results to one app name."),
) -> None:
    ctx = _ctx(typer_ctx)
    args: dict[str, Any] = {"query": query, "days": days}
    if app_filter:
        args["app_filter"] = app_filter
    _emit_tool(ctx, "search_screen_history", args)


@app.command("screenshot", help="Fetch a screenshot by ID.")
def screenshot(
    typer_ctx: typer.Context,
    screenshot_id: str = typer.Argument(..., help="Screenshot ID from local search results."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write screenshot data to this path."),
) -> None:
    ctx = _ctx(typer_ctx)
    with ctx.make_local_client() as client:
        result = client.call_tool("get_screenshot", {"screenshot_id": screenshot_id})
    if output is None:
        ctx.renderer.emit(result, title="screenshot")
        return

    written = _write_screenshot_result(result, output)
    ctx.renderer.success(f"Wrote screenshot to [bold]{written}[/bold].")
    ctx.renderer.emit({"output": str(written), "result": _redact_screenshot_payload(result)}, title="screenshot")


@app.command("recap", help="Get a pre-formatted daily local activity recap.")
def recap(
    typer_ctx: typer.Context,
    days_ago: int = typer.Option(0, "--days-ago", min=0, max=365, help="0=today, 1=yesterday."),
) -> None:
    ctx = _ctx(typer_ctx)
    _emit_tool(ctx, "get_daily_recap", {"days_ago": days_ago})


@app.command("sql", help="Run SQL against the local Omi Desktop database.")
def sql(
    typer_ctx: typer.Context,
    query: str = typer.Argument(..., help="SQL query to execute."),
) -> None:
    ctx = _ctx(typer_ctx)
    _emit_tool(ctx, "execute_sql", {"query": query})


@task_app.command("search", help="Semantic search over local Omi tasks.")
def search_tasks(
    typer_ctx: typer.Context,
    query: str = typer.Argument(..., help="Natural-language task query."),
    include_completed: bool = typer.Option(False, "--include-completed", help="Include completed tasks."),
) -> None:
    ctx = _ctx(typer_ctx)
    _emit_tool(ctx, "search_tasks", {"query": query, "include_completed": include_completed})


@task_app.command("complete", help="Mark a task complete.")
def complete_task(
    typer_ctx: typer.Context,
    task_id: str = typer.Argument(..., help="Task backend ID."),
) -> None:
    ctx = _ctx(typer_ctx)
    _emit_tool(ctx, "complete_task", {"task_id": task_id}, success=f"Completed task [bold]{task_id}[/bold].")


@task_app.command("delete", help="Delete a task permanently.")
def delete_task(
    typer_ctx: typer.Context,
    task_id: str = typer.Argument(..., help="Task backend ID."),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    ctx = _ctx(typer_ctx)
    if not confirm:
        typer.confirm(f"Delete task {task_id}?", abort=True)
    _emit_tool(ctx, "delete_task", {"task_id": task_id}, success=f"Deleted task [bold]{task_id}[/bold].")


def _emit_tool(
    ctx: "AppContext",
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    success: Optional[str] = None,
) -> None:
    with ctx.make_local_client() as client:
        result = client.call_tool(tool_name, arguments)
    if success:
        ctx.renderer.success(success)
    ctx.renderer.emit(result, title=tool_name)


def _write_screenshot_result(result: Any, output: Path) -> Path:
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(result, str):
        source = existing_path(result)
        if source:
            shutil.copyfile(source, output)
        else:
            output.write_text(result)
        return output

    if isinstance(result, Mapping):
        source_path = _first_string(result, ("path", "file_path", "image_path", "screenshot_path"))
        if source_path:
            source = existing_path(source_path)
            if source:
                shutil.copyfile(source, output)
                return output

        encoded = _first_string(result, ("image_base64", "base64", "data_base64", "data"))
        if encoded:
            output.write_bytes(_decode_base64_payload(encoded))
            return output

        content = result.get("content")
        if isinstance(content, str):
            output.write_text(content)
            return output

    output.write_text(json.dumps(result, indent=2, sort_keys=False))
    return output


def _redact_screenshot_payload(result: Any) -> Any:
    if not isinstance(result, Mapping):
        return result
    redacted = dict(result)
    image_payload = redacted.pop("image_base64", None)
    if image_payload is not None:
        redacted["image_base64_redacted"] = True
        redacted["image_base64_chars"] = len(str(image_payload))
    return redacted


def _first_string(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _decode_base64_payload(value: str) -> bytes:
    payload = value
    if "," in payload and payload.lstrip().startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UsageError(message="Screenshot result did not contain valid base64 data") from exc


def _mask_token(token: Optional[str]) -> str:
    if not token:
        return "(none)"
    if len(token) <= 12:
        return f"{token[:2]}…{token[-2:]}"
    return f"{token[:6]}…{token[-4:]}"
