from contextlib import asynccontextmanager
import os
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    CompanyRequest,
    FinancialSnapshotRequest,
    RecentFilingsRequest,
)
from sec import (
    SecEdgarError,
    get_company_profile,
    get_financial_snapshot,
    list_recent_filings,
)


REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "Omi-SEC-EDGAR-App/1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                os.getenv("SEC_USER_AGENT", "").strip() or DEFAULT_USER_AGENT
            ),
        },
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(
    title="Omi SEC EDGAR Integration",
    description="Look up public SEC company filings from Omi chat tools",
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
            error=f"invalid SEC request: {exc.errors()[0]['msg']}"
        ).model_dump(),
    )


def _client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi SEC EDGAR Integration</title></head>
      <body>
        <h1>Omi SEC EDGAR Integration</h1>
        <p>Look up public company filings from Omi conversations.</p>
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
        "name": "SEC EDGAR",
        "description": "Research public SEC company filings from Omi.",
        "tools": [
            {
                "name": "get_company_profile",
                "description": (
                    "Get a public company's SEC registrant profile by ticker, "
                    "CIK, or company name."
                ),
                "endpoint": "/tools/get_company_profile",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "string",
                            "description": (
                                "Ticker, CIK, or company name, such as AAPL or Apple."
                            ),
                        }
                    },
                    "required": ["company"],
                },
            },
            {
                "name": "list_recent_filings",
                "description": (
                    "List a public company's recent SEC filings, optionally "
                    "filtered by form type."
                ),
                "endpoint": "/tools/list_recent_filings",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "string",
                            "description": "Ticker, CIK, or company name.",
                        },
                        "form_type": {
                            "type": "string",
                            "description": (
                                "Exact SEC form type, such as 10-K, 10-Q, or 8-K."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": ["company"],
                },
            },
            {
                "name": "get_financial_snapshot",
                "description": (
                    "Get recent annual SEC XBRL facts for revenue, net income, "
                    "assets, liabilities, equity, cash, and diluted EPS."
                ),
                "endpoint": "/tools/get_financial_snapshot",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "string",
                            "description": "Ticker, CIK, or company name.",
                        },
                        "years": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                            "default": 3,
                            "description": "Annual periods to return per metric.",
                        },
                    },
                    "required": ["company"],
                },
            },
        ],
    }


@app.post("/tools/get_company_profile", response_model=ChatToolResponse)
async def tool_get_company_profile(
    request: Request,
    payload: CompanyRequest,
) -> ChatToolResponse:
    try:
        return ChatToolResponse(
            result=await get_company_profile(_client(request), payload)
        )
    except SecEdgarError as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/list_recent_filings", response_model=ChatToolResponse)
async def tool_list_recent_filings(
    request: Request,
    payload: RecentFilingsRequest,
) -> ChatToolResponse:
    try:
        return ChatToolResponse(
            result=await list_recent_filings(_client(request), payload)
        )
    except SecEdgarError as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/get_financial_snapshot", response_model=ChatToolResponse)
async def tool_get_financial_snapshot(
    request: Request,
    payload: FinancialSnapshotRequest,
) -> ChatToolResponse:
    try:
        return ChatToolResponse(
            result=await get_financial_snapshot(_client(request), payload)
        )
    except SecEdgarError as exc:
        return ChatToolResponse(error=str(exc))
