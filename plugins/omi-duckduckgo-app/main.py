"""
DuckDuckGo Instant Answers & Search Integration App for Omi.

Provides real-time instant factual summaries, definitions, and topic
disambiguation via DuckDuckGo's public Instant Answers API without requiring API keys.
"""

from contextlib import asynccontextmanager
import html
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from models import (
        ChatToolResponse,
        DefineTermRequest,
        InstantAnswerRequest,
        SearchTopicsRequest,
    )
except ImportError:
    from .models import (
        ChatToolResponse,
        DefineTermRequest,
        InstantAnswerRequest,
        SearchTopicsRequest,
    )

DUCKDUCKGO_API_URL = "https://api.duckduckgo.com/"
REQUEST_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "Omi-DuckDuckGo-Plugin/1.0"},
    ) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi DuckDuckGo Instant Answers Integration",
    description="Look up instant answers, entity definitions, and web topics from DuckDuckGo in Omi chat.",
    version="1.0.0",
    lifespan=lifespan,
)


def _clean_text(text: Optional[str]) -> str:
    """Strip HTML tags and unescape HTML entities."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return html.unescape(clean).strip()


def _extract_related_topics(related_topics: Any, max_count: int = 5) -> List[Dict[str, str]]:
    """Flatten and extract related topic items from DuckDuckGo response."""
    items: List[Dict[str, str]] = []
    if not isinstance(related_topics, list):
        return items

    for entry in related_topics:
        if len(items) >= max_count:
            break
        if not isinstance(entry, dict):
            continue

        # Nested topic category
        if "Topics" in entry and isinstance(entry["Topics"], list):
            for sub in entry["Topics"]:
                if len(items) >= max_count:
                    break
                if isinstance(sub, dict) and sub.get("Text"):
                    items.append({
                        "text": _clean_text(sub.get("Text")),
                        "url": sub.get("FirstURL", "").strip(),
                    })
        elif entry.get("Text"):
            items.append({
                "text": _clean_text(entry.get("Text")),
                "url": entry.get("FirstURL", "").strip(),
            })

    return items


async def _query_duckduckgo(
    query: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Execute async query against DuckDuckGo Instant Answer API."""
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "no_redirect": "1",
        "skip_disambig": "0",
    }
    should_close = False
    if client is None:
        client = getattr(app.state, "http_client", None)
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        should_close = True

    try:
        response = await client.get(DUCKDUCKGO_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return {"error": "DuckDuckGo returned an invalid non-dictionary response."}
        return data
    except httpx.TimeoutException:
        return {"error": "DuckDuckGo request timed out. Please try again."}
    except httpx.HTTPStatusError as e:
        return {"error": f"DuckDuckGo API HTTP {e.response.status_code} error: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Failed to connect to DuckDuckGo API: {str(e)}"}
    finally:
        if should_close:
            await client.aclose()


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DuckDuckGo Instant Answers for Omi</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }
        h1 { color: #de5833; }
        .card { background: #f9f9fb; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        code { background: #eef1f5; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
        .endpoint { font-weight: bold; color: #0366d6; }
        .badge { display: inline-block; background: #e3f2fd; color: #0d47a1; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; }
    </style>
</head>
<body>
    <h1>🦆 DuckDuckGo Instant Answers for Omi</h1>
    <p>This integration provides fast, privacy-preserving factual answers, Wikipedia entity summaries, and dictionary definitions directly to Omi.</p>

    <div class="card">
        <h3>Available Chat Tools</h3>
        <ul>
            <li><span class="endpoint">POST /tools/instant_answer</span> — Instant topic abstract, direct answer, and source citation.</li>
            <li><span class="endpoint">POST /tools/search_topics</span> — Related topic exploration and disambiguation snippets.</li>
            <li><span class="endpoint">POST /tools/define_term</span> — Dictionary definition lookup.</li>
        </ul>
    </div>

    <div class="card">
        <h3>Metadata & Setup</h3>
        <p><a href="/manifest.json">Omi App Manifest</a> | <a href="/.well-known/ai-plugin.json">AI Plugin Spec</a> | <a href="/health">Health Check</a> | <a href="/privacy">Privacy</a></p>
    </div>
</body>
</html>"""


@app.get("/health")
async def health():
    return {"status": "ok", "service": "omi-duckduckgo-app"}


@app.get("/privacy")
async def privacy():
    return {
        "privacy_policy": "Omi DuckDuckGo Integration does not store, log, or share any personal user data or search history."
    }


@app.get("/manifest.json")
@app.get("/.well-known/ai-plugin.json")
async def plugin_manifest():
    return {
        "schema_version": "v1",
        "name_for_human": "DuckDuckGo Instant Answers",
        "name_for_model": "duckduckgo_answers",
        "description_for_human": "Instant entity summaries, dictionary definitions, and web topics from DuckDuckGo.",
        "description_for_model": "Look up instant answers, factual knowledge abstracts, dictionary definitions, and related topics via DuckDuckGo.",
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": "/openapi.json"
        },
        "logo_url": "https://duckduckgo.com/assets/logo_header.alt.v108.svg",
        "contact_email": "support@omi.me",
        "legal_info_url": "/privacy"
    }


@app.post("/tools/instant_answer", response_model=ChatToolResponse)
async def instant_answer(req: InstantAnswerRequest):
    """Retrieve instant answer or entity abstract from DuckDuckGo."""
    data = await _query_duckduckgo(req.query)
    if "error" in data:
        return ChatToolResponse(error=data["error"])

    # 1. Check direct computation/answer
    answer = _clean_text(data.get("Answer"))
    if answer:
        ans_type = data.get("AnswerType", "Direct Answer")
        formatted = f"**{ans_type}**: {answer}"
        return ChatToolResponse(result=formatted)

    # 2. Check abstract summary
    heading = _clean_text(data.get("Heading")) or req.query
    abstract = _clean_text(data.get("AbstractText") or data.get("Abstract"))
    source = data.get("AbstractSource", "").strip()
    url = data.get("AbstractURL", "").strip()

    if abstract:
        lines = [f"### {heading}", "", abstract]
        if req.include_sources and (source or url):
            src_part = f"Source: {source}" if source else "Source: DuckDuckGo"
            if url:
                lines.extend(["", f"{src_part} ({url})"])
            else:
                lines.extend(["", src_part])
        return ChatToolResponse(result="\n".join(lines))

    # 3. Check definition
    definition = _clean_text(data.get("Definition"))
    if definition:
        def_source = data.get("DefinitionSource", "Dictionary").strip()
        def_url = data.get("DefinitionURL", "").strip()
        lines = [f"### Definition: {heading}", "", definition]
        if req.include_sources and (def_source or def_url):
            src_str = f"Source: {def_source}"
            if def_url:
                lines.extend(["", f"{src_str} ({def_url})"])
            else:
                lines.extend(["", src_str])
        return ChatToolResponse(result="\n".join(lines))

    # 4. Check official results
    results = data.get("Results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict) and first.get("Text"):
            res_text = _clean_text(first.get("Text"))
            res_url = first.get("FirstURL", "").strip()
            lines = [f"### {heading}", "", res_text]
            if req.include_sources and res_url:
                lines.extend(["", f"URL: {res_url}"])
            return ChatToolResponse(result="\n".join(lines))

    # 5. Check related topics (e.g. disambiguation)
    related = _extract_related_topics(data.get("RelatedTopics"), max_count=5)
    if related:
        lines = [f"### Topics matching '{req.query}':", ""]
        for item in related:
            txt = item["text"]
            url_part = f" — {item['url']}" if (req.include_sources and item["url"]) else ""
            lines.append(f"- {txt}{url_part}")
        return ChatToolResponse(result="\n".join(lines))

    return ChatToolResponse(
        result=f"No instant answer or detailed summary was found on DuckDuckGo for '{req.query}'."
    )


@app.post("/tools/search_topics", response_model=ChatToolResponse)
async def search_topics(req: SearchTopicsRequest):
    """Retrieve related topics and disambiguation snippets."""
    data = await _query_duckduckgo(req.query)
    if "error" in data:
        return ChatToolResponse(error=data["error"])

    limit = req.limit or 5
    related = _extract_related_topics(data.get("RelatedTopics"), max_count=limit)

    if not related:
        abstract = _clean_text(data.get("AbstractText") or data.get("Abstract"))
        if abstract:
            heading = _clean_text(data.get("Heading")) or req.query
            url = data.get("AbstractURL", "").strip()
            url_suffix = f" ({url})" if url else ""
            return ChatToolResponse(result=f"**{heading}**: {abstract}{url_suffix}")
        return ChatToolResponse(
            result=f"No related topics or disambiguations found for '{req.query}'."
        )

    lines = [f"### Related Topics for '{req.query}':", ""]
    for i, item in enumerate(related, start=1):
        txt = item["text"]
        url_part = f" [Link]({item['url']})" if item["url"] else ""
        lines.append(f"{i}. {txt}{url_part}")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/define_term", response_model=ChatToolResponse)
async def define_term(req: DefineTermRequest):
    """Look up dictionary definition for a word or term."""
    data = await _query_duckduckgo(req.term)
    if "error" in data:
        return ChatToolResponse(error=data["error"])

    term_heading = _clean_text(data.get("Heading")) or req.term
    definition = _clean_text(data.get("Definition"))
    def_source = data.get("DefinitionSource", "").strip() or "Dictionary"
    def_url = data.get("DefinitionURL", "").strip()

    if definition:
        lines = [f"**{term_heading}** (via {def_source}):", "", definition]
        if def_url:
            lines.extend(["", f"Reference: {def_url}"])
        return ChatToolResponse(result="\n".join(lines))

    # Fallback to abstract if dictionary definition isn't directly tagged
    abstract = _clean_text(data.get("AbstractText") or data.get("Abstract"))
    if abstract:
        source = data.get("AbstractSource", "").strip() or "Encyclopedia"
        url = data.get("AbstractURL", "").strip()
        lines = [f"**{term_heading}** (via {source}):", "", abstract]
        if url:
            lines.extend(["", f"Reference: {url}"])
        return ChatToolResponse(result="\n".join(lines))

    return ChatToolResponse(
        result=f"No dictionary definition found for '{req.term}' on DuckDuckGo."
    )
