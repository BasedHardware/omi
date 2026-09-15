"""
Stack Overflow Integration App for Omi.

Provides chat tools for searching Stack Overflow and reading question answers
through the public Stack Exchange API.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import unescape
import re
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    DEFAULT_SITE,
    MAX_LIMIT,
    ChatToolResponse,
    GetQuestionRequest,
    GetTopAnswersRequest,
    SearchQuestionsRequest,
    _coerce_bool,
    _safe_limit,
    _safe_site,
    _safe_tags,
)


STACK_API_BASE_URL = "https://api.stackexchange.com/2.3"
REQUEST_TIMEOUT_SECONDS = 10
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0].get("msg", "Invalid request payload") if errors else "Invalid request payload"
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    return JSONResponse(
        status_code=200,
        content={"result": None, "error": msg},
    )


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""

    text = unescape(str(value))
    text = re.sub(r"<pre[^>]*>|</pre>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<code[^>]*>|</code>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|blockquote|ul|ol|li|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_date(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "unknown date"
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return "unknown date"


async def _request_json(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    client = await _get_stack_client()
    response = await client.get(f"{STACK_API_BASE_URL}{path}", params=params)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Invalid JSON response from Stack Exchange API")
    if data.get("error_id"):
        raise ValueError(data.get("error_message") or "Stack Exchange API returned an error")
    if data.get("backoff"):
        raise ValueError(f"Stack Exchange requested a {data['backoff']} second backoff. Retry shortly.")
    return data


def _question_url(site: str, question_id: Any) -> str:
    if site.endswith(".stackoverflow"):
        host = f"{site}.com"
    elif site.endswith(".serverfault"):
        host = f"{site}.com"
    elif site.endswith(".superuser"):
        host = f"{site}.com"
    else:
        host = SITE_HOSTS.get(site, f"{site}.stackexchange.com")
    return f"https://{host}/questions/{question_id}"


def _format_question(item: dict[str, Any], index: int, site: str) -> str:
    title = _clean_text(item.get("title")) or "Untitled question"
    question_id = item.get("question_id")
    score = item.get("score", 0)
    answers = item.get("answer_count", 0)
    views = item.get("view_count", 0)
    # Stack Exchange distinguishes "has any answer" (is_answered) from
    # "has an accepted answer" (accepted_answer_id). Label only the latter.
    accepted = "accepted" if item.get("accepted_answer_id") else "not accepted"
    raw_tags = item.get("tags")
    if isinstance(raw_tags, (list, tuple)):
        tags = ", ".join(str(t) for t in raw_tags if t is not None) or "no tags"
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = raw_tags.strip()
    else:
        tags = "no tags"
    link = item.get("link") or _question_url(site, question_id)

    return (
        f"{index}. {title}\n"
        f"   {score} score | {answers} answers | {views} views | {accepted}\n"
        f"   Tags: {tags}\n"
        f"   {link}"
    )


def _format_answer(item: dict[str, Any], index: int) -> str:
    owner_data = item.get("owner")
    owner = (owner_data.get("display_name") if isinstance(owner_data, dict) else None) or "unknown"
    score = item.get("score", 0)
    accepted = " | accepted" if item.get("is_accepted") else ""
    body = _clean_text(item.get("body"))
    if len(body) > 1600:
        body = body[:1600].rstrip() + "..."

    return f"{index}. {owner} | {score} score{accepted}\n{body}"


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
                            "description": "Stack Overflow question ID.",
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
                            "description": "Stack Overflow question ID.",
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
async def search_questions(payload: SearchQuestionsRequest):
    if isinstance(payload, dict):
        payload = SearchQuestionsRequest(**payload)
    query = payload.query
    site = payload.site or DEFAULT_SITE
    limit = payload.limit or 5
    params: dict[str, Any] = {
        "site": site,
        "q": query,
        "pagesize": limit,
        "order": "desc",
        "sort": "relevance",
    }
    if payload.tags:
        params["tagged"] = payload.tags
    if payload.accepted is not None:
        params["accepted"] = "true" if payload.accepted else "false"

    try:
        data = await _request_json("/search/advanced", params)
        raw_items = data.get("items")
        items = [item for item in raw_items if isinstance(item, dict)][:limit] if isinstance(raw_items, list) else []
        if not items:
            return ChatToolResponse(result=f"No Stack Exchange questions found for '{query}'.")

        lines = [f"Stack Exchange results for '{query}' on {site}:"]
        lines.extend(_format_question(item, index, site) for index, item in enumerate(items, start=1))
        return ChatToolResponse(result="\n\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=f"Stack Exchange search failed: {exc}")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Stack Exchange search failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Stack Exchange search failed: {exc}")


@app.post("/tools/get_question", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_question(payload: GetQuestionRequest):
    if isinstance(payload, dict):
        payload = GetQuestionRequest(**payload)
    question_id = payload.question_id
    site = payload.site or DEFAULT_SITE
    try:
        data = await _request_json(
            f"/questions/{question_id}",
            {"site": site, "filter": "withbody", "pagesize": 1},
        )
        raw_items = data.get("items")
        items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        if not items:
            return ChatToolResponse(error=f"No question found for ID {question_id} on {site}.")

        item = items[0]
        title = _clean_text(item.get("title")) or "Untitled question"
        body = _clean_text(item.get("body"))
        if len(body) > 1800:
            body = body[:1800].rstrip() + "..."
        raw_tags = item.get("tags")
        if isinstance(raw_tags, (list, tuple)):
            tags = ", ".join(str(t) for t in raw_tags if t is not None) or "no tags"
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags = raw_tags.strip()
        else:
            tags = "no tags"
        link = item.get("link") or _question_url(site, question_id)

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
async def get_top_answers(payload: GetTopAnswersRequest):
    if isinstance(payload, dict):
        payload = GetTopAnswersRequest(**payload)
    question_id = payload.question_id
    site = payload.site or DEFAULT_SITE
    limit = payload.limit or 3
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
        raw_items = data.get("items")
        items = [item for item in raw_items if isinstance(item, dict)][:limit] if isinstance(raw_items, list) else []
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
