from contextlib import asynccontextmanager
import html
import logging
import re
from typing import Any, Optional
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from models import ChatToolResponse

logger = logging.getLogger("omi-pubmed-app")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = 20.0
USER_AGENT = "omi-pubmed-app/1.0 (https://omi.me)"

_pubmed_client: Optional[httpx.AsyncClient] = None


def _new_pubmed_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )


async def _get_pubmed_client() -> httpx.AsyncClient:
    global _pubmed_client
    if _pubmed_client is None or getattr(_pubmed_client, "is_closed", False):
        _pubmed_client = _new_pubmed_client()
    return _pubmed_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _pubmed_client
    _pubmed_client = _new_pubmed_client()
    try:
        yield
    finally:
        if _pubmed_client is not None and not getattr(_pubmed_client, "is_closed", False):
            await _pubmed_client.aclose()


app = FastAPI(
    title="Omi PubMed App",
    description="PubMed chat tools for Omi",
    version="1.0.4",
    lifespan=lifespan,
)


def _safe(value: Any) -> str:
    return html.unescape(str(value)) if value is not None else ""


def _is_valid_pmid(pmid: str) -> bool:
    return pmid.isdigit() and len(pmid) <= 12


def _normalize_pmid(raw: Any) -> Optional[str]:
    """Normalize a user/agent supplied PubMed identifier to a bare numeric PMID.

    Accepts:
    - Bare numeric strings: '34567890'
    - Formatted prefixes: 'PMID: 34567890', 'pmid:34567890', 'PMID 34567890'
    - PubMed URLs: 'https://pubmed.ncbi.nlm.nih.gov/34567890/', 'https://www.ncbi.nlm.nih.gov/pubmed/34567890'
    Returns bare numeric PMID string if valid, else None.
    """
    if not raw or not isinstance(raw, str):
        return None
    val = raw.strip()

    # Match PubMed URLs: pubmed.ncbi.nlm.nih.gov/<pmid> or /pubmed/<pmid>
    url_match = re.search(r"(?:pubmed\.ncbi\.nlm\.nih\.gov|/pubmed)/(\d+)", val)
    if url_match:
        candidate = url_match.group(1)
        return candidate if _is_valid_pmid(candidate) else None

    # Match PMID prefixes: 'PMID: 12345', 'pmid:12345', 'PMID 12345'
    prefix_match = re.match(r"^(?:pmid\s*:?\s*)(\d+)$", val, re.IGNORECASE)
    if prefix_match:
        candidate = prefix_match.group(1)
        return candidate if _is_valid_pmid(candidate) else None

    # Direct numeric PMID
    if _is_valid_pmid(val):
        return val

    return None


def _clamp_max_results(value: Any, default: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 10))


def _extract_abstract_from_efetch_xml(xml_text: str) -> str:
    """Parse efetch XML and return the abstract text for the first article."""
    if not xml_text or not isinstance(xml_text, str):
        return ""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
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


def _extract_article_fields(record: dict) -> dict:
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
                if name:
                    authors.append(name)
            elif isinstance(author, str) and author.strip():
                authors.append(_safe(author.strip()))

    abstract = ""
    raw_abstract = record.get("abstract")
    if isinstance(raw_abstract, list):
        abstract = " ".join(_safe(x) for x in raw_abstract if x)
    elif isinstance(raw_abstract, str):
        abstract = _safe(raw_abstract)

    return {
        "title": title,
        "pubdate": pubdate,
        "source": source,
        "doi": doi,
        "authors": authors,
        "abstract": abstract,
    }


async def _fetch_json(client: httpx.AsyncClient, endpoint: str, params: dict) -> Any:
    resp = await client.get(f"{EUTILS}/{endpoint}", params=params)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {}


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
    result_data = data.get("esearchresult")
    if not isinstance(result_data, dict):
        return []
    ids = result_data.get("idlist")
    if not isinstance(ids, list):
        return []
    return [str(x) for x in ids if x is not None and str(x).strip()]


def _select_related_pmids(links: Any, source_pmid: str, max_results: int) -> list[str]:
    """NCBI's pubmed_pubmed linkset includes the source PMID among the results;
    exclude it before applying the limit so max_results counts only articles
    actually related to it."""
    if not isinstance(links, list):
        return []
    cleaned = []
    for x in links:
        if x is not None:
            val = str(x).strip()
            if val and val != str(source_pmid):
                cleaned.append(val)
    return cleaned[:max_results]


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
                "description": "Get detailed citation and abstract for a PubMed ID or URL.",
                "endpoint": "/tools/get_pubmed_article",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "pmid": {"type": "string", "description": "PubMed ID (numeric, PMID prefix, or pubmed.ncbi.nlm.nih.gov URL)"},
                    },
                    "required": ["pmid"],
                },
                "auth_required": False,
                "status_message": "Fetching PubMed article...",
            },
            {
                "name": "get_related_pubmed",
                "description": "Find related PubMed articles from a PubMed ID or URL.",
                "endpoint": "/tools/get_related_pubmed",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "pmid": {"type": "string", "description": "PubMed ID (numeric, PMID prefix, or pubmed.ncbi.nlm.nih.gov URL)"},
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
        if not isinstance(body, dict):
            return ChatToolResponse(error="Request body must be a JSON object")
        query = (body.get("query") or "").strip()
        max_results = _clamp_max_results(body.get("max_results", 5))
        if not query:
            return ChatToolResponse(error="query is required")

        client = await _get_pubmed_client()
        ids = await _search_ids(client, query, max_results)
        if not ids:
            return ChatToolResponse(result=f"No PubMed results found for: {query}")
        summaries = await _fetch_summaries(client, ids)

        lines = [f"Top PubMed results for: {query}"]
        for idx, result_pmid in enumerate(ids, start=1):
            row = summaries.get(result_pmid, {})
            if not isinstance(row, dict) or row.get("error"):
                continue
            title = _safe(row.get("title", "Untitled"))
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {result_pmid}: {title} ({journal}, {date})")
        if len(lines) == 1:
            return ChatToolResponse(result=f"No PubMed results found for: {query}")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        logger.error("PubMed search failed: %s", e, exc_info=True)
        return ChatToolResponse(error="PubMed search failed. Please try again later.")


@app.post("/tools/get_pubmed_article", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_pubmed_article(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return ChatToolResponse(error="Request body must be a JSON object")
        raw_pmid = body.get("pmid")
        if not raw_pmid or not str(raw_pmid).strip():
            return ChatToolResponse(error="pmid is required")

        pmid = _normalize_pmid(str(raw_pmid))
        if not pmid:
            return ChatToolResponse(error="pmid must be a numeric PubMed ID")

        client = await _get_pubmed_client()
        summaries = await _fetch_summaries(client, [pmid])
        record_data = summaries.get(pmid) if isinstance(summaries.get(pmid), dict) else None
        if record_data and not record_data.get("error"):
            # Prefer a real efetch abstract; ESummary never includes one.
            # Abstract enrichment is optional so ESummary still works if efetch fails.
            try:
                abstract = await _fetch_abstract(client, pmid)
            except Exception as e:
                logger.warning("Failed to fetch efetch abstract for PMID %s: %s", pmid, e)
                abstract = ""
            if abstract:
                record_data["abstract"] = abstract

        if not record_data or record_data.get("error"):
            return ChatToolResponse(error=f"No PubMed record found for PMID {pmid}")

        record = _extract_article_fields(record_data)
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
        logger.error("Failed to fetch PubMed article: %s", e, exc_info=True)
        return ChatToolResponse(error="Failed to fetch PubMed article. Please try again later.")


@app.post("/tools/get_related_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_related_pubmed(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return ChatToolResponse(error="Request body must be a JSON object")
        raw_pmid = body.get("pmid")
        max_results = _clamp_max_results(body.get("max_results", 5))
        if not raw_pmid or not str(raw_pmid).strip():
            return ChatToolResponse(error="pmid is required")

        pmid = _normalize_pmid(str(raw_pmid))
        if not pmid:
            return ChatToolResponse(error="pmid must be a numeric PubMed ID")

        client = await _get_pubmed_client()
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
            first_ls = linksets[0] if isinstance(linksets[0], dict) else {}
            dbs = first_ls.get("linksetdbs") if isinstance(first_ls, dict) else None
            if isinstance(dbs, list) and dbs:
                first_db = dbs[0] if isinstance(dbs[0], dict) else {}
                raw_links = first_db.get("links") if isinstance(first_db, dict) else None
                if isinstance(raw_links, list):
                    related = _select_related_pmids(raw_links, pmid, max_results)

        if not related:
            return ChatToolResponse(result=f"No related articles found for PMID {pmid}")

        summaries = await _fetch_summaries(client, related)

        lines = [f"Related PubMed articles for PMID {pmid}:"]
        for related_pmid in related:
            row = summaries.get(related_pmid, {})
            if not isinstance(row, dict) or row.get("error"):
                continue
            title = _safe(row.get("title", "Untitled"))
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{len(lines)}. PMID {related_pmid}: {title} ({journal}, {date})")
        if len(lines) == 1:
            return ChatToolResponse(result=f"No related articles found for PMID {pmid}")
        return ChatToolResponse(result="\n".join(lines))
    except Exception as e:
        logger.error("Failed to fetch related PubMed articles: %s", e, exc_info=True)
        return ChatToolResponse(error="Failed to fetch related PubMed articles. Please try again later.")
