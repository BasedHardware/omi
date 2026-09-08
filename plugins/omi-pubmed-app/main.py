import html
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from models import ChatToolResponse

app = FastAPI(
    title="Omi PubMed App",
    description="PubMed chat tools for Omi",
    version="1.0.1",
)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = 20.0


def _safe(value: Any) -> str:
    return html.unescape(str(value)) if value is not None else ""


def _is_valid_pmid(pmid: str) -> bool:
    return pmid.isdigit() and len(pmid) <= 12


def _clamp_max_results(value: Any, default: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 10))


def _extract_article_fields(record: dict) -> dict:
    title = _safe(record.get("title", "Untitled"))
    pubdate = _safe(record.get("pubdate", ""))
    source = _safe(record.get("source", ""))
    doi = _safe(record.get("elocationid", ""))
    authors = []
    for author in record.get("authors", [])[:8]:
        name = _safe(author.get("name"))
        if name:
            authors.append(name)

    abstract = ""
    if isinstance(record.get("abstract"), list):
        abstract = " ".join(_safe(x) for x in record["abstract"] if x)
    elif record.get("abstract"):
        abstract = _safe(record["abstract"])

    return {
        "title": title,
        "pubdate": pubdate,
        "source": source,
        "doi": doi,
        "authors": authors,
        "abstract": abstract,
    }


async def _fetch_json(client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
    resp = await client.get(f"{EUTILS}/{endpoint}", params=params)
    resp.raise_for_status()
    return resp.json()


async def _search_ids(client: httpx.AsyncClient, query: str, retmax: int = 5) -> list[str]:
    data = await _fetch_json(
        client,
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": _clamp_max_results(retmax),
            "sort": "relevance",
        },
    )
    return data.get("esearchresult", {}).get("idlist", [])


async def _fetch_summaries(client: httpx.AsyncClient, ids: list[str]) -> dict:
    if not ids:
        return {}
    data = await _fetch_json(
        client,
        "esummary.fcgi",
        {"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    return data.get("result", {})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def home():
    return HTMLResponse(
        """
        <html><body style='font-family:sans-serif;max-width:680px;margin:40px auto;'>
        <h1>Omi PubMed App</h1>
        <p>Use PubMed search and article lookup from Omi chat.</p>
        <p>Manifest: <code>/.well-known/omi-tools.json</code></p>
        </body></html>
        """
    )


@app.get("/.well-known/omi-tools.json")
async def manifest():
    return {
        "tools": [
            {
                "name": "search_pubmed",
                "description": "Search PubMed by keywords and return relevant papers.",
                "endpoint": "/tools/search_pubmed",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "1-10, default 5"},
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching PubMed...",
            },
            {
                "name": "get_pubmed_article",
                "description": "Get detailed citation and abstract for a PubMed ID.",
                "endpoint": "/tools/get_pubmed_article",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "pmid": {"type": "string", "description": "PubMed ID (numeric)"},
                    },
                    "required": ["pmid"],
                },
                "auth_required": False,
                "status_message": "Fetching PubMed article...",
            },
            {
                "name": "get_related_pubmed",
                "description": "Find related PubMed articles from a PubMed ID.",
                "endpoint": "/tools/get_related_pubmed",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "pmid": {"type": "string", "description": "PubMed ID (numeric)"},
                        "max_results": {"type": "integer", "description": "1-10, default 5"},
                    },
                    "required": ["pmid"],
                },
                "auth_required": False,
                "status_message": "Finding related PubMed articles...",
            },
        ]
    }


@app.get("/manifest.json")
async def manifest_alias():
    return await manifest()


@app.post("/tools/search_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def search_pubmed(request: Request):
    try:
        body = await request.json()
        query = (body.get("query") or "").strip()
        max_results = _clamp_max_results(body.get("max_results", 5))
        if not query:
            return ChatToolResponse(error="query is required")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            ids = await _search_ids(client, query, max_results)
            if not ids:
                return ChatToolResponse(result=f"No PubMed results found for: {query}")
            summaries = await _fetch_summaries(client, ids)

        lines = [f"Top PubMed results for: {query}"]
        for idx, result_pmid in enumerate(ids, start=1):
            row = summaries.get(result_pmid, {})
            title = _safe(row.get("title", "Untitled"))
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {result_pmid}: {title} ({journal}, {date})")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        return ChatToolResponse(error=f"PubMed search failed: {e}")


@app.post("/tools/get_pubmed_article", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_pubmed_article(request: Request):
    try:
        body = await request.json()
        pmid = (body.get("pmid") or "").strip()
        if not pmid:
            return ChatToolResponse(error="pmid is required")
        if not _is_valid_pmid(pmid):
            return ChatToolResponse(error="pmid must be a numeric PubMed ID")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            summaries = await _fetch_summaries(client, [pmid])

        if pmid not in summaries:
            return ChatToolResponse(error=f"No PubMed record found for PMID {pmid}")

        record = _extract_article_fields(summaries[pmid])
        lines = [
            f"PMID {pmid}",
            f"Title: {record['title']}",
            f"Authors: {', '.join(record['authors']) if record['authors'] else 'N/A'}",
            f"Journal/Date: {record['source']} ({record['pubdate']})",
            f"DOI/Location: {record['doi'] or 'N/A'}",
        ]
        if record["abstract"]:
            lines.append(f"Abstract: {record['abstract'][:1800]}")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch PubMed article: {e}")


@app.post("/tools/get_related_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_related_pubmed(request: Request):
    try:
        body = await request.json()
        pmid = (body.get("pmid") or "").strip()
        max_results = _clamp_max_results(body.get("max_results", 5))
        if not pmid:
            return ChatToolResponse(error="pmid is required")
        if not _is_valid_pmid(pmid):
            return ChatToolResponse(error="pmid must be a numeric PubMed ID")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            data = await _fetch_json(
                client,
                "elink.fcgi",
                {
                    "dbfrom": "pubmed",
                    "db": "pubmed",
                    "id": pmid,
                    "linkname": "pubmed_pubmed",
                    "retmode": "json",
                },
            )

            linksets = data.get("linksets", [])
            related = []
            if linksets:
                dbs = linksets[0].get("linksetdbs", [])
                if dbs:
                    related = [str(x) for x in dbs[0].get("links", [])[:max_results]]

            if not related:
                return ChatToolResponse(result=f"No related articles found for PMID {pmid}")

            summaries = await _fetch_summaries(client, related)

        lines = [f"Related PubMed articles for PMID {pmid}:"]
        for idx, related_pmid in enumerate(related, start=1):
            row = summaries.get(related_pmid, {})
            title = _safe(row.get("title", "Untitled"))
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {related_pmid}: {title} ({journal}, {date})")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch related PubMed articles: {e}")
