"""PubMed Integration App for Omi.

Provides chat tools for searching PubMed literature, retrieving structured citations
with abstracts, and discovering related articles via NCBI E-utilities.
"""

from contextlib import asynccontextmanager
import html
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

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
USER_AGENT = "omi-pubmed-app/1.0.2 (https://omi.me)"


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manage HTTP client lifecycle for connection reuse."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi PubMed App",
    description="PubMed chat tools for Omi",
    version="1.0.2",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


def _safe(value: Any) -> str:
    return html.unescape(str(value)).strip() if value is not None else ""


def _is_valid_pmid(pmid: str) -> bool:
    return bool(pmid and pmid.isdigit() and len(pmid) <= 12)


def _clamp_max_results(value: Any, default: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 10))


def _extract_abstract_from_efetch_xml(xml_text: str) -> str:
    """Parse efetch XML and return the abstract text for the first article."""
    if not xml_text:
        return ""
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


def _get_client() -> Optional[httpx.AsyncClient]:
    """Retrieve shared persistent client from app state if available."""
    client = getattr(app.state, "http_client", None)
    if client is not None and getattr(client, "is_closed", False) is not True:
        return client
    return None


async def _fetch_json(endpoint: str, params: dict, client: Optional[httpx.AsyncClient] = None) -> dict:
    """Fetch and decode JSON from NCBI E-utilities with client reuse and fallback."""
    cli = client or _get_client()
    if cli is not None:
        resp = await cli.get(f"{EUTILS}/{endpoint}", params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError(f"NCBI E-utilities returned invalid response format: expected JSON object, got {type(data).__name__}")
        return data

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as fallback_client:
        resp = await fallback_client.get(f"{EUTILS}/{endpoint}", params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError(f"NCBI E-utilities returned invalid response format: expected JSON object, got {type(data).__name__}")
        return data


async def _fetch_abstract(pmid: str, client: Optional[httpx.AsyncClient] = None) -> str:
    """ESummary has no abstract field; efetch XML does."""
    cli = client or _get_client()
    if cli is not None:
        resp = await cli.get(
            f"{EUTILS}/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
        )
        resp.raise_for_status()
        return _extract_abstract_from_efetch_xml(resp.text)

    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as fallback_client:
        resp = await fallback_client.get(
            f"{EUTILS}/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
        )
        resp.raise_for_status()
        return _extract_abstract_from_efetch_xml(resp.text)


def _extract_article_fields(record: Any) -> dict:
    if not isinstance(record, dict):
        return {
            "title": "Untitled",
            "pubdate": "",
            "source": "",
            "doi": "",
            "authors": [],
            "abstract": "",
        }
    title = _safe(record.get("title", "Untitled")) or "Untitled"
    pubdate = _safe(record.get("pubdate", ""))
    source = _safe(record.get("source", ""))
    doi = _safe(record.get("elocationid", ""))
    authors = []
    raw_authors = record.get("authors", [])
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
    elif raw_abstract:
        abstract = _safe(raw_abstract)

    return {
        "title": title,
        "pubdate": pubdate,
        "source": source,
        "doi": doi,
        "authors": authors,
        "abstract": abstract,
    }


async def _search_ids(query: str, retmax: int = 5, client: Optional[httpx.AsyncClient] = None) -> List[str]:
    data = await _fetch_json(
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": _clamp_max_results(retmax),
            "sort": "relevance",
        },
        client=client,
    )
    if not isinstance(data, dict):
        return []
    esearch = data.get("esearchresult")
    if not isinstance(esearch, dict):
        return []
    idlist = esearch.get("idlist", [])
    if not isinstance(idlist, list):
        return []
    return [str(x) for x in idlist if str(x).isdigit()]


def _select_related_pmids(links: Any, source_pmid: str, max_results: int) -> List[str]:
    """NCBI's pubmed_pubmed linkset includes the source PMID among the results;
    exclude it before applying the limit so max_results counts only articles
    actually related to it."""
    if not isinstance(links, list):
        return []
    return [str(x) for x in links if str(x).isdigit() and str(x) != str(source_pmid)][:max_results]


async def _fetch_summaries(ids: List[str], client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    if not ids:
        return {}
    data = await _fetch_json(
        "esummary.fcgi",
        {"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        client=client,
    )
    if not isinstance(data, dict):
        return {}
    result = data.get("result", {})
    if not isinstance(result, dict):
        return {}
    return result


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
async def search_pubmed(req: SearchPubmedRequest) -> ChatToolResponse:
    query = req.query.strip()
    if not query:
        return ChatToolResponse(error="query is required")
    max_results = req.max_results

    try:
        ids = await _search_ids(query, max_results)
        if not ids:
            return ChatToolResponse(result=f"No PubMed results found for: {query}")
        summaries = await _fetch_summaries(ids)

        lines = [f"Top PubMed results for: {query}"]
        for idx, result_pmid in enumerate(ids, start=1):
            row = summaries.get(result_pmid)
            if not isinstance(row, dict):
                lines.append(f"{idx}. PMID {result_pmid}: Untitled (, )")
                continue
            title = _safe(row.get("title", "Untitled")) or "Untitled"
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {result_pmid}: {title} ({journal}, {date})")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"PubMed search failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"PubMed search failed: {exc}")
    except ValueError as exc:
        return ChatToolResponse(error=f"PubMed search failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error searching PubMed: {exc}")


@app.post("/tools/get_pubmed_article", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_pubmed_article(req: GetPubmedArticleRequest) -> ChatToolResponse:
    pmid = req.pmid.strip()
    if not pmid:
        return ChatToolResponse(error="pmid is required")
    if not _is_valid_pmid(pmid):
        return ChatToolResponse(error="pmid must be a numeric PubMed ID")

    try:
        summaries = await _fetch_summaries([pmid])
        if pmid in summaries and isinstance(summaries[pmid], dict):
            try:
                abstract = await _fetch_abstract(pmid)
            except Exception:
                abstract = ""
            if abstract:
                summaries[pmid]["abstract"] = abstract

        if pmid not in summaries or not isinstance(summaries[pmid], dict):
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
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Failed to fetch PubMed article with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Failed to fetch PubMed article: {exc}")
    except ValueError as exc:
        return ChatToolResponse(error=f"Failed to fetch PubMed article: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error fetching PubMed article: {exc}")


@app.post("/tools/get_related_pubmed", response_model=ChatToolResponse, tags=["chat_tools"])
async def get_related_pubmed(req: GetRelatedPubmedRequest) -> ChatToolResponse:
    pmid = req.pmid.strip()
    max_results = req.max_results
    if not pmid:
        return ChatToolResponse(error="pmid is required")
    if not _is_valid_pmid(pmid):
        return ChatToolResponse(error="pmid must be a numeric PubMed ID")

    try:
        data = await _fetch_json(
            "elink.fcgi",
            {
                "dbfrom": "pubmed",
                "db": "pubmed",
                "id": pmid,
                "linkname": "pubmed_pubmed",
                "retmode": "json",
            },
        )

        related = []
        if isinstance(data, dict):
            linksets = data.get("linksets", [])
            if isinstance(linksets, list) and linksets and isinstance(linksets[0], dict):
                dbs = linksets[0].get("linksetdbs", [])
                if isinstance(dbs, list) and dbs and isinstance(dbs[0], dict):
                    raw_links = dbs[0].get("links", [])
                    related = _select_related_pmids(raw_links, pmid, max_results)

        if not related:
            return ChatToolResponse(result=f"No related articles found for PMID {pmid}")

        summaries = await _fetch_summaries(related)

        lines = [f"Related PubMed articles for PMID {pmid}:"]
        for idx, related_pmid in enumerate(related, start=1):
            row = summaries.get(related_pmid)
            if not isinstance(row, dict):
                lines.append(f"{idx}. PMID {related_pmid}: Untitled (, )")
                continue
            title = _safe(row.get("title", "Untitled")) or "Untitled"
            journal = _safe(row.get("fulljournalname", row.get("source", "")))
            date = _safe(row.get("pubdate", ""))
            lines.append(f"{idx}. PMID {related_pmid}: {title} ({journal}, {date})")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Failed to fetch related PubMed articles with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Failed to fetch related PubMed articles: {exc}")
    except ValueError as exc:
        return ChatToolResponse(error=f"Failed to fetch related PubMed articles: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error fetching related PubMed articles: {exc}")
