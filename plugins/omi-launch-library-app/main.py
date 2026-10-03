from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from launchlibrary import (
    LaunchLibraryError,
    get_launch,
    get_upcoming_launches,
    search_launches,
)
from models import (
    ChatToolResponse,
    LaunchDetailsRequest,
    SearchLaunchesRequest,
    UpcomingLaunchesRequest,
)


REQUEST_TIMEOUT_SECONDS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"Accept": "application/json"},
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(
    title="Omi Launch Library 2 Integration",
    description="Search public rocket launch data from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content=ChatToolResponse(
            error=f"invalid launch request: {exc.errors()[0]['msg']}"
        ).model_dump(),
    )


def _client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi Launch Library 2 Integration</title></head>
      <body>
        <h1>Omi Launch Library 2 Integration</h1>
        <p>Search public rocket launch data from Omi conversations.</p>
        <p><a href="/.well-known/omi-tools.json">Tool manifest</a></p>
      </body>
    </html>
    """


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "name": "Launch Library 2",
        "description": "Search public rocket launch data from Omi.",
        "tools": [
            {
                "name": "get_upcoming_launches",
                "description": (
                    "List upcoming rocket launches, optionally filtered by "
                    "provider, rocket, and date range."
                ),
                "endpoint": "/tools/get_upcoming_launches",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 365,
                            "default": 30,
                            "description": "Look-ahead window in days.",
                        },
                        "provider": {
                            "type": "string",
                            "description": (
                                "Exact launch service provider name, such as SpaceX."
                            ),
                        },
                        "rocket": {
                            "type": "string",
                            "description": ("Rocket name substring, such as Falcon 9."),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "search_launches",
                "description": (
                    "Search public rocket launch records by text, provider, "
                    "rocket, or UTC date range."
                ),
                "endpoint": "/tools/search_launches",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-text launch search.",
                        },
                        "provider": {
                            "type": "string",
                            "description": "Exact launch service provider name.",
                        },
                        "rocket": {
                            "type": "string",
                            "description": "Rocket name substring.",
                        },
                        "start_date": {
                            "type": "string",
                            "format": "date-time",
                            "description": "Earliest launch NET in ISO 8601 form.",
                        },
                        "end_date": {
                            "type": "string",
                            "format": "date-time",
                            "description": "Latest launch NET in ISO 8601 form.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_launch",
                "description": (
                    "Get launch details by Launch Library UUID or API URL."
                ),
                "endpoint": "/tools/get_launch",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "launch_id": {
                            "type": "string",
                            "description": (
                                "Launch Library UUID, for example "
                                "5af31461-bce5-4cfb-a0ee-b527cf285d90."
                            ),
                        }
                    },
                    "required": ["launch_id"],
                },
            },
        ],
    }


@app.post("/tools/get_upcoming_launches", response_model=ChatToolResponse)
async def tool_get_upcoming_launches(
    request: Request,
    payload: UpcomingLaunchesRequest,
) -> ChatToolResponse:
    try:
        return ChatToolResponse(
            result=await get_upcoming_launches(_client(request), payload)
        )
    except LaunchLibraryError as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/search_launches", response_model=ChatToolResponse)
async def tool_search_launches(
    request: Request,
    payload: SearchLaunchesRequest,
) -> ChatToolResponse:
    try:
        return ChatToolResponse(result=await search_launches(_client(request), payload))
    except LaunchLibraryError as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/get_launch", response_model=ChatToolResponse)
async def tool_get_launch(
    request: Request,
    payload: LaunchDetailsRequest,
) -> ChatToolResponse:
    try:
        return ChatToolResponse(result=await get_launch(_client(request), payload))
    except LaunchLibraryError as exc:
        return ChatToolResponse(error=str(exc))
