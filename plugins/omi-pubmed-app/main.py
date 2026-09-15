import html
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetPubmedArticleRequest,
    GetRelatedPubmedRequest,
    SearchPubmedRequest,
)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = 20.0


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi PubMed App",
    description="PubMed chat tools for Omi",
    version="1.0.2",
    lifespan=lifespan,
)


@asynccontextmanager
async def _acquire_client():
    """Yield the lifespan-managed HTTP client, or a transient one if unset."""
    client = getattr(app.state, "http_client", None)
    if client is not None:
        yield client
        return
    async with httpx.AsyncClient(timeout=TIMEOUT) as transient:
        yield transient


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


def _safe(value: Any) -> str:
    return html.unescape(str(value)) if value is not None else ""


def _clamp_max_results(value: Any, default: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 10))


def _extract_abstract_from_efetch_xml(xml_text: str) -> str:
    """Parse efetch XML and return the abstract text for the first article."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    abstract_parts = root.findall(".//AbstractText")
    if not abstract_parts:
        return ""
    chunks = []
    for part in abstract_parts:
        label = (part.get("Label") or "").strip()
        text = "".join(part.itertext()).strip()
        if not text:
            continue
        chunks.append(f"{label}: {text}" if label else text)
    return " ".join(chunks).strip()


async def _fetch_abstract(client: httpx.AsyncClient, pmid: str) -> str:
    """ESummary has no abstract field; efetch XML does."""
    resp = await client.get(
        f"{EUTILS}/efetch.fcgi",
        params={"db": "pubmed", "id": pmid, "retmode": "xml"},
    )
    resp.raise_for_status()
    return _extract_abstract_from_efetch_xml(resp.text)


def _extract_article_fields(record: Any) -> dict:
    if not isinstance(record, dict):
        record = {}
    title = _safe(record.get("title", "Untitled"))
    pubdate = _safe(record.get("pubdate", ""))
    source = _safe(record.get("source", ""))
    doi = _safe(record.get("elocationid", ""))
    authors = []
    raw_authors = record.get("authors")
    if isinstance(raw_authors, list):
        for author in raw_authors[:8]:
            if isinstance(author, dict):
                name = _safe(author.get("name"))
            elif isinstance(author, str):
                name = _safe(author)
            else:
                continue
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
    if not isinstance(data, dict):
        return []
    esearch_result = data.get("esearchresult")
    if not isinstance(esearch_result, dict):
        return []
    idlist = esearch_result.get("idlist")
    if not isinstance(idlist, list):
        return []
    return [str(item) for item in idlist]


async def _fetch_summaries(client: httpx.AsyncClient, ids: list[str]) -> dict:
    if not ids:
        return {}
    data = await _fetch_json(
        client,
        "esummary.fcgi",
        {"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    if not isinstance(data, dict):
        return {}
    result = data.get("result")
    return result if isinstance(result, dict) else {}


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
async def search_pubmed(req: SearchPubmedRequest):
    try:
        query = req.query
        async with _acquire_client() as client:
            ids = await _search_ids(client, query, req.max_results)
            if not ids:
                return ChatToolResponse(result=f"No PubMed results found for: {query}")
            summaries = await _fetch_summaries(client, ids)

        lines = [f"Top PubMed results for: {query}"]
        for idx, result_pmid in enumerate(ids, start=1):
            row = summaries.get(result_pmid)
            if not isinstance(row, dict):
                row = {}
            title = _safe(row.get("title", "Untitled"))
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {result_pmid}: {title} ({journal}, {date})")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        return ChatToolResponse(error=f"PubMed search failed: {e}")


@app.post("/tools/get_pubmed_article", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_pubmed_article(req: GetPubmedArticleRequest):
    try:
        pmid = req.pmid
        async with _acquire_client() as client:
            summaries = await _fetch_summaries(client, [pmid])
            record = summaries.get(pmid)
            if isinstance(record, dict):
                # Prefer a real efetch abstract; ESummary never includes one.
                # Abstract enrichment is optional so ESummary still works if efetch fails.
                try:
                    abstract = await _fetch_abstract(client, pmid)
                except Exception:
                    abstract = ""
                if abstract:
                    record["abstract"] = abstract

        if not isinstance(record, dict):
            return ChatToolResponse(error=f"No PubMed record found for PMID {pmid}")

        fields = _extract_article_fields(record)
        lines = [
            f"PMID {pmid}",
            f"Title: {fields['title']}",
            f"Authors: {', '.join(fields['authors']) if fields['authors'] else 'N/A'}",
            f"Journal/Date: {fields['source']} ({fields['pubdate']})",
            f"DOI/Location: {fields['doi'] or 'N/A'}",
        ]
        if fields["abstract"]:
            lines.append(f"Abstract: {fields['abstract'][:1800]}")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch PubMed article: {e}")


@app.post("/tools/get_related_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_related_pubmed(req: GetRelatedPubmedRequest):
    try:
        pmid = req.pmid
        async with _acquire_client() as client:
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

            linksets = data.get("linksets") if isinstance(data, dict) else None
            related = []
            if isinstance(linksets, list) and linksets:
                first_linkset = linksets[0]
                dbs = first_linkset.get("linksetdbs") if isinstance(first_linkset, dict) else None
                if isinstance(dbs, list) and dbs:
                    links = dbs[0].get("links") if isinstance(dbs[0], dict) else None
                    if isinstance(links, list):
                        related = [str(x) for x in links[: req.max_results]]

            if not related:
                return ChatToolResponse(result=f"No related articles found for PMID {pmid}")

            summaries = await _fetch_summaries(client, related)

        lines = [f"Related PubMed articles for PMID {pmid}:"]
        for idx, related_pmid in enumerate(related, start=1):
            row = summaries.get(related_pmid)
            if not isinstance(row, dict):
                row = {}
            title = _safe(row.get("title", "Untitled"))
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {related_pmid}: {title} ({journal}, {date})")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch related PubMed articles: {e}")
