<content>
import asyncio
import logging
from typing import Any, Dict, Optional, Union

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, constr

app = FastAPI()

logger = logging.getLogger(__name__)

PUBMED_API_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_API_KEY = "YOUR_API_KEY"  # Replace with your actual API key or use environment variable


class SearchQuery(BaseModel):
    query: constr(min_length=1)
    max_results: int = Field(5, ge=1, le=100)


class ArticleQuery(BaseModel):
    pmid: constr(min_length=1)
    include_related: bool = False


class RelatedPapersQuery(BaseModel):
    pmid: constr(min_length=1)
    max_results: int = Field(5, ge=1, le=100)


def _normalize_pmid(raw: Union[str, int]) -> str:
    """Normalize PMID to string, rejecting booleans and other types."""
    if isinstance(raw, bool):
        raise ValueError("PMID cannot be a boolean")
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, str):
        if not raw.isdigit():
            raise ValueError("PMID must be numeric")
        return raw
    raise ValueError("PMID must be a string or integer")


def _clamp_max_results(value: Any, default: int = 5) -> int:
    """Clamp max_results to a valid range, guarding against booleans."""
    if isinstance(value, bool):
        return default
    try:
        num = int(value)
        return max(1, min(100, num))
    except (ValueError, TypeError):
        return default


@app.post("/tools/search_pubmed")
async def search_pubmed(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        query = body.get("query")
        if query is None or isinstance(query, bool):
            raise HTTPException(status_code=400, detail="Query must be a non-empty string")

        max_results = body.get("max_results", 5)
        try:
            max_results = _clamp_max_results(max_results)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid max_results value")

        # Simulate API call
        return {"results": [{"id": "123", "title": "Sample Article"}]}
    except Exception as e:
        logger.error(f"Error in search_pubmed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/tools/get_pubmed_article")
async def get_pubmed_article(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        pmid = body.get("pmid")
        if pmid is None or isinstance(pmid, bool):
            raise HTTPException(status_code=400, detail="PMID must be a non-empty string or integer")

        try:
            pmid = _normalize_pmid(pmid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid PMID")

        include_related = body.get("include_related", False)
        if not isinstance(include_related, bool):
            raise HTTPException(status_code=400, detail="include_related must be a boolean")

        # Simulate API call
        return {"article": {"id": pmid, "title": "Sample Article"}}
    except Exception as e:
        logger.error(f"Error in get_pubmed_article: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/tools/get_related_pubmed")
async def get_related_pubmed(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        pmid = body.get("pmid")
        if pmid is None or isinstance(pmid, bool):
            raise HTTPException(status_code=400, detail="PMID must be a non-empty string or integer")

        try:
            pmid = _normalize_pmid(pmid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid PMID")

        max_results = body.get("max_results", 5)
        try:
            max_results = _clamp_max_results(max_results)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid max_results value")

        # Simulate API call
        return {"related_articles": [{"id": "123", "title": "Related Article"}]}
    except Exception as e:
        logger.error(f"Error in get_related_pubmed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
</content>