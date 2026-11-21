"""
Datamuse Integration App for Omi.

Provides chat tools for finding rhymes, synonyms, related words, and spelling
suggestions using the public Datamuse word-finding API.
"""

from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


DATAMUSE_BASE_URL = "https://api.datamuse.com"
REQUEST_TIMEOUT_SECONDS = 10
MAX_WORDS = 15


app = FastAPI(
    title="Omi Datamuse Integration",
    description="Find rhymes, synonyms, related words, and spelling suggestions from Omi chat tools",
    version="1.0.0",
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class WordRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=80)


class RelatedWordsRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=80)
    relation: Literal["synonym", "rhyme", "adjective", "noun", "follows", "triggers"] = "synonym"


class SpellingRequest(BaseModel):
    partial: str = Field(..., min_length=1, max_length=80)


def _clean_query(value: str) -> str:
    return " ".join(str(value).strip().split())


_RELATION_PARAMS = {
    "synonym": "rel_syn",
    "rhyme": "rel_rhy",
    "adjective": "rel_jjb",
    "noun": "rel_jja",
    "follows": "rel_bga",
    "triggers": "rel_trg",
}


async def _request_json(client: httpx.AsyncClient, url: str, params: Optional[dict[str, Any]] = None) -> Any:
    response = await client.get(url, params=params or {})
    response.raise_for_status()
    return response.json()


def _extract_words(payload: Any) -> list[str]:
    """Pull the `word` field out of a Datamuse result list, skipping malformed rows."""
    if not isinstance(payload, list):
        return []
    return [item["word"] for item in payload if isinstance(item, dict) and isinstance(item.get("word"), str)]


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi Datamuse Integration</title></head>
      <body>
        <h1>Omi Datamuse Integration</h1>
        <p>Use Omi chat tools to find rhymes, synonyms, related words, and spelling suggestions.</p>
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
        "name": "Datamuse",
        "description": "Find rhymes, synonyms, related words, and spelling suggestions from Omi.",
        "tools": [
            {
                "name": "find_rhymes",
                "description": "Find words that rhyme with a given word.",
                "endpoint": "/tools/find_rhymes",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "Word to rhyme with, such as 'time'.",
                        },
                    },
                    "required": ["word"],
                },
            },
            {
                "name": "find_related_words",
                "description": "Find synonyms, rhymes, adjectives, associated words, or words that follow a word.",
                "endpoint": "/tools/find_related_words",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "Seed word, such as 'ocean'.",
                        },
                        "relation": {
                            "type": "string",
                            "enum": ["synonym", "rhyme", "adjective", "noun", "follows", "triggers"],
                            "default": "synonym",
                        },
                    },
                    "required": ["word"],
                },
            },
            {
                "name": "suggest_spelling",
                "description": "Suggest completions or corrections for a partial or misspelled word.",
                "endpoint": "/tools/suggest_spelling",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "partial": {
                            "type": "string",
                            "description": "Partial or misspelled word, such as 'eleph'.",
                        },
                    },
                    "required": ["partial"],
                },
            },
        ],
    }


@app.post("/tools/find_rhymes", response_model=ChatToolResponse)
async def find_rhymes(request: WordRequest) -> ChatToolResponse:
    word = _clean_query(request.word)
    if not word:
        return ChatToolResponse(error="word is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(
                client,
                f"{DATAMUSE_BASE_URL}/words",
                {"rel_rhy": word, "max": MAX_WORDS},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Datamuse request failed: {exc}")

    words = _extract_words(payload)
    if not words:
        return ChatToolResponse(result=f"No rhymes found for '{word}'.")

    lines = [f"Words that rhyme with '{word}':"]
    lines.append(", ".join(words))
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/find_related_words", response_model=ChatToolResponse)
async def find_related_words(request: RelatedWordsRequest) -> ChatToolResponse:
    word = _clean_query(request.word)
    if not word:
        return ChatToolResponse(error="word is required")

    param = _RELATION_PARAMS[request.relation]
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(
                client,
                f"{DATAMUSE_BASE_URL}/words",
                {param: word, "max": MAX_WORDS},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Datamuse request failed: {exc}")

    words = _extract_words(payload)
    label = {
        "synonym": "Synonyms",
        "rhyme": "Rhymes",
        "adjective": "Adjectives describing",
        "noun": "Nouns described by",
        "follows": "Words that often follow",
        "triggers": "Words associated with",
    }[request.relation]
    if not words:
        return ChatToolResponse(result=f"{label} '{word}': none found.")

    lines = [f"{label} '{word}':"]
    lines.append(", ".join(words))
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/suggest_spelling", response_model=ChatToolResponse)
async def suggest_spelling(request: SpellingRequest) -> ChatToolResponse:
    partial = _clean_query(request.partial)
    if not partial:
        return ChatToolResponse(error="partial word is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(
                client,
                f"{DATAMUSE_BASE_URL}/sug",
                {"s": partial, "max": MAX_WORDS},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Datamuse request failed: {exc}")

    words = _extract_words(payload)
    if not words:
        return ChatToolResponse(result=f"No suggestions for '{partial}'.")

    lines = [f"Suggestions for '{partial}':"]
    lines.append(", ".join(words))
    return ChatToolResponse(result="\n".join(lines))
