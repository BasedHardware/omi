"""Read-only Omi chat tools for publisher-supplied PyPI metadata."""

import re
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field

PYPI_BASE = "https://pypi.org/pypi"
TIMEOUT = 10.0
MAX_RESULT = 6000
NAME_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
app = FastAPI(title="PyPI Omi Integration", version="1.0.0")


class PackageInput(BaseModel):
    package: str = Field(min_length=1, max_length=200)


class ReleaseInput(PackageInput):
    version: str = Field(min_length=1, max_length=200)


class ChatToolResponse(BaseModel):
    result: str | None = None
    error: str | None = None


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(status_code=422, content={"result": None, "error": "Invalid package or version input."})


def clean(value: Any, limit: int = 400) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit] + " [truncated]"


def metadata_text(info: dict, source_url: str) -> str:
    links = info.get("project_urls")
    if isinstance(links, dict) and links:
        link_text = "; ".join(f"{clean(k, 50)}: {clean(v, 200)}" for k, v in list(links.items())[:5])
        if len(links) > 5:
            link_text += "; [truncated]"
    else:
        link_text = "unknown"
    dependencies = info.get("requires_dist")
    if isinstance(dependencies, list):
        dependency_text = "; ".join(clean(dep, 200) for dep in dependencies[:10]) or "none declared"
        if len(dependencies) > 10:
            dependency_text += "; [truncated]"
    else:
        dependency_text = "unknown"
    yanked = info.get("yanked")
    yanked_text = "yes" if yanked is True else "no" if yanked is False else "unknown"
    lines = [
        "PyPI publisher-supplied metadata; not a safety verification.",
        f"PyPI source: {source_url}",
        f"Name: {clean(info.get('name'), 200)}",
        f"Version: {clean(info.get('version'), 200)}",
        f"Summary: {clean(info.get('summary'), 500)}",
        f"Requires Python: {clean(info.get('requires_python'), 200)}",
        f"License: {clean(info.get('license_expression') or info.get('license'), 300)}",
        f"Yanked: {yanked_text}",
        f"Yank reason: {clean(info.get('yanked_reason'), 200)}",
        f"Project links: {link_text}",
        f"Declared dependencies: {dependency_text}",
    ]
    result = "\n".join(lines)
    return result if len(result) <= MAX_RESULT else result[: MAX_RESULT - 12] + " [truncated]"


async def lookup(package: str, version: str | None = None) -> ChatToolResponse:
    package = package.strip()
    if not NAME_PATTERN.fullmatch(package):
        return ChatToolResponse(error="Invalid package name. Use a PyPI project name, not a URL.")
    package = re.sub(r"[-_.]+", "-", package).lower()
    path = f"/{package}"
    if version is not None:
        version = version.strip()
        if not re.fullmatch(r"[A-Za-z0-9.!+_-]+", version):
            return ChatToolResponse(error="Invalid release version. Use a PEP 440 version.")
        try:
            Version(version)
        except InvalidVersion:
            return ChatToolResponse(error="Invalid release version. Use a PEP 440 version.")
        path += f"/{quote(version, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.get(f"{PYPI_BASE}{path}/json")
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return ChatToolResponse(error="PyPI request timed out. Try again later.")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(error="PyPI package or release not found.")
        return ChatToolResponse(error="PyPI is unavailable. Try again later.")
    except httpx.RequestError:
        return ChatToolResponse(error="PyPI is unavailable. Try again later.")
    except ValueError:
        return ChatToolResponse(error="PyPI returned invalid metadata.")
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
        return ChatToolResponse(error="PyPI returned invalid metadata.")
    info = data["info"]
    if any(not isinstance(info.get(key), str) or not info[key].strip() for key in ("name", "version")):
        return ChatToolResponse(error="PyPI returned invalid metadata.")
    return ChatToolResponse(result=metadata_text(info, f"https://pypi.org/project{path}/"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    tools = []
    for name, description, required in [
        ("get_pypi_package", "Look up a PyPI project's current metadata", ["package"]),
        ("get_pypi_release", "Look up metadata for an exact PyPI release", ["package", "version"]),
    ]:
        properties = {"package": {"type": "string", "description": "PyPI project name, e.g. httpx"}}
        if "version" in required:
            properties["version"] = {"type": "string", "description": "Exact PEP 440 version, e.g. 0.28.0"}
        tools.append(
            {
                "name": name,
                "description": description + ". Publisher-supplied metadata, not a safety verification.",
                "endpoint": f"/tools/{name}",
                "method": "POST",
                "parameters": {"type": "object", "properties": properties, "required": required},
                "auth_required": False,
                "status_message": "Fetching PyPI metadata...",
            }
        )
    return {"tools": tools}


@app.post("/tools/get_pypi_package", response_model=ChatToolResponse)
async def get_pypi_package(payload: PackageInput):
    return await lookup(payload.package)


@app.post("/tools/get_pypi_release", response_model=ChatToolResponse)
async def get_pypi_release(payload: ReleaseInput):
    return await lookup(payload.package, payload.version)
