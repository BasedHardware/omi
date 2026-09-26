"""
openFDA Integration App for Omi.

Provides chat tools for searching FDA drug recalls, drug label information,
and food recalls using the public openFDA API. No API key required.
"""

from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


OPENFDA_BASE_URL = "https://api.fda.gov"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RESULTS = 5


app = FastAPI(
    title="Omi openFDA Integration",
    description="Search FDA drug recalls, drug labels, and food recalls from Omi chat tools",
    version="1.0.0",
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class RecallRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=120)


class DrugInfoRequest(BaseModel):
    drug: str = Field(..., min_length=1, max_length=120)


def _clean_query(value: str) -> str:
    return " ".join(str(value).strip().split())


def _first(value: Any) -> str:
    """openFDA returns most fields as one-element lists; unwrap safely."""
    if isinstance(value, list) and value:
        value = value[0]
    return str(value) if isinstance(value, (str, int, float)) else ""


def _truncate(text: str, limit: int = 220) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _format_enforcement(item: Any) -> str:
    """One-line summary of an openFDA enforcement (recall) record."""
    if not isinstance(item, dict):
        return "- Malformed record"
    product = _truncate(_first(item.get("product_description")), 120) or "Unknown product"
    firm = _first(item.get("recalling_firm")) or "unknown firm"
    classification = _first(item.get("classification")) or "?"
    reason = _truncate(_first(item.get("reason_for_recall")), 160)
    date = _first(item.get("recall_initiation_date"))
    date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
    parts = [f"- {product} — {firm}; {classification}"]
    if date_str:
        parts[0] += f"; initiated {date_str}"
    if reason:
        parts.append(f"  Reason: {reason}")
    return "\n".join(parts)


async def _request_json(client: httpx.AsyncClient, url: str, params: Optional[dict[str, Any]] = None) -> Any:
    response = await client.get(url, params=params or {})
    response.raise_for_status()
    return response.json()


async def _search_enforcement(client: httpx.AsyncClient, endpoint: str, query: str) -> Any:
    """Search an openFDA enforcement endpoint; returns None on a 404 no-match."""
    response = await client.get(
        f"{OPENFDA_BASE_URL}/{endpoint}/enforcement.json",
        params={"search": f'product_description:"{query}"', "limit": MAX_RESULTS},
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi openFDA Integration</title></head>
      <body>
        <h1>Omi openFDA Integration</h1>
        <p>Use Omi chat tools to search FDA drug recalls, drug labels, and food recalls.</p>
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
        "name": "openFDA",
        "description": "Search FDA drug recalls, drug label information, and food recalls from Omi.",
        "tools": [
            {
                "name": "search_drug_recalls",
                "description": "Search FDA drug recall (enforcement) reports by product name or keyword.",
                "endpoint": "/tools/search_drug_recalls",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Drug name or keyword, such as 'aspirin' or 'metformin'.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_drug_info",
                "description": "Get FDA drug label information: purpose, warnings, and drug interactions.",
                "endpoint": "/tools/get_drug_info",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drug": {
                            "type": "string",
                            "description": "Brand or generic drug name, such as 'tylenol' or 'ibuprofen'.",
                        },
                    },
                    "required": ["drug"],
                },
            },
            {
                "name": "search_food_recalls",
                "description": "Search FDA food recall (enforcement) reports by food name or keyword.",
                "endpoint": "/tools/search_food_recalls",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Food name, allergen, or keyword, such as 'peanut' or 'spinach'.",
                        },
                    },
                    "required": ["query"],
                },
            },
        ],
    }


@app.post("/tools/search_drug_recalls", response_model=ChatToolResponse)
async def search_drug_recalls(request: RecallRequest) -> ChatToolResponse:
    query = _clean_query(request.query)
    if not query:
        return ChatToolResponse(error="query is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _search_enforcement(client, "drug", query)
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"openFDA request failed: {exc}")

    results = (payload or {}).get("results") or []
    if not results:
        return ChatToolResponse(result=f"No FDA drug recalls found for '{query}'.")

    lines = [f"FDA drug recalls for '{query}':"]
    lines.extend(_format_enforcement(item) for item in results[:MAX_RESULTS])
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/search_food_recalls", response_model=ChatToolResponse)
async def search_food_recalls(request: RecallRequest) -> ChatToolResponse:
    query = _clean_query(request.query)
    if not query:
        return ChatToolResponse(error="query is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _search_enforcement(client, "food", query)
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"openFDA request failed: {exc}")

    results = (payload or {}).get("results") or []
    if not results:
        return ChatToolResponse(result=f"No FDA food recalls found for '{query}'.")

    lines = [f"FDA food recalls for '{query}':"]
    lines.extend(_format_enforcement(item) for item in results[:MAX_RESULTS])
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_drug_info", response_model=ChatToolResponse)
async def get_drug_info(request: DrugInfoRequest) -> ChatToolResponse:
    drug = _clean_query(request.drug)
    if not drug:
        return ChatToolResponse(error="drug name is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{OPENFDA_BASE_URL}/drug/label.json",
                params={
                    "search": f'openfda.brand_name:"{drug}" openfda.generic_name:"{drug}"',
                    "limit": 1,
                },
            )
            if response.status_code == 404:
                return ChatToolResponse(result=f"No FDA drug label found for '{drug}'.")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"openFDA request failed: {exc}")

    results = payload.get("results") if isinstance(payload, dict) else None
    if not results or not isinstance(results[0], dict):
        return ChatToolResponse(result=f"No FDA drug label found for '{drug}'.")

    label = results[0]
    openfda = label.get("openfda") or {}
    brand = _first(openfda.get("brand_name")) or drug
    generic = _first(openfda.get("generic_name"))
    manufacturer = _first(openfda.get("manufacturer_name"))

    lines = [f"FDA label: {brand}"]
    if generic and generic.lower() != brand.lower():
        lines.append(f"Generic: {generic}")
    if manufacturer:
        lines.append(f"Manufacturer: {manufacturer}")
    for field, title in [
        ("purpose", "Purpose"),
        ("warnings", "Warnings"),
        ("drug_interactions", "Interactions"),
    ]:
        text = _truncate(_first(label.get(field)), 300)
        if text:
            lines.append(f"{title}: {text}")
    return ChatToolResponse(result="\n".join(lines))
