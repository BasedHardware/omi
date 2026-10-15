from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from clinicaltrials import (
    ClinicalTrialsError,
    find_recruiting_trials,
    get_trial,
    search_trials,
)
from models import (
    ChatToolResponse,
    RecruitingTrialsRequest,
    SearchTrialsRequest,
    TrialDetailsRequest,
)


REQUEST_TIMEOUT_SECONDS = 15


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={
            "Accept": "application/json",
        },
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(
    title="Omi ClinicalTrials.gov Integration",
    description="Search public ClinicalTrials.gov study records from Omi chat tools",
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
            error=f"invalid clinical-trials request: {exc.errors()[0]['msg']}"
        ).model_dump(),
    )


def _client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi ClinicalTrials.gov Integration</title></head>
      <body>
        <h1>Omi ClinicalTrials.gov Integration</h1>
        <p>Search public study registrations from Omi conversations.</p>
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
        "name": "ClinicalTrials.gov",
        "description": "Search public clinical-study registrations from Omi.",
        "tools": [
            {
                "name": "search_clinical_trials",
                "description": (
                    "Search ClinicalTrials.gov by condition, intervention, "
                    "location, recruitment status, or phase."
                ),
                "endpoint": "/tools/search_clinical_trials",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {
                            "type": "string",
                            "description": "Disease or condition, such as 'type 2 diabetes'.",
                        },
                        "intervention": {
                            "type": "string",
                            "description": "Treatment or intervention, such as 'remdesivir'.",
                        },
                        "location": {
                            "type": "string",
                            "description": "City, state, country, or facility.",
                        },
                        "status": {
                            "type": "string",
                            "enum": [
                                "RECRUITING",
                                "ACTIVE_NOT_RECRUITING",
                                "ENROLLING_BY_INVITATION",
                                "NOT_YET_RECRUITING",
                                "COMPLETED",
                                "TERMINATED",
                                "WITHDRAWN",
                                "SUSPENDED",
                                "UNKNOWN",
                            ],
                            "default": "RECRUITING",
                        },
                        "phase": {
                            "type": "string",
                            "enum": [
                                "EARLY_PHASE1",
                                "PHASE1",
                                "PHASE2",
                                "PHASE3",
                                "PHASE4",
                                "NA",
                            ],
                        },
                        "page_size": {
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
                "name": "find_recruiting_trials",
                "description": (
                    "Find currently recruiting studies for a condition, "
                    "optionally near a location."
                ),
                "endpoint": "/tools/find_recruiting_trials",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {"type": "string"},
                        "location": {"type": "string"},
                        "page_size": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": ["condition"],
                },
            },
            {
                "name": "get_clinical_trial",
                "description": (
                    "Get a concise study summary from its NCT identifier, "
                    "such as NCT04280705."
                ),
                "endpoint": "/tools/get_clinical_trial",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nct_id": {
                            "type": "string",
                            "pattern": "^NCT[0-9]{8}$",
                            "description": "ClinicalTrials.gov NCT identifier.",
                        }
                    },
                    "required": ["nct_id"],
                },
            },
        ],
    }


@app.post("/tools/search_clinical_trials", response_model=ChatToolResponse)
async def tool_search_clinical_trials(
    request: Request, payload: SearchTrialsRequest
) -> ChatToolResponse:
    try:
        return ChatToolResponse(result=await search_trials(_client(request), payload))
    except ClinicalTrialsError as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/find_recruiting_trials", response_model=ChatToolResponse)
async def tool_find_recruiting_trials(
    request: Request, payload: RecruitingTrialsRequest
) -> ChatToolResponse:
    try:
        return ChatToolResponse(
            result=await find_recruiting_trials(_client(request), payload)
        )
    except ClinicalTrialsError as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/get_clinical_trial", response_model=ChatToolResponse)
async def tool_get_clinical_trial(
    request: Request, payload: TrialDetailsRequest
) -> ChatToolResponse:
    try:
        return ChatToolResponse(
            result=await get_trial(_client(request), payload.nct_id)
        )
    except ClinicalTrialsError as exc:
        return ChatToolResponse(error=str(exc))
