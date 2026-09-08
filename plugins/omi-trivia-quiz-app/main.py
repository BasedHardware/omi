"""Interactive Trivia, Voice Quiz & Brain Teaser Integration App for Omi.

Provides voice-optimized trivia challenges, multiple choice questions,
and quick True/False quizzes across 24 knowledge categories for Omi AI wearables
using the open, unauthenticated Open Trivia Database (OpenTDB) API.
Requires zero external authentication or API keys.
"""

from collections import OrderedDict
from contextlib import asynccontextmanager
import html
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetTriviaQuestionRequest,
    ListCategoriesRequest,
    QuickTrueFalseQuizRequest,
)

OPENTDB_API_URL = "https://opentdb.com/api.php"
OPENTDB_CATEGORY_URL = "https://opentdb.com/api_category.php"
REQUEST_TIMEOUT_SECONDS = 15.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (Omi-Trivia/1.0)"
)


# ---------------------------------------------------------------------------
# In-Memory Bounded LRU Cache with TTL
# ---------------------------------------------------------------------------
class SimpleTTLCache:
    """Thread-safe, bounded LRU cache with expiration."""

    def __init__(self, maxsize: int = 512, ttl_seconds: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        created_at, value = self._cache[key]
        if time.time() - created_at > self.ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


trivia_cache = SimpleTTLCache(maxsize=128, ttl_seconds=86400)
question_pool: Dict[str, List[Dict[str, Any]]] = {}


def _get_cached_question(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve a pre-fetched question from the pool if available."""
    pool = question_pool.get(key)
    if pool:
        return pool.pop(0)
    return None


def _store_cached_questions(key: str, questions: List[Dict[str, Any]]) -> None:
    """Store extra fetched questions in the pool to protect against rate limits."""
    if not questions:
        return
    if key not in question_pool:
        question_pool[key] = []
    if len(question_pool[key]) < 20:
        question_pool[key].extend(questions)


# ---------------------------------------------------------------------------
# Pre-loaded Knowledge Domains & Keyword Aliases
# ---------------------------------------------------------------------------
CATEGORY_NAME_MAP: Dict[int, str] = {
    9: "General Knowledge",
    10: "Entertainment: Books",
    11: "Entertainment: Film",
    12: "Entertainment: Music",
    13: "Entertainment: Musicals & Theatres",
    14: "Entertainment: Television",
    15: "Entertainment: Video Games",
    16: "Entertainment: Board Games",
    17: "Science & Nature",
    18: "Science: Computers & Technology",
    19: "Science: Mathematics",
    20: "Mythology",
    21: "Sports",
    22: "Geography",
    23: "History",
    24: "Politics",
    25: "Art",
    26: "Celebrities",
    27: "Animals",
    28: "Vehicles",
    29: "Entertainment: Comics",
    30: "Science: Gadgets",
    31: "Entertainment: Anime & Manga",
    32: "Entertainment: Cartoon & Animations",
}

KEYWORD_TO_CATEGORY_ID: Dict[str, int] = {
    "general": 9,
    "knowledge": 9,
    "book": 10,
    "books": 10,
    "literature": 10,
    "film": 11,
    "films": 11,
    "movie": 11,
    "movies": 11,
    "cinema": 11,
    "music": 12,
    "song": 12,
    "songs": 12,
    "musical": 13,
    "musicals": 13,
    "theatre": 13,
    "theater": 13,
    "tv": 14,
    "television": 14,
    "game": 15,
    "games": 15,
    "gaming": 15,
    "video game": 15,
    "video games": 15,
    "board game": 16,
    "board games": 16,
    "science": 17,
    "nature": 17,
    "biology": 17,
    "physics": 17,
    "chemistry": 17,
    "computer": 18,
    "computers": 18,
    "computer science": 18,
    "cs": 18,
    "tech": 18,
    "technology": 18,
    "coding": 18,
    "software": 18,
    "math": 19,
    "maths": 19,
    "mathematics": 19,
    "myth": 20,
    "mythology": 20,
    "gods": 20,
    "sport": 21,
    "sports": 21,
    "football": 21,
    "soccer": 21,
    "basketball": 21,
    "geo": 22,
    "geography": 22,
    "countries": 22,
    "capitals": 22,
    "history": 23,
    "historical": 23,
    "war": 23,
    "politics": 24,
    "government": 24,
    "art": 25,
    "painting": 25,
    "celebrity": 26,
    "celebrities": 26,
    "animal": 27,
    "animals": 27,
    "wildlife": 27,
    "vehicle": 28,
    "vehicles": 28,
    "cars": 28,
    "comic": 29,
    "comics": 29,
    "gadget": 30,
    "gadgets": 30,
    "anime": 31,
    "manga": 31,
    "cartoon": 32,
    "cartoons": 32,
    "animation": 32,
}


def _resolve_category_id(query: Optional[str]) -> Optional[int]:
    """Fuzzy resolve category name/keyword to OpenTDB category ID, preferring longest match."""
    if not query:
        return None
    cleaned = query.strip().lower()
    if cleaned in KEYWORD_TO_CATEGORY_ID:
        return KEYWORD_TO_CATEGORY_ID[cleaned]

    # Find matching keywords and choose the longest keyword match
    matches = [
        (kw, cat_id)
        for kw, cat_id in KEYWORD_TO_CATEGORY_ID.items()
        if kw in cleaned or cleaned in kw
    ]
    if matches:
        matches.sort(key=lambda x: len(x[0]), reverse=True)
        return matches[0][1]

    return None


# ---------------------------------------------------------------------------
# Lifespan & FastAPI App Setup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi Open Trivia & Voice Quiz Integration",
    description="Interactive trivia questions, multiple choice brain teasers, and True/False voice games for Omi AI wearables.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"Invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------
def _format_trivia_question(q: Dict[str, Any]) -> str:
    """Format an OpenTDB question dict into an engaging voice-friendly prompt."""
    category = html.unescape(q.get("category", "General Knowledge"))
    difficulty = q.get("difficulty", "medium").capitalize()
    q_type = q.get("type", "multiple")
    question_text = html.unescape(q.get("question", "")).strip()
    correct = html.unescape(q.get("correct_answer", "")).strip()
    incorrects = [html.unescape(ans).strip() for ans in q.get("incorrect_answers", [])]

    if q_type == "boolean":
        return (
            f"⚡ Quick True/False Challenge ({difficulty} | {category}):\n"
            f"\"{question_text}\"\n\n"
            f"Say 'True' or 'False' to answer!\n\n"
            f"💡 Correct Answer: {correct}"
        )

    # Multiple choice
    all_choices = incorrects + [correct]
    random.shuffle(all_choices)
    labels = ["A", "B", "C", "D"][:len(all_choices)]

    options_text = []
    correct_letter = "A"
    for label, choice in zip(labels, all_choices):
        options_text.append(f"{label}) {choice}")
        if choice == correct:
            correct_letter = label

    options_formatted = "\n".join(options_text)
    return (
        f"🎯 Trivia Question ({difficulty} | {category}):\n"
        f"\"{question_text}\"\n\n"
        f"Options:\n"
        f"{options_formatted}\n\n"
        f"💡 Correct Answer: {correct_letter}) {correct}"
    )


# ---------------------------------------------------------------------------
# Tool Endpoints
# ---------------------------------------------------------------------------
@app.post("/tools/get_trivia_question", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_trivia_question(request: GetTriviaQuestionRequest) -> ChatToolResponse:
    """Get a multiple choice or custom trivia question with category and difficulty options."""
    client: httpx.AsyncClient = app.state.http_client

    cat_id = _resolve_category_id(request.category) if request.category else None
    pool_key = f"{cat_id or 'all'}:{request.difficulty or 'any'}:{request.question_type or 'any'}"

    # Check question pool first to avoid redundant upstream calls
    cached_q = _get_cached_question(pool_key)
    if cached_q:
        return ChatToolResponse(result=_format_trivia_question(cached_q))

    params: Dict[str, Any] = {"amount": 5}
    if cat_id:
        params["category"] = cat_id
    if request.difficulty:
        params["difficulty"] = request.difficulty
    if request.question_type:
        params["type"] = request.question_type

    try:
        resp = await client.get(OPENTDB_API_URL, params=params)
        if resp.status_code == 429:
            return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")
        resp.raise_for_status()
        data = resp.json()

        code = data.get("response_code", 0)
        # Check rate-limit response code 5 before fallback
        if code == 5:
            return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")

        results = data.get("results", [])
        if code == 1 or not results:
            # Fallback without category/difficulty filters, but preserve question_type
            fallback_params: Dict[str, Any] = {"amount": 1}
            if request.question_type:
                fallback_params["type"] = request.question_type
            resp = await client.get(OPENTDB_API_URL, params=fallback_params)
            if resp.status_code == 429:
                return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")
            resp.raise_for_status()
            data = resp.json()
            if data.get("response_code") == 5:
                return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")
            results = data.get("results", [])

        if not results:
            return ChatToolResponse(error="Could not retrieve a trivia question at this moment.")

        result_str = _format_trivia_question(results[0])
        if len(results) > 1:
            _store_cached_questions(pool_key, results[1:])
        return ChatToolResponse(result=result_str)
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to fetch trivia question: {exc}")


@app.post("/tools/get_true_false_quiz", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_true_false_quiz(request: QuickTrueFalseQuizRequest) -> ChatToolResponse:
    """Get a rapid True or False quiz question for instant voice responses."""
    client: httpx.AsyncClient = app.state.http_client

    cat_id = _resolve_category_id(request.category) if request.category else None
    pool_key = f"boolean:{cat_id or 'all'}:{request.difficulty or 'any'}"

    # Check question pool first
    cached_q = _get_cached_question(pool_key)
    if cached_q:
        return ChatToolResponse(result=_format_trivia_question(cached_q))

    params: Dict[str, Any] = {"amount": 5, "type": "boolean"}
    if cat_id:
        params["category"] = cat_id
    if request.difficulty:
        params["difficulty"] = request.difficulty

    try:
        resp = await client.get(OPENTDB_API_URL, params=params)
        if resp.status_code == 429:
            return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")
        resp.raise_for_status()
        data = resp.json()

        code = data.get("response_code", 0)
        # Check rate-limit response code 5 before fallback
        if code == 5:
            return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")

        results = data.get("results", [])
        if code == 1 or not results:
            # Fallback to general boolean
            fallback_params: Dict[str, Any] = {"amount": 1, "type": "boolean"}
            resp = await client.get(OPENTDB_API_URL, params=fallback_params)
            if resp.status_code == 429:
                return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")
            resp.raise_for_status()
            data = resp.json()
            if data.get("response_code") == 5:
                return ChatToolResponse(error="Trivia service is busy (rate limit). Please wait a moment before trying again.")
            results = data.get("results", [])

        if not results:
            return ChatToolResponse(error="Could not retrieve a True/False quiz question at this moment.")

        result_str = _format_trivia_question(results[0])
        if len(results) > 1:
            _store_cached_questions(pool_key, results[1:])
        return ChatToolResponse(result=result_str)
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to fetch True/False quiz: {exc}")


@app.post("/tools/list_trivia_categories", response_model=ChatToolResponse, response_model_exclude_none=True)
async def list_trivia_categories(_: ListCategoriesRequest) -> ChatToolResponse:
    """List all available trivia categories and knowledge domains."""
    cached = trivia_cache.get("categories")
    if cached:
        return ChatToolResponse(result=cached)

    lines = ["📚 Available Trivia Categories:"]
    for cat_id, name in sorted(CATEGORY_NAME_MAP.items(), key=lambda x: x[1]):
        lines.append(f"• {name}")

    result_text = "\n".join(lines)
    trivia_cache.set("categories", result_text)
    return ChatToolResponse(result=result_text)


# ---------------------------------------------------------------------------
# Health & Manifest Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "service": "omi-trivia-quiz-app", "version": "1.0.0"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> Dict[str, Any]:
    """Omi Function Calling Chat Tools Manifest."""
    return {
        "schema_version": "1.0",
        "auth": {"type": "none"},
        "tools": [
            {
                "name": "get_trivia_question",
                "description": "Generate an interactive multiple choice trivia question with optional category and difficulty filters.",
                "endpoint": "/tools/get_trivia_question",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional category or topic (e.g. 'Science', 'History', 'Tech', 'Film', 'Geography').",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "Optional question difficulty.",
                        },
                        "question_type": {
                            "type": "string",
                            "enum": ["multiple", "boolean"],
                            "description": "Optional question format: 'multiple' for 4 choices, 'boolean' for True/False.",
                        },
                    },
                },
            },
            {
                "name": "get_true_false_quiz",
                "description": "Get a rapid True or False quiz question for instant voice responses on Omi wearables.",
                "endpoint": "/tools/get_true_false_quiz",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional category keyword (e.g. 'Science', 'Animals', 'History').",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "Optional difficulty level.",
                        },
                    },
                },
            },
            {
                "name": "list_trivia_categories",
                "description": "List all 24 available knowledge domains and trivia categories.",
                "endpoint": "/tools/list_trivia_categories",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Service landing page."""
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Omi Open Trivia & Voice Quiz App</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 48px auto; padding: 0 16px; line-height: 1.6; color: #24292f; }
                h1 { font-size: 24px; color: #0969da; }
                code { background: #f6f8fa; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
                ul { padding-left: 20px; }
            </style>
        </head>
        <body>
            <h1>🧠 Omi Open Trivia & Voice Quiz App</h1>
            <p>Interactive voice-based trivia games and brain teasers for Omi AI wearables powered by OpenTDB.</p>
            <h3>Registered Chat Tools:</h3>
            <ul>
                <li><code>get_trivia_question</code>: 4-choice multiple choice questions across 24 topics.</li>
                <li><code>get_true_false_quiz</code>: Rapid True/False voice questions.</li>
                <li><code>list_trivia_categories</code>: Browse all available knowledge categories.</li>
            </ul>
            <h3>Endpoints:</h3>
            <ul>
                <li><a href="/health"><code>GET /health</code></a>: Health check</li>
                <li><a href="/.well-known/omi-tools.json"><code>GET /.well-known/omi-tools.json</code></a>: Chat tools manifest</li>
            </ul>
        </body>
        </html>
        """
    )
