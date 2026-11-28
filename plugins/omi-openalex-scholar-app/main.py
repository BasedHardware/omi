"""Omi OpenAlex Scholar Integration App.

Connects Omi wearable devices to the OpenAlex Global Scholarly Knowledge Graph
(250M+ research papers, 90M+ researchers, 100K+ institutions).
Exposes 4 zero-auth voice tools for academic search, author metrics, institution
rankings, and scientific topics.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI

from models import (
    ChatToolResponse,
    SearchResearchPapersRequest,
    GetAuthorProfileRequest,
    GetInstitutionSummaryRequest,
    ExploreAcademicTopicRequest,
    ExploreAcademicConceptRequest,
)

OPENALEX_BASE_URL = "https://api.openalex.org"
REQUEST_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "OmiOpenAlexApp/1.0 (+https://omi.me)"

_client_lock = asyncio.Lock()
_global_client: Optional[httpx.AsyncClient] = None


def _create_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=OPENALEX_BASE_URL,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


async def _get_client() -> httpx.AsyncClient:
    global _global_client
    if _global_client is None or _global_client.is_closed:
        async with _client_lock:
            if _global_client is None or _global_client.is_closed:
                _global_client = _create_http_client()
    return _global_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _global_client
    _global_client = _create_http_client()
    try:
        yield
    finally:
        if _global_client is not None and not _global_client.is_closed:
            await _global_client.aclose()


app = FastAPI(
    title="Omi OpenAlex Scholar Integration App",
    description="Live scientific & scholarly research tools for Omi wearable devices powered by OpenAlex.",
    version="1.0.0",
    lifespan=lifespan,
)


async def _fetch_openalex(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client = await _get_client()
    try:
        response = await client.get(endpoint, params=params)
        if response.status_code == 404:
            return {"results": [], "meta": {"count": 0}}
        if response.status_code == 429:
            raise ValueError("OpenAlex rate limit reached. Please try again in a moment.")
        if response.status_code >= 500:
            raise ValueError(f"OpenAlex service is temporarily unavailable (HTTP {response.status_code}).")
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        raise ValueError("Request to OpenAlex timed out. Please try again.")
    except httpx.RequestError as exc:
        raise ValueError(f"Network error contacting OpenAlex: {exc}")


@app.get("/health")
async def health():
    return {"status": "ok", "app": "omi-openalex-scholar-app", "version": "1.0.0"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools():
    return {
        "schema_version": "1.0",
        "app_name": "omi-openalex-scholar-app",
        "display_name": "OpenAlex Scholar Intelligence",
        "description": "Voice-enabled academic research and scientific discovery tools for Omi smart wearables.",
        "author": "Omi Community",
        "auth_required": False,
        "tools": [
            {
                "name": "search_research_papers",
                "description": "Search millions of peer-reviewed research papers and preprints by title, topic, or keyword.",
                "endpoint": "/tools/search_research_papers",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Keywords, topic, or paper title (e.g. 'CRISPR Cas9', 'attention is all you need').",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 15,
                            "description": "Number of papers to return.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_author_profile",
                "description": "Look up researchers, professors, and scientists to get their h-index, citation metrics, and affiliations.",
                "endpoint": "/tools/get_author_profile",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "author_name": {
                            "type": "string",
                            "description": "Full name of the scholar or scientist (e.g. 'Yann LeCun', 'Geoffrey Hinton').",
                        },
                    },
                    "required": ["author_name"],
                },
            },
            {
                "name": "get_institution_summary",
                "description": "Look up universities and research institutes for their publication volume, citations, and country.",
                "endpoint": "/tools/get_institution_summary",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "institution_name": {
                            "type": "string",
                            "description": "Name of university or institute (e.g. 'MIT', 'Stanford University', 'Oxford').",
                        },
                    },
                    "required": ["institution_name"],
                },
            },
            {
                "name": "explore_academic_topic",
                "description": "Explore scientific or academic topics, research clusters, and subfields with publication counts and domain hierarchy.",
                "endpoint": "/tools/explore_academic_topic",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Scientific topic or research cluster (e.g. 'Quantum Computing', 'CRISPR Gene Editing').",
                        },
                    },
                    "required": ["topic"],
                },
            },
        ],
    }


@app.post("/tools/search_research_papers", response_model=ChatToolResponse)
async def search_research_papers(req: SearchResearchPapersRequest) -> ChatToolResponse:
    try:
        params = {
            "search": req.query,
            "filter": "type:article|preprint|review",
            "per_page": req.limit,
        }
        data = await _fetch_openalex("/works", params=params)
        works = data.get("results") or []
        if not works:
            return ChatToolResponse(result=f"No academic research papers found matching '{req.query}'.")

        lines = [f"Found {len(works)} research papers for '{req.query}':"]
        for idx, work in enumerate(works, 1):
            title = (work.get("title") or "Untitled").strip()
            year = work.get("publication_year") or "Unknown Year"
            citations = work.get("cited_by_count") or 0

            # Authors
            authorships = work.get("authorships") or []
            authors_list = [
                a.get("author", {}).get("display_name", "")
                for a in authorships
                if isinstance(a, dict) and isinstance(a.get("author"), dict)
            ]
            authors_str = ", ".join([a for a in authors_list if a][:3])
            if len(authorships) > 3:
                authors_str += " et al."
            if not authors_str:
                authors_str = "Unknown Authors"

            # Open Access URL: distinguish between direct PDF and repository landing page
            best_oa = work.get("best_oa_location") or {}
            pdf_url = best_oa.get("pdf_url") if isinstance(best_oa, dict) else None
            landing_url = best_oa.get("landing_page_url") if isinstance(best_oa, dict) else None
            if not landing_url:
                oa = work.get("open_access") or {}
                landing_url = oa.get("oa_url") if isinstance(oa, dict) else None

            if pdf_url:
                oa_str = f" | [Open Access PDF]({pdf_url})"
            elif landing_url:
                oa_str = f" | [Open Access Link]({landing_url})"
            else:
                oa_str = ""

            # DOI
            doi = work.get("doi")
            doi_str = f" | DOI: {doi}" if doi else ""

            lines.append(f"{idx}. **{title}** ({year})")
            lines.append(f"   Authors: {authors_str} | Citations: {citations:,}{doi_str}{oa_str}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error searching research papers: {exc}")


@app.post("/tools/get_author_profile", response_model=ChatToolResponse)
async def get_author_profile(req: GetAuthorProfileRequest) -> ChatToolResponse:
    try:
        data = await _fetch_openalex("/authors", params={"search": req.author_name, "per_page": 3})
        authors = data.get("results") or []
        if not authors:
            return ChatToolResponse(result=f"No researcher profile found for '{req.author_name}'.")

        author = authors[0]
        name = author.get("display_name") or req.author_name
        works_count = author.get("works_count") or 0
        cited_by = author.get("cited_by_count") or 0

        summary_stats = author.get("summary_stats") or {}
        h_index = summary_stats.get("h_index", "N/A") if isinstance(summary_stats, dict) else "N/A"
        i10_index = summary_stats.get("i10_index", "N/A") if isinstance(summary_stats, dict) else "N/A"
        mean_cited = summary_stats.get("2yr_mean_citedness", "N/A") if isinstance(summary_stats, dict) else "N/A"
        if isinstance(mean_cited, (int, float)):
            mean_cited = f"{mean_cited:.2f}"

        # Affiliations (relabeled as last known institutions per OpenAlex semantics)
        affils = author.get("last_known_institutions") or []
        affil_names = [a.get("display_name") for a in affils if isinstance(a, dict) and a.get("display_name")]
        affil_str = ", ".join(affil_names[:2]) if affil_names else "Independent / Unaffiliated"

        # Top research topics
        topics = author.get("topics") or []
        topic_names = [t.get("display_name") for t in topics if isinstance(t, dict) and t.get("display_name")]
        topics_str = ", ".join(topic_names[:3]) if topic_names else "General Sciences"

        lines = [
            f"**Researcher Profile: {name}**",
            f"- Last known institution(s): {affil_str}",
            f"- Total Publications: {works_count:,}",
            f"- Total Citations: {cited_by:,}",
            f"- h-index: {h_index} | i10-index: {i10_index} | 2-Yr Mean Citedness: {mean_cited}",
            f"- Primary Topics: {topics_str}",
        ]
        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error retrieving author profile: {exc}")


@app.post("/tools/get_institution_summary", response_model=ChatToolResponse)
async def get_institution_summary(req: GetInstitutionSummaryRequest) -> ChatToolResponse:
    try:
        data = await _fetch_openalex("/institutions", params={"search": req.institution_name, "per_page": 3})
        institutions = data.get("results") or []
        if not institutions:
            return ChatToolResponse(result=f"No institution found matching '{req.institution_name}'.")

        inst = institutions[0]
        name = inst.get("display_name") or req.institution_name
        country = inst.get("country_code") or "Unknown"
        raw_type = inst.get("type") or "institution"
        inst_type = raw_type.capitalize()
        works = inst.get("works_count") or 0
        citations = inst.get("cited_by_count") or 0
        ror = inst.get("ror") or ""
        ror_str = f" | ROR: {ror}" if ror else ""

        lines = [
            f"**Institution: {name}** ({country})",
            f"- Category: {inst_type}{ror_str}",
            f"- Total Research Publications: {works:,}",
            f"- Total Global Citations: {citations:,}",
        ]
        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error retrieving institution summary: {exc}")


@app.post("/tools/explore_academic_topic", response_model=ChatToolResponse)
@app.post("/tools/explore_academic_concept", response_model=ChatToolResponse)
async def explore_academic_topic(req: ExploreAcademicTopicRequest) -> ChatToolResponse:
    try:
        query_topic = req.topic
        data = await _fetch_openalex("/topics", params={"search": query_topic, "per_page": 3})
        topics = data.get("results") or []
        if not topics:
            return ChatToolResponse(result=f"No academic research topic found for '{query_topic}'.")

        top = topics[0]
        name = top.get("display_name") or query_topic
        desc = top.get("description") or "Research topic cluster"
        works = top.get("works_count") or 0
        citations = top.get("cited_by_count") or 0

        subfield = top.get("subfield", {}).get("display_name") if isinstance(top.get("subfield"), dict) else None
        field = top.get("field", {}).get("display_name") if isinstance(top.get("field"), dict) else None
        domain = top.get("domain", {}).get("display_name") if isinstance(top.get("domain"), dict) else None
        hierarchy_parts = [p for p in [domain, field, subfield] if p]
        hierarchy_str = " > ".join(hierarchy_parts) if hierarchy_parts else "General Sciences"

        keywords = top.get("keywords") or []
        kw_str = ", ".join(keywords[:5]) if isinstance(keywords, list) and keywords else None

        lines = [
            f"**Research Topic: {name}**",
            f"- Domain Hierarchy: {hierarchy_str}",
            f"- Description: {desc}",
            f"- Total Works: {works:,} | Citations: {citations:,}",
        ]
        if kw_str:
            lines.append(f"- Key Concepts: {kw_str}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error exploring academic topic: {exc}")
