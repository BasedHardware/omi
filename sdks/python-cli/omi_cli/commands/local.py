"""``omi local`` — local Omi Desktop API tools."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
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
    limit: int = typer.Option(15, "--limit", min=1, max=50, help="Maximum results to return."),
) -> None:
    ctx = _ctx(typer_ctx)
    args: dict[str, Any] = {"query": query, "days": days, "limit": limit}
    if app_filter:
        args["app_filter"] = app_filter
    with ctx.make_local_client() as client:
        result = client.call_tool("search_screen_history", args)
        if ctx.renderer.json_mode:
            result = _normalize_screen_search(result, args)
            if isinstance(result, Mapping) and not result.get("results"):
                result = _add_exact_screen_fallback(client, result, query=query, app_filter=app_filter, limit=limit)
    ctx.renderer.emit(result, title="search_screen_history")


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
    raw_metadata = result.get("metadata") if isinstance(result, Mapping) else None
    metadata: Mapping[str, Any] = raw_metadata if isinstance(raw_metadata, Mapping) else {}
    ctx.renderer.success(f"Wrote screenshot to [bold]{written}[/bold].")
    ctx.renderer.emit(
        {
            "path": str(written),
            "screenshot_id": metadata.get("screenshot_id")
            or (result.get("screenshot_id") if isinstance(result, Mapping) else screenshot_id),
            "bytes": written.stat().st_size,
            "metadata": metadata,
            "result": _redact_screenshot_payload(result),
        },
        title="screenshot",
    )


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
    _emit_tool(ctx, "execute_sql", {"query": query}, transform=_normalize_sql_result)


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
    transform: Optional[Any] = None,
) -> None:
    with ctx.make_local_client() as client:
        result = client.call_tool(tool_name, arguments)
    if transform is not None and ctx.renderer.json_mode:
        result = transform(result)
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


def _normalize_sql_result(result: Any) -> Any:
    if not isinstance(result, str):
        return result

    lines = [line.rstrip() for line in result.splitlines()]
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return {"rows": [], "columns": [], "row_count": 0, "text": result}

    if result == "No results":
        return {"rows": [], "columns": [], "row_count": 0}
    if result.startswith("Error:") or result.startswith("SQL Error:"):
        return {"error": result}
    if result.startswith("OK:"):
        return {"ok": True, "message": result}

    footer = non_empty[-1]
    row_count_match = re.match(r"^(\d+) row\(s\)$", footer)
    header = non_empty[0]
    separator_index = 1 if len(non_empty) > 1 and set(non_empty[1]) <= {"-", " "} else None
    if separator_index is None or not row_count_match:
        return {"text": result}

    columns = [part.strip() for part in header.split("|")] if "|" in header else [header.strip()]
    rows = []
    for line in non_empty[2:-1]:
        values = [part.strip() for part in line.split("|")] if "|" in line else [line.strip()]
        rows.append({column: values[index] if index < len(values) else "" for index, column in enumerate(columns)})

    return {
        "columns": columns,
        "rows": rows,
        "row_count": int(row_count_match.group(1)),
    }


def _normalize_screen_search(result: Any, arguments: Mapping[str, Any]) -> Any:
    if not isinstance(result, str):
        return result

    query = str(arguments.get("query") or "")
    days = int(arguments.get("days") or 7)
    app_filter = arguments.get("app_filter")
    limit = int(arguments.get("limit") or 15)

    if result.startswith("No matching screen-history results") or result.startswith("No screen history is available"):
        suggestions = [
            "Try a broader query",
            "Increase --days",
            "Use `omi --json local sql` for exact app/window/OCR filters",
        ]
        if app_filter is None:
            suggestions.insert(0, f"Try `omi --json local search-screen {json.dumps(query)} --app <AppName>`")
        return {
            "results": [],
            "query": query,
            "days": days,
            "app_filter": app_filter,
            "limit": limit,
            "reason": result.strip(),
            "suggestions": suggestions,
        }

    results: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    result_line = re.compile(
        r"^\s*(\d+)\. \[(.*?)\] (.*?)(?: - (.*?))? \(screenshot_id: (\d+), similarity: ([0-9.]+)\)$"
    )
    for line in result.splitlines():
        match = result_line.match(line)
        if match:
            current = {
                "rank": int(match.group(1)),
                "timestamp": match.group(2),
                "app_name": match.group(3),
                "window_title": match.group(4) or None,
                "screenshot_id": int(match.group(5)),
                "similarity": float(match.group(6)),
            }
            results.append(current)
            continue
        if current is not None and line.strip().startswith("Content:"):
            current["ocr_preview"] = line.split("Content:", 1)[1].strip()

    if not results:
        return {"text": result, "query": query, "days": days, "app_filter": app_filter, "limit": limit}

    return {
        "results": results,
        "query": query,
        "days": days,
        "app_filter": app_filter,
        "limit": limit,
        "result_count": len(results),
    }


def _add_exact_screen_fallback(
    client: Any,
    payload: Mapping[str, Any],
    *,
    query: str,
    app_filter: Optional[str],
    limit: int,
) -> dict[str, Any]:
    next_payload = dict(payload)
    escaped_query = _sql_like_literal(query)
    query_clauses = [
        f"appName LIKE '%{escaped_query}%'",
        f"windowTitle LIKE '%{escaped_query}%'",
        f"ocrText LIKE '%{escaped_query}%'",
    ]
    if app_filter:
        escaped_app = _sql_like_literal(app_filter)
        where_clause = f"(appName LIKE '%{escaped_app}%') AND ({' OR '.join(query_clauses)})"
    else:
        where_clause = " OR ".join(query_clauses)

    sql = (
        "SELECT id AS screenshot_id, timestamp, appName AS app_name, isIndexed AS is_indexed "
        "FROM screenshots "
        f"WHERE {where_clause} "
        "ORDER BY timestamp DESC "
        f"LIMIT {limit}"
    )
    fallback = _normalize_sql_result(client.call_tool("execute_sql", {"query": sql}))
    next_payload["exact_fallback"] = {
        "query": sql,
        "source": "app_window_ocr_sql",
        "result": fallback,
    }
    if isinstance(fallback, Mapping):
        rows = fallback.get("rows")
        if isinstance(rows, list) and rows:
            next_payload["suggested_screenshot_ids"] = [
                row.get("screenshot_id") for row in rows if isinstance(row, Mapping) and row.get("screenshot_id")
            ]
    return next_payload


def _sql_like_literal(value: str) -> str:
    return value.replace("'", "''")


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
