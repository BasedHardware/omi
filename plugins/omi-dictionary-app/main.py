"""English dictionary and pronunciation tools for Omi, using Free Dictionary API."""

from contextlib import asynccontextmanager
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import TypeAdapter, ValidationError

from models import ChatToolResponse, DefinitionRequest, Entry, WordRequest

API_BASE = "https://api.dictionaryapi.dev/api/v2/entries/en/"


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "Omi-Dictionary/1.0", "Accept": "application/json"},
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as client:
        application.state.http_client = client
        yield


app = FastAPI(title="Omi English Dictionary", version="1.0.0", lifespan=lifespan)


class DictionaryError(Exception):
    """An upstream lookup failure that can be explained to the user."""


async def lookup(word: str) -> list[Entry]:
    try:
        response = await app.state.http_client.get(API_BASE + quote(word, safe=""))
        if response.status_code == 404:
            raise DictionaryError("No entry found. Check the spelling and try the base form of the English word.")
        if response.status_code == 429:
            raise DictionaryError("The dictionary is receiving too many requests. Please try again later.")
        response.raise_for_status()
        entries = TypeAdapter(list[Entry]).validate_json(response.content)
        if not entries:
            raise DictionaryError("The dictionary returned no entries for this word.")
        return entries
    except httpx.TimeoutException as exc:
        raise DictionaryError("The dictionary request timed out. Please try again.") from exc
    except httpx.HTTPError as exc:
        raise DictionaryError("The dictionary service is unavailable. Please try again later.") from exc
    except ValidationError as exc:
        raise DictionaryError("The dictionary returned an unreadable response. Please try again later.") from exc


def text(value: str, limit: int = 300) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"


def public_url(value: str) -> str:
    if value.startswith("//"):
        value = "https:" + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username:
            return value
    except ValueError:
        pass
    return ""


def attribution(entries: list[Entry]) -> list[str]:
    lines = ["Provided by Free Dictionary API (https://dictionaryapi.dev)."]
    for entry in entries:
        for source in entry.sourceUrls:
            if url := public_url(source):
                lines.append(f"Source: {url}")
        if entry.license and (url := public_url(entry.license.url)):
            lines.append(f"License: {text(entry.license.name, 80)} — {url}")
    return list(dict.fromkeys(lines))


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo the incoming body, which may contain Omi's user identifier.
    response = ChatToolResponse(error="Enter an English word of 1–80 characters and a definition limit from 1 to 5.")
    return JSONResponse(status_code=200, content=response.model_dump())


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """<!doctype html><html lang="en"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Omi English Dictionary</title>
    <body style="font:18px system-ui;max-width:650px;margin:3rem auto;padding:0 1rem;color:#222">
    <h1>Omi English Dictionary</h1>
    <p>Look up the meaning or pronunciation of an English word mentioned in conversation.</p>
    <p>No account or API key is needed. Only the requested word is sent to Free Dictionary API;
    this service does not store conversation history.</p>
    <p><a href="/.well-known/omi-tools.json">Omi tool manifest</a> · <a href="/docs">API documentation</a></p>
    <p>Definitions and audio availability vary by word. Sources and licenses accompany results.</p>
    </body></html>"""


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "omi-dictionary-app"}


@app.get("/.well-known/omi-tools.json")
async def manifest() -> dict:
    return {
        "schema_version": "1.0",
        "name": "English Dictionary",
        "description": "English word meanings, examples and pronunciation from Free Dictionary API.",
        "tools": [
            {
                "name": name,
                "description": description,
                "endpoint": f"/tools/{name}",
                "method": "POST",
                "parameters": model.model_json_schema(),
            }
            for name, description, model in [
                (
                    "get_word_definition",
                    "Look up an English word's meanings, usage examples and available synonyms.",
                    DefinitionRequest,
                ),
                (
                    "get_word_pronunciation",
                    "Get phonetic spellings and available audio links for an English word. Does not play audio.",
                    WordRequest,
                ),
            ]
        ],
    }


@app.post("/tools/get_word_definition", response_model=ChatToolResponse)
async def get_word_definition(request: DefinitionRequest) -> ChatToolResponse:
    try:
        entries = await lookup(request.word)
    except DictionaryError as exc:
        return ChatToolResponse(error=str(exc))
    lines = [f"{request.word} — English definitions"]
    used_entries: list[Entry] = []
    count = 0
    for entry in entries:
        for meaning in entry.meanings:
            for definition in meaning.definitions:
                if count >= request.max_definitions:
                    break
                if not text(definition.definition):
                    continue
                count += 1
                used_entries.append(entry)
                lines.append(f"{count}. {text(meaning.partOfSpeech, 40)}: {text(definition.definition)}")
                if definition.example:
                    lines.append(f"Example: {text(definition.example, 180)}")
                synonyms = list(dict.fromkeys(definition.synonyms + meaning.synonyms))[:5]
                if synonyms:
                    lines.append("Synonyms: " + ", ".join(text(word, 80) for word in synonyms))
    if not count:
        return ChatToolResponse(error="This entry has no definitions available.")
    return ChatToolResponse(result="\n".join(lines + attribution(used_entries)))


@app.post("/tools/get_word_pronunciation", response_model=ChatToolResponse)
async def get_word_pronunciation(request: WordRequest) -> ChatToolResponse:
    try:
        entries = await lookup(request.word)
    except DictionaryError as exc:
        return ChatToolResponse(error=str(exc))
    pronunciations: list[str] = []
    for entry in entries:
        if entry.phonetic:
            pronunciations.append(f"Phonetic: {text(entry.phonetic, 100)}")
        for phonetic in entry.phonetics[:5]:
            if phonetic.text:
                pronunciations.append(f"Phonetic: {text(phonetic.text, 100)}")
            if url := public_url(phonetic.audio):
                pronunciations.append(f"Audio: {url}")
                if source := public_url(phonetic.sourceUrl):
                    pronunciations.append(f"Audio source: {source}")
                if phonetic.license and (license_url := public_url(phonetic.license.url)):
                    pronunciations.append(f"Audio license: {text(phonetic.license.name, 80)} — {license_url}")
    if not pronunciations:
        return ChatToolResponse(result=f"No phonetic spelling or audio is available for '{request.word}'.")
    lines = [f"{request.word} — English pronunciation"] + list(dict.fromkeys(pronunciations))
    return ChatToolResponse(result="\n".join(lines + attribution(entries)))
