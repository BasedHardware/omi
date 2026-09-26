"""
Stack Overflow Integration App for Omi.

Provides chat tools for searching Stack Overflow and reading question answers
through the public Stack Exchange API.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import unescape
import math
import re
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


STACK_API_BASE_URL = "https://api.stackexchange.com/2.3"
REQUEST_TIMEOUT_SECONDS = 10
MAX_LIMIT = 10
DEFAULT_SITE = "stackoverflow"
USER_AGENT = "omi-stack-overflow-app/1.0 (https://omi.me)"

SITE_HOSTS = {
    "stackoverflow": "stackoverflow.com",
    "serverfault": "serverfault.com",
    "superuser": "superuser.com",
    "askubuntu": "askubuntu.com",
    "mathoverflow": "mathoverflow.net",
    "stackapps": "stackapps.com",
}

_stack_client: Optional[httpx.AsyncClient] = None


def _new_stack_client() -> httpx.AsyncClient:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers)


async def _get_stack_client() -> httpx.AsyncClient:
    global _stack_client
    if _stack_client is None or _stack_client.is_closed:
        _stack_client = _new_stack_client()
    return _stack_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _stack_client
    _stack_client = _new_stack_client()
    try:
        yield
    finally:
        if _stack_client is not None:
            await _stack_client.aclose()


app = FastAPI(
    title="Omi Stack Overflow Integration",
    description="Search Stack Overflow and read answers from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


def _safe_limit(limit: Any, default: int = 5, max_limit: int = MAX_LIMIT) -> int:
    """Safely coerces limit to an integer clamped between 1 and max_limit."""
    if limit is None or isinstance(limit, bool):
        return default
    try:
        if isinstance(limit, (int, float)):
            if not math.isfinite(limit):
                return default
            val = int(limit)
        elif isinstance(limit, str):
            cleaned = limit.strip()
            if not cleaned:
                return default
            val = int(float(cleaned)) if "." in cleaned else int(cleaned)
        else:
            return default
    except (ValueError, TypeError, OverflowError):
        return default
    return max(1, min(val, max_limit))


def _safe_site(site: Any) -> str:
    """Normalizes and validates Stack Exchange API site slug."""
    if not isinstance(site, str):
        return DEFAULT_SITE
    value = site.strip().lower()
    if not value or not re.fullmatch(r"[a-z0-9.-]{2,40}", value):
        return DEFAULT_SITE
    return value


def _safe_tags(tags: Any) -> Optional[str]:
    """Sanitizes tags from comma/semicolon/space separated strings or lists."""
    if not tags or isinstance(tags, bool):
        return None
    if isinstance(tags, list):
        values = tags
    elif isinstance(tags, str):
        values = re.split(r"[,;\s]+", tags)
    else:
        return None

    cleaned = []
    for tag in values:
        if not isinstance(tag, str):
            continue
        t = tag.strip().lower()
        if re.fullmatch(r"[a-z0-9.+#-]{1,35}", t):
            cleaned.append(t)

    return ";".join(cleaned[:5]) if cleaned else None


def _coerce_bool(value: Any) -> Optional[bool]:
    """Safely coerces truthy/falsy representations to a boolean."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    cleaned = str(value).strip().lower()
    if cleaned in {"1", "true", "yes", "y"}:
        return True
    if cleaned in {"0", "false", "no", "n"}:
        return False
    return None


def _clean_text(value: Any) -> str:
    """Strips HTML formatting, invisible characters, and normalizes spacing."""
    if not isinstance(value, str) or not value.strip():
        return ""

    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", value)
    text = re.sub(r"<pre[^>]*>|</pre>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<code[^>]*>|</code>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|blockquote|ul|ol|li|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_date(timestamp: Optional[int]) -> str:
    """Formats a Unix epoch timestamp to YYYY-MM-DD string."""
    if not timestamp or not isinstance(timestamp, (int, float)):
        return "unknown date"
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return "unknown date"


def _parse_question_target(value: Any) -> tuple[Optional[int], Optional[str]]:
    """Extracts integer question ID and optional site slug from raw ID, URL, or prefixed string."""
    if value is None or isinstance(value, bool):
        return None, None

    if isinstance(value, int):
        return (value if value > 0 else None), None

    if isinstance(value, float):
        if math.isfinite(value) and value > 0 and value.is_integer():
            return int(value), None
        return None, None

    if not isinstance(value, str):
        return None, None

    candidate = value.strip()
    if not candidate:
        return None, None

    inferred_site: Optional[str] = None

    # Handle full or partial URLs
    if "://" in candidate or candidate.startswith(("stackoverflow.com", "superuser.com", "serverfault.com")):
        try:
            target_url = candidate if "://" in candidate else f"https://{candidate}"
            parsed = urlsplit(target_url)
            host = (parsed.hostname or "").lower()
            if host:
                for site_slug, domain in SITE_HOSTS.items():
                    if host == domain or host.endswith(f".{domain}"):
                        inferred_site = site_slug
                        break
                if not inferred_site and host.endswith(".stackexchange.com"):
                    inferred_site = host.split(".stackexchange.com")[0]

            path_match = re.search(r"/(?:questions|q)/([0-9]+)", parsed.path)
            if path_match:
                return int(path_match.group(1)), inferred_site
        except Exception:
            pass

    # Strip conversational prefixes: "question: 123", "#123", "id: 123"
    cleaned = re.sub(r"^(?:question(?:\s*id)?|id)\s*[:=]?\s*", "", candidate, flags=re.IGNORECASE)
    cleaned = cleaned.lstrip("#").strip()

    if re.fullmatch(r"[0-9]+", cleaned):
        qid = int(cleaned)
        return (qid if qid > 0 else None), inferred_site

    return None, None


async def _request_json(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Issues an HTTP GET request to Stack Exchange API with error and backoff handling."""
    client = await _get_stack_client()
    response = await client.get(f"{STACK_API_BASE_URL}{path}", params=params)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return {}
    if data.get("error_id"):
        raise ValueError(data.get("error_message") or "Stack Exchange API returned an error")
    if data.get("backoff"):
        raise ValueError(f"Stack Exchange requested a {data['backoff']} second backoff. Retry shortly.")
    return data


def _question_url(site: str, question_id: Any) -> str:
    """Constructs canonical web URL for a question."""
    if site.endswith(".stackoverflow"):
        host = f"{site}.com"
    elif site.endswith(".serverfault"):
        host = f"{site}.com"
    elif site.endswith(".superuser"):
        host = f"{site}.com"
    else:
        host = SITE_HOSTS.get(site, f"{site}.stackexchange.com")
    return f"https://{host}/questions/{question_id}"


def _format_question(item: Any, index: int, site: str) -> str:
    """Formats a single question summary item defensively."""
    if not isinstance(item, dict):
        return f"{index}. Untitled question"

    title = _clean_text(item.get("title")) or "Untitled question"
    question_id = item.get("question_id")
    score = item.get("score") if isinstance(item.get("score"), int) else 0
    answers = item.get("answer_count") if isinstance(item.get("answer_count"), int) else 0
    views = item.get("view_count") if isinstance(item.get("view_count"), int) else 0

    # Stack Exchange distinguishes "has any answer" from "has an accepted answer"
    accepted = "accepted" if item.get("accepted_answer_id") else "not accepted"
    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        tags = ", ".join(str(t) for t in raw_tags if isinstance(t, str)) or "no tags"
    else:
        tags = "no tags"

    link = str(item.get("link") or "").strip() or _question_url(site, question_id)

    return (
        f"{index}. {title}\n"
        f"   {score} score | {answers} answers | {views} views | {accepted}\n"
        f"   Tags: {tags}\n"
        f"   {link}"
    )


def _format_answer(item: Any, index: int) -> str:
    """Formats an answer item defensively, safeguarding against owner NoneType crashes."""
    if not isinstance(item, dict):
        return f"{index}. unknown | 0 score\nNo answer content available."

    owner = item.get("owner")
    owner_name = "unknown"
    if isinstance(owner, dict):
        owner_name = str(owner.get("display_name") or "").strip() or "unknown"

    score = item.get("score") if isinstance(item.get("score"), int) else 0
    accepted = " | accepted" if item.get("is_accepted") else ""
    body = _clean_text(item.get("body"))
    if len(body) > 1600:
        body = body[:1600].rstrip() + "..."

    return f"{index}. {owner_name} | {score} score{accepted}\n{body}"


@app.get("/")
async def root():
    return HTMLResponse(
        """
        <html>
        <head><title>Stack Overflow x Omi</title></head>
        <body style="font-family: sans-serif; max-width: 640px; margin: 48px auto; line-height: 1.5;">
            <h1>Stack Overflow x Omi</h1>
            <p>Search developer questions, inspect question details, and read top answers from Omi.</p>
            <p>No sign-in or API key is required.</p>
        </body>
        </html>
        """
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "search_questions",
                "description": "Search Stack Overflow or another Stack Exchange site for developer questions. Use this when the user asks how to solve a programming problem or wants related Q&A threads.",
                "endpoint": "/tools/search_questions",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-form search query, such as an error message, API name, or programming problem.",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Optional comma- or semicolon-separated tags, such as python, react, fastapi.",
                        },
                        "site": {
                            "type": "string",
                            "description": "Stack Exchange API site slug. Defaults to stackoverflow.",
                        },
                        "accepted": {
                            "type": "boolean",
                            "description": "Optional filter for questions with accepted answers.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum questions to return. Defaults to 5, maximum 10.",
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching Stack Overflow...",
            },
            {
                "name": "get_question",
                "description": "Get details for a specific Stack Overflow question ID, including title, score, tags, and body excerpt.",
                "endpoint": "/tools/get_question",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_id": {
                            "type": "integer",
                            "description": "Stack Overflow question ID or question URL.",
                        },
                        "site": {
                            "type": "string",
                            "description": "Stack Exchange API site slug. Defaults to stackoverflow.",
                        },
                    },
                    "required": ["question_id"],
                },
                "auth_required": False,
                "status_message": "Fetching Stack Overflow question...",
            },
            {
                "name": "get_top_answers",
                "description": "Get the highest-voted answers for a specific Stack Overflow question ID.",
                "endpoint": "/tools/get_top_answers",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_id": {
                            "type": "integer",
                            "description": "Stack Overflow question ID or question URL.",
                        },
                        "site": {
                            "type": "string",
                            "description": "Stack Exchange API site slug. Defaults to stackoverflow.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum answers to return. Defaults to 3, maximum 10.",
                        },
                    },
                    "required": ["question_id"],
                },
                "auth_required": False,
                "status_message": "Fetching Stack Overflow answers...",
            },
        ]
    }


@app.post("/tools/search_questions", tags=["chat_tools"], response_model=ChatToolResponse)
async def search_questions(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload")

    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return ChatToolResponse(error="Missing required field: query")

    clean_query = query.strip()
    site = _safe_site(payload.get("site"))
    limit = _safe_limit(payload.get("limit"))
    params: dict[str, Any] = {
        "site": site,
        "q": clean_query,
        "pagesize": limit,
        "order": "desc",
        "sort": "relevance",
    }
    tags = _safe_tags(payload.get("tags"))
    if tags:
        params["tagged"] = tags
    accepted = _coerce_bool(payload.get("accepted"))
    if accepted is not None:
        params["accepted"] = "true" if accepted else "false"

    try:
        data = await _request_json("/search/advanced", params)
        raw_items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(raw_items, list):
            return ChatToolResponse(result=f"No Stack Exchange questions found for '{clean_query}'.")

        items = [item for item in raw_items if isinstance(item, dict)][:limit]
        if not items:
            return ChatToolResponse(result=f"No Stack Exchange questions found for '{clean_query}'.")

        lines = [f"Stack Exchange results for '{clean_query}' on {site}:"]
        lines.extend(_format_question(item, index, site) for index, item in enumerate(items, start=1))
        return ChatToolResponse(result="\n\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=f"Stack Exchange search failed: {exc}")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Stack Exchange search failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Stack Exchange search failed: {exc}")


@app.post("/tools/get_question", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_question(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload")

    raw_target = payload.get("question_id")
    if raw_target is None or (isinstance(raw_target, str) and not raw_target.strip()):
        return ChatToolResponse(error="Missing required field: question_id")

    question_id, inferred_site = _parse_question_target(raw_target)
    if question_id is None:
        return ChatToolResponse(error="question_id must be an integer ID or valid Stack Exchange question URL")

    site = _safe_site(payload.get("site"))
    if payload.get("site") is None and inferred_site:
        site = inferred_site

    try:
        data = await _request_json(
            f"/questions/{question_id}",
            {"site": site, "filter": "withbody", "pagesize": 1},
        )
        raw_items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(raw_items, list) or not raw_items:
            return ChatToolResponse(error=f"No question found for ID {question_id} on {site}.")

        item = raw_items[0] if isinstance(raw_items[0], dict) else {}
        if not item:
            return ChatToolResponse(error=f"No question found for ID {question_id} on {site}.")

        title = _clean_text(item.get("title")) or "Untitled question"
        body = _clean_text(item.get("body"))
        if len(body) > 1800:
            body = body[:1800].rstrip() + "..."
        raw_tags = item.get("tags")
        if isinstance(raw_tags, list):
            tags = ", ".join(str(t) for t in raw_tags if isinstance(t, str)) or "no tags"
        else:
            tags = "no tags"
        link = str(item.get("link") or "").strip() or _question_url(site, question_id)

        lines = [
            title,
            f"Question ID: {question_id}",
            f"Created: {_format_date(item.get('creation_date'))}",
            f"Score: {item.get('score', 0)} | Answers: {item.get('answer_count', 0)} | Views: {item.get('view_count', 0)}",
            f"Tags: {tags}",
            link,
        ]
        if body:
            lines.extend(["", "Question body:", body])
        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=f"Stack Exchange question request failed: {exc}")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Stack Exchange question request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Stack Exchange question request failed: {exc}")


@app.post("/tools/get_top_answers", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_top_answers(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload")

    raw_target = payload.get("question_id")
    if raw_target is None or (isinstance(raw_target, str) and not raw_target.strip()):
        return ChatToolResponse(error="Missing required field: question_id")

    question_id, inferred_site = _parse_question_target(raw_target)
    if question_id is None:
        return ChatToolResponse(error="question_id must be an integer ID or valid Stack Exchange question URL")

    site = _safe_site(payload.get("site"))
    if payload.get("site") is None and inferred_site:
        site = inferred_site

    limit = _safe_limit(payload.get("limit"), default=3)
    try:
        data = await _request_json(
            f"/questions/{question_id}/answers",
            {
                "site": site,
                "filter": "withbody",
                "pagesize": limit,
                "order": "desc",
                "sort": "votes",
            },
        )
        raw_items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(raw_items, list):
            return ChatToolResponse(result=f"No answers found for question ID {question_id} on {site}.")

        items = [item for item in raw_items if isinstance(item, dict)][:limit]
        if not items:
            return ChatToolResponse(result=f"No answers found for question ID {question_id} on {site}.")

        lines = [f"Top answers for question {question_id} on {site}:", _question_url(site, question_id)]
        lines.extend(_format_answer(item, index) for index, item in enumerate(items, start=1))
        return ChatToolResponse(result="\n\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=f"Stack Exchange answers request failed: {exc}")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Stack Exchange answers request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Stack Exchange answers request failed: {exc}")
