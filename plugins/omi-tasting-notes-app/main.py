"""
Tasting Notes Integration App for Omi.

Stay in the moment at tastings — no phone, no notebook. Omi captures the
conversation; this app turns it into structured tasting cards.

Two ways to capture:
  1. Chat tools (explicit): ask Omi to "log this tasting" and dictate or
     confirm the structured fields.
  2. Ambient webhook (implicit): Omi posts the finished Conversation to
     /webhook/tasting-candidate?uid=<user-id> and the app scores the
     transcript for tasting signals. Strong matches are stored as candidates
     flagged `needs_review` so you can confirm them later with the
     `confirm_candidate` chat tool (list them with `list_candidates`).

Beverage types: wine, coffee, whiskey, beer, other.
Scores are normalized to a 100-point scale.

Security note: there is no authentication — anyone who knows a uid can
read and write that user's tastings. The data is low-sensitivity tasting
notes, but treat uids as bearer tokens and don't share them.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from omi_plugin_sdk.models import Conversation

APP_TITLE = "Omi Tasting Notes Integration"
APP_VERSION = "1.1.0"

# Created lazily on first write so importing this module (e.g. repo-wide
# import checks) never touches the disk.
DATA_DIR = Path(os.environ.get("TASTING_DATA_DIR", Path(__file__).parent / "data"))

BEVERAGE_TYPES = ("wine", "coffee", "whiskey", "beer", "other")
VERDICTS = ("buy", "skip", "cellar")

# ---------------------------------------------------------------------------
# Tasting-signal detection (ambient webhook)
# ---------------------------------------------------------------------------

# Weighted vocabulary per beverage type. Weights are deliberately small and
# the threshold conservative: better to miss a tasting than to file a lunch
# conversation as a Barolo review.
TASTING_KEYWORDS: dict[str, dict[str, int]] = {
    "wine": {
        "wine": 3, "winery": 4, "vineyard": 3, "tasting room": 4, "sommelier": 4,
        "vintage": 3, "tannin": 3, "tannins": 3, "bouquet": 3, "terroir": 4,
        "cabernet": 3, "merlot": 3, "pinot": 3, "chardonnay": 3, "riesling": 3,
        "barolo": 4, "bordeaux": 3, "burgundy": 3, "champagne": 3, "sauvignon": 3,
        "syrah": 3, "shiraz": 3, "malbec": 3, "zinfandel": 3, "sangiovese": 3,
        "nebbiolo": 4, "tempranillo": 3, "grenache": 3, "viognier": 3,
        "decant": 3, "aerate": 2, "legs": 2, "swirl": 2, "corked": 3,
        "oaky": 2, "oaked": 2, "full-bodied": 2, "fruit-forward": 2,
    },
    "coffee": {
        "coffee": 3, "espresso": 4, "roast": 2,
        "barista": 4, "pour over": 4, "pour-over": 4,
        "single origin": 4, "french press": 3, "aeropress": 3, "cold brew": 3,
        "crema": 3, "roastery": 4, "cupping": 5, "chemex": 3,
        "v60": 3, "latte art": 2,
    },
    "whiskey": {
        "whiskey": 3, "whisky": 3, "bourbon": 4, "scotch": 4, "rye whiskey": 4,
        "dram": 4, "cask": 3, "cask strength": 4, "single malt": 4,
        "distillery": 4, "peated": 3, "peaty": 3, "neat": 2,
    },
    "beer": {
        "beer": 2, "brewery": 4, "ipa": 3, "stout": 3, "porter": 3, "lager": 2,
        "pilsner": 3, "sour beer": 3, "hazy": 2, "taproom": 4, "flight of": 3,
        "mouthfeel": 2,
    },
}

# Coffee's generic words ("coffee", "espresso", "roast") appear in ordinary
# chatter ("grabbed a coffee, then we talked roadmap"), so coffee additionally
# requires at least one tasting-specific term before it can be detected.
COFFEE_TASTING_TERMS = {
    "barista", "pour over", "pour-over", "single origin", "french press",
    "aeropress", "cold brew", "crema", "roastery", "cupping", "chemex",
    "v60", "latte art",
}

TASTING_DETECT_THRESHOLD = 8

BUY_SIGNALS = (
    "would buy", "will buy", "buy a case", "buying a case", "take home",
    "taking home", "worth buying", "stock up", "cellar worthy",
)
SKIP_SIGNALS = (
    "wouldn't buy", "would not buy", "not buying", "skip this",
    "pass on this",
)
# "not worth" is a skip signal on its own, but not in "not worth missing".
_SKIP_NOT_WORTH_RE = re.compile(r"not worth\b(?!\s+missing)")

# Words that negate a nearby buy signal ("no way we're buying a case").
_BUY_NEGATORS = (
    "not", "no", "never", "don't", "dont", "didn't", "didnt",
    "wouldn't", "wouldnt", "can't", "cant", "won't", "wont",
)
_BUY_NEGATOR_RES = [re.compile(r"\b" + re.escape(n) + r"\b") for n in _BUY_NEGATORS]
_BUY_NEGATION_WINDOW = 40  # characters before the buy signal to scan

_SCORE_100_RE = re.compile(r"(?<!\d)(\d{2,3}(?:\.\d+)?)(?!\d)\s*(?:points|/100|out of 100)")
_SCORE_5_RE = re.compile(r"(?<!\d)(\d(?:\.\d+)?)\s*stars?")
_SCORE_10_RE = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*/\s*10\b")


def _keyword_hits(text: str, beverage: str) -> tuple[int, set[str]]:
    """Return (weighted score, matched phrases) for one beverage vocabulary."""
    total = 0
    hits: set[str] = set()
    for phrase, weight in TASTING_KEYWORDS[beverage].items():
        # Word-boundary match so "winery" doesn't fire on "swinery".
        if re.search(r"\b" + re.escape(phrase) + r"\b", text):
            total += weight
            hits.add(phrase)
    return total, hits


def detect_tasting(text: str) -> tuple[Optional[str], int]:
    """Return (beverage_type, score) for the best-matching tasting vocabulary.

    Returns (None, 0) when the text does not clear the detection threshold.
    Coffee additionally requires a tasting-specific term so ordinary coffee
    chatter ("grabbed a coffee, then we talked roadmap") is not filed.
    """
    lowered = text.lower()
    best: Optional[str] = None
    best_score = 0
    for beverage in TASTING_KEYWORDS:
        total, hits = _keyword_hits(lowered, beverage)
        if beverage == "coffee" and not (hits & COFFEE_TASTING_TERMS):
            continue
        if total > best_score:
            best_score = total
            best = beverage
    if best is not None and best_score >= TASTING_DETECT_THRESHOLD:
        return best, best_score
    return None, 0


def parse_score(text: str) -> Optional[float]:
    """Extract a score from free text and normalize it to a 100-point scale."""
    lowered = text.lower()
    match = _SCORE_100_RE.search(lowered)
    if match:
        return _clamp_score(float(match.group(1)))
    match = _SCORE_5_RE.search(lowered)
    if match:
        return _clamp_score(min(float(match.group(1)), 5.0) * 20.0)
    match = _SCORE_10_RE.search(lowered)
    if match:
        return _clamp_score(float(match.group(1)) * 10.0)
    return None


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, round(value, 1)))


def _buy_signal_negated(lowered: str, signal_start: int) -> bool:
    """Check the window before a buy signal for negating words."""
    window_start = max(0, signal_start - _BUY_NEGATION_WINDOW)
    before = lowered[window_start:signal_start]
    return any(neg.search(before) for neg in _BUY_NEGATOR_RES)


def infer_verdict(text: str) -> Optional[str]:
    """Infer a buy/skip verdict from explicit purchase language only.

    Skip signals are checked first ("wouldn't buy" contains "buy"). Buy
    signals are ignored when a negator (not/no/never/don't/...) appears
    shortly before them, so "no way we're buying a case" is not a buy.
    """
    lowered = text.lower()
    for signal in SKIP_SIGNALS:
        if signal in lowered:
            return "skip"
    if _SKIP_NOT_WORTH_RE.search(lowered):
        return "skip"
    for signal in BUY_SIGNALS:
        for match in re.finditer(re.escape(signal), lowered):
            if not _buy_signal_negated(lowered, match.start()):
                return "buy"
    return None


# ---------------------------------------------------------------------------
# Storage (per-user JSON files, no external DB)
#
# NOTE: hosts with ephemeral disks (Fly.io machines, Railway without a
# volume) wipe these files on every deploy/restart. Run with a persistent
# volume mounted and TASTING_DATA_DIR pointing at it (see README).
# ---------------------------------------------------------------------------

def _user_path(uid: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", uid)[:64] or "anonymous"
    return DATA_DIR / f"{safe}.json"


def _load_user(uid: str) -> dict[str, Any]:
    path = _user_path(uid)
    if not path.exists():
        return {"tastings": [], "candidates": []}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"tastings": [], "candidates": []}
    data.setdefault("tastings", [])
    data.setdefault("candidates", [])
    return data


def _save_user(uid: str, data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _user_path(uid).write_text(json.dumps(data, indent=2))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_tasting(uid: str, source: str, **fields: Any) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": uuid.uuid4().hex[:8],
        "uid": uid,
        "beverage_type": fields.get("beverage_type", "wine"),
        "name": fields.get("name"),
        "producer": fields.get("producer"),
        "vintage": fields.get("vintage"),
        "region": fields.get("region"),
        "varietal": fields.get("varietal"),
        "nose": fields.get("nose"),
        "palate": fields.get("palate"),
        "finish": fields.get("finish"),
        "score_100": fields.get("score_100"),
        "verdict": fields.get("verdict"),
        "notes": fields.get("notes"),
        "source": source,
        "needs_review": bool(fields.get("needs_review", False)),
        "created_at": now,
        "updated_at": now,
    }


def _store_tasting(uid: str, source: str, **fields: Any) -> dict[str, Any]:
    data = _load_user(uid)
    tasting = _new_tasting(uid, source, **fields)
    data["tastings"].append(tasting)
    _save_user(uid, data)
    return tasting


def _conversation_text(conversation: Conversation) -> str:
    """Build plain transcript text from a Conversation.

    Prefers the SDK's get_transcript(); falls back to reading
    transcript_segments directly so dict-shaped segments keep working.
    """
    get_transcript = getattr(conversation, "get_transcript", None)
    if callable(get_transcript):
        try:
            text = get_transcript()
        except Exception:
            text = ""
        if text:
            return text
    parts: list[str] = []
    for segment in getattr(conversation, "transcript_segments", None) or []:
        if isinstance(segment, dict):
            text = segment.get("text")
        else:
            text = getattr(segment, "text", None)
        if text:
            parts.append(str(text))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

class _NullMeansDefault(BaseModel):
    """The Omi backend sends every optional tool parameter the model did not
    supply as JSON null (langchain-core forwards defaulted fields), so a null
    must mean 'use the default', not 'invalid request'."""

    @model_validator(mode="before")
    @classmethod
    def drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class Tasting(BaseModel):
    id: str
    uid: str
    beverage_type: str
    name: Optional[str] = None
    producer: Optional[str] = None
    vintage: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    nose: Optional[str] = None
    palate: Optional[str] = None
    finish: Optional[str] = None
    score_100: Optional[float] = None
    verdict: Optional[str] = None
    notes: Optional[str] = None
    source: str = "chat"
    needs_review: bool = False
    created_at: str
    updated_at: str


class LogTastingRequest(_NullMeansDefault):
    uid: str = Field(..., min_length=1)
    beverage_type: Optional[str] = Field(default="wine")
    name: Optional[str] = None
    producer: Optional[str] = None
    vintage: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    nose: Optional[str] = None
    palate: Optional[str] = None
    finish: Optional[str] = None
    score_100: Optional[float] = Field(default=None, ge=0, le=100)
    verdict: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("beverage_type", mode="before")
    @classmethod
    def normalize_beverage(cls, value: Any) -> str:
        if value is None:
            return "wine"
        normalized = str(value).strip().lower()
        if normalized not in BEVERAGE_TYPES:
            raise ValueError(f"beverage_type must be one of {', '.join(BEVERAGE_TYPES)}")
        return normalized

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        return normalized


def _coerce_limit(value: Any) -> int:
    """Shared limit coercion: null -> default 10, numeric strings accepted,
    enforced to 1..50 (so Field(ge/le) would be redundant)."""
    if value is None:
        return 10
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer between 1 and 50")
    if not 1 <= coerced <= 50:
        raise ValueError("limit must be an integer between 1 and 50")
    return coerced


class ListTastingsRequest(_NullMeansDefault):
    uid: str = Field(..., min_length=1)
    beverage_type: Optional[str] = None
    limit: Optional[int] = 10

    @field_validator("beverage_type", mode="before")
    @classmethod
    def normalize_beverage(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in BEVERAGE_TYPES:
            raise ValueError(f"beverage_type must be one of {', '.join(BEVERAGE_TYPES)}")
        return normalized

    @field_validator("limit", mode="before")
    @classmethod
    def coerce_limit(cls, value: Any) -> int:
        return _coerce_limit(value)


class ListCandidatesRequest(_NullMeansDefault):
    uid: str = Field(..., min_length=1)
    limit: Optional[int] = 10

    @field_validator("limit", mode="before")
    @classmethod
    def coerce_limit(cls, value: Any) -> int:
        return _coerce_limit(value)


class GetTastingRequest(_NullMeansDefault):
    uid: str = Field(..., min_length=1)
    tasting_id: str = Field(..., min_length=1)


class StatsRequest(_NullMeansDefault):
    uid: str = Field(..., min_length=1)


class ConfirmCandidateRequest(_NullMeansDefault):
    uid: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    # Optional corrections applied at confirm time.
    name: Optional[str] = None
    producer: Optional[str] = None
    vintage: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    nose: Optional[str] = None
    palate: Optional[str] = None
    finish: Optional[str] = None
    score_100: Optional[float] = Field(default=None, ge=0, le=100)
    verdict: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        return normalized


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title=APP_TITLE, description=__doc__, version=APP_VERSION)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


def _format_tasting(tasting: dict[str, Any]) -> str:
    lines = []
    header = f"**{tasting.get('name') or 'Untitled tasting'}**"
    meta = [tasting.get("beverage_type", "other")]
    if tasting.get("producer"):
        meta.append(str(tasting["producer"]))
    if tasting.get("vintage"):
        meta.append(str(tasting["vintage"]))
    lines.append(f"{header} ({', '.join(meta)})")
    for field in ("region", "varietal", "nose", "palate", "finish"):
        if tasting.get(field):
            lines.append(f"{field.capitalize()}: {tasting[field]}")
    if tasting.get("score_100") is not None:
        lines.append(f"Score: {tasting['score_100']}/100")
    if tasting.get("verdict"):
        lines.append(f"Verdict: {str(tasting['verdict']).capitalize()}")
    if tasting.get("notes"):
        lines.append(f"Notes: {tasting['notes']}")
    if tasting.get("needs_review"):
        lines.append("_Needs review — confirm with the confirm_candidate tool._")
    return "\n".join(lines)


def _format_candidate(candidate: dict[str, Any]) -> str:
    title = candidate.get("name") or "Untitled candidate"
    score = (
        f" — {candidate['score_100']}/100"
        if candidate.get("score_100") is not None
        else ""
    )
    verdict = f" [{candidate['verdict']}]" if candidate.get("verdict") else ""
    excerpt = (candidate.get("excerpt") or "")[:120]
    return (
        f"- {title} ({candidate.get('beverage_type', 'other')}){score}{verdict} "
        f"(id: {candidate['id']})\n  \"{excerpt}...\""
    )


# ---------------------------------------------------------------------------
# Chat tools
# ---------------------------------------------------------------------------

@app.post("/tools/log_tasting", response_model=ChatToolResponse)
async def log_tasting(request: LogTastingRequest) -> ChatToolResponse:
    """Record a structured tasting from chat ("log this Barolo")."""
    tasting = _store_tasting(
        request.uid,
        "chat",
        beverage_type=request.beverage_type,
        name=request.name,
        producer=request.producer,
        vintage=request.vintage,
        region=request.region,
        varietal=request.varietal,
        nose=request.nose,
        palate=request.palate,
        finish=request.finish,
        score_100=request.score_100,
        verdict=request.verdict,
        notes=request.notes,
    )
    return ChatToolResponse(result="Tasting logged:\n" + _format_tasting(tasting))


@app.post("/tools/list_tastings", response_model=ChatToolResponse)
async def list_tastings(request: ListTastingsRequest) -> ChatToolResponse:
    """List recent tastings, newest first, optionally filtered by beverage."""
    data = _load_user(request.uid)
    tastings = data["tastings"]
    if request.beverage_type:
        tastings = [t for t in tastings if t.get("beverage_type") == request.beverage_type]
    tastings = sorted(tastings, key=lambda t: t.get("created_at", ""), reverse=True)
    if not tastings:
        return ChatToolResponse(result="No tastings logged yet.")
    limit = request.limit or 10
    lines = ["Your tastings:"]
    for tasting in tastings[:limit]:
        title = tasting.get("name") or "Untitled tasting"
        score = f" — {tasting['score_100']}/100" if tasting.get("score_100") is not None else ""
        verdict = f" [{tasting['verdict']}]" if tasting.get("verdict") else ""
        review = " (needs review)" if tasting.get("needs_review") else ""
        lines.append(f"- {title}{score}{verdict}{review} (id: {tasting['id']})")
    if len(tastings) > limit:
        lines.append(f"... {len(tastings) - limit} more")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/list_candidates", response_model=ChatToolResponse)
async def list_candidates(request: ListCandidatesRequest) -> ChatToolResponse:
    """List ambient-detected candidates awaiting review, newest first."""
    data = _load_user(request.uid)
    candidates = sorted(
        data["candidates"], key=lambda c: c.get("created_at", ""), reverse=True
    )
    if not candidates:
        return ChatToolResponse(result="No candidates awaiting review.")
    limit = request.limit or 10
    lines = ["Candidates awaiting review (confirm with confirm_candidate):"]
    for candidate in candidates[:limit]:
        lines.append(_format_candidate(candidate))
    if len(candidates) > limit:
        lines.append(f"... {len(candidates) - limit} more")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_tasting", response_model=ChatToolResponse)
async def get_tasting(request: GetTastingRequest) -> ChatToolResponse:
    """Fetch one tasting by id with full structured details."""
    data = _load_user(request.uid)
    for tasting in data["tastings"]:
        if tasting.get("id") == request.tasting_id:
            return ChatToolResponse(result=_format_tasting(tasting))
    return ChatToolResponse(error=f"no tasting found with id {request.tasting_id}")


@app.post("/tools/tasting_stats", response_model=ChatToolResponse)
async def tasting_stats(request: StatsRequest) -> ChatToolResponse:
    """Aggregate stats: counts, average scores, and buy-rate per beverage."""
    data = _load_user(request.uid)
    tastings = data["tastings"]
    if not tastings:
        return ChatToolResponse(result="No tastings logged yet.")
    lines = [f"Tasting stats ({len(tastings)} total):"]
    by_beverage: dict[str, list[dict[str, Any]]] = {}
    for tasting in tastings:
        by_beverage.setdefault(tasting.get("beverage_type", "other"), []).append(tasting)
    for beverage in sorted(by_beverage):
        group = by_beverage[beverage]
        scores = [t["score_100"] for t in group if t.get("score_100") is not None]
        avg = f", avg {sum(scores) / len(scores):.1f}/100" if scores else ""
        buys = sum(1 for t in group if t.get("verdict") == "buy")
        lines.append(f"- {beverage}: {len(group)}{avg}, {buys} buy verdicts")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/confirm_candidate", response_model=ChatToolResponse)
async def confirm_candidate(request: ConfirmCandidateRequest) -> ChatToolResponse:
    """Confirm an ambient-detected candidate, applying optional corrections."""
    data = _load_user(request.uid)
    candidate = next(
        (c for c in data["candidates"] if c.get("id") == request.candidate_id), None
    )
    if candidate is None:
        return ChatToolResponse(error=f"no candidate found with id {request.candidate_id}")
    # Single load/save round-trip: remove the candidate and append the
    # confirmed tasting to the same in-memory data before persisting, so the
    # new tasting is never overwritten by a stale save.
    data["candidates"] = [c for c in data["candidates"] if c.get("id") != request.candidate_id]
    tasting = _new_tasting(
        request.uid,
        "webhook",
        beverage_type=candidate.get("beverage_type", "wine"),
        name=request.name or candidate.get("name"),
        producer=request.producer,
        vintage=request.vintage,
        region=request.region,
        varietal=request.varietal,
        nose=request.nose,
        palate=request.palate,
        finish=request.finish,
        score_100=request.score_100
        if request.score_100 is not None
        else candidate.get("score_100"),
        verdict=request.verdict or candidate.get("verdict"),
        notes=request.notes or candidate.get("excerpt"),
        needs_review=False,
    )
    data["tastings"].append(tasting)
    _save_user(request.uid, data)
    return ChatToolResponse(result="Candidate confirmed:\n" + _format_tasting(tasting))


# ---------------------------------------------------------------------------
# Ambient webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/tasting-candidate")
async def tasting_candidate(
    conversation: Conversation,
    uid: str = Query(..., description="Omi user id"),
) -> dict[str, Any]:
    """Score a finished Omi conversation for tasting signals.

    Omi posts the Conversation model; the uid arrives as a query parameter
    (e.g. /webhook/tasting-candidate?uid=<user-id>). Strong matches are
    stored as candidates flagged `needs_review`; weak or non-matches are
    ignored. Returns what was detected so the caller can log it.
    """
    if getattr(conversation, "discarded", False):
        return {"detected": False, "reason": "discarded conversation"}

    text = _conversation_text(conversation)
    beverage, signal_score = detect_tasting(text)
    if beverage is None:
        return {"detected": False, "beverage_type": None, "signal_score": signal_score}

    data = _load_user(uid)
    candidate = {
        "id": uuid.uuid4().hex[:8],
        "uid": uid,
        "beverage_type": beverage,
        "signal_score": signal_score,
        "score_100": parse_score(text),
        "verdict": infer_verdict(text),
        "name": None,
        "excerpt": text[:500],
        "conversation_id": getattr(conversation, "id", None),
        "occurred_at": (
            conversation.created_at.isoformat()
            if getattr(conversation, "created_at", None) is not None
            and not isinstance(getattr(conversation, "created_at", None), str)
            else getattr(conversation, "created_at", None)
        ) or _now_iso(),
        "created_at": _now_iso(),
    }
    data["candidates"].append(candidate)
    _save_user(uid, data)
    return {
        "detected": True,
        "beverage_type": beverage,
        "signal_score": signal_score,
        "candidate_id": candidate["id"],
        "score_100": candidate["score_100"],
        "verdict": candidate["verdict"],
        "needs_review": True,
    }


# ---------------------------------------------------------------------------
# Manifest, health, root
# ---------------------------------------------------------------------------

@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> dict[str, Any]:
    uid_schema = {"type": "string", "description": "Omi user id (appended automatically)."}
    beverage_schema = {
        "type": "string",
        "enum": list(BEVERAGE_TYPES),
        "description": "Beverage type being tasted.",
    }
    optional_str = lambda desc: {"type": "string", "description": desc}  # noqa: E731
    return {
        "schema_version": "1.0",
        "name": "Tasting Notes",
        "description": (
            "Log structured tasting notes for wine, coffee, whiskey, and beer. "
            "Stay in the moment — Omi captures the conversation, this app structures it "
            "into review cards with scores and buy/skip verdicts."
        ),
        "tools": [
            {
                "name": "log_tasting",
                "description": (
                    "Record a structured tasting: beverage, name, producer, vintage, "
                    "region, varietal, nose/palate/finish notes, 0-100 score, and "
                    "buy/skip/cellar verdict."
                ),
                "endpoint": "/tools/log_tasting",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uid": uid_schema,
                        "beverage_type": beverage_schema,
                        "name": optional_str("Name of the wine/coffee/whiskey, e.g. 'Barolo Riserva'."),
                        "producer": optional_str("Producer, winery, roaster, or distillery."),
                        "vintage": optional_str("Vintage year for wine."),
                        "region": optional_str("Region of origin, e.g. 'Piedmont, Italy'."),
                        "varietal": optional_str("Grape varietal, coffee varietal, or mash bill."),
                        "nose": optional_str("Aroma notes."),
                        "palate": optional_str("Taste notes."),
                        "finish": optional_str("Finish notes."),
                        "score_100": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Score on a 100-point scale.",
                        },
                        "verdict": {
                            "type": "string",
                            "enum": list(VERDICTS),
                            "description": "buy, skip, or cellar.",
                        },
                        "notes": optional_str("Any freeform notes."),
                    },
                    "required": ["uid"],
                },
            },
            {
                "name": "list_tastings",
                "description": "List recent tastings, newest first, optionally filtered by beverage type.",
                "endpoint": "/tools/list_tastings",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uid": uid_schema,
                        "beverage_type": beverage_schema,
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    },
                    "required": ["uid"],
                },
            },
            {
                "name": "list_candidates",
                "description": (
                    "List ambient-detected tasting candidates awaiting review, "
                    "newest first. Confirm one with confirm_candidate."
                ),
                "endpoint": "/tools/list_candidates",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uid": uid_schema,
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    },
                    "required": ["uid"],
                },
            },
            {
                "name": "get_tasting",
                "description": "Fetch one tasting by id with full structured details.",
                "endpoint": "/tools/get_tasting",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uid": uid_schema,
                        "tasting_id": {"type": "string", "description": "Tasting id from list_tastings."},
                    },
                    "required": ["uid", "tasting_id"],
                },
            },
            {
                "name": "tasting_stats",
                "description": "Aggregate tasting stats: counts, average scores, buy-rate per beverage.",
                "endpoint": "/tools/tasting_stats",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {"uid": uid_schema},
                    "required": ["uid"],
                },
            },
            {
                "name": "confirm_candidate",
                "description": (
                    "Confirm an ambient-detected tasting candidate (listed by "
                    "list_candidates), applying optional corrections to name, "
                    "producer, notes, score, or verdict."
                ),
                "endpoint": "/tools/confirm_candidate",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uid": uid_schema,
                        "candidate_id": {"type": "string", "description": "Candidate id from list_candidates."},
                        "name": optional_str("Corrected name."),
                        "producer": optional_str("Corrected producer."),
                        "vintage": optional_str("Corrected vintage."),
                        "region": optional_str("Corrected region."),
                        "varietal": optional_str("Corrected varietal."),
                        "nose": optional_str("Corrected nose notes."),
                        "palate": optional_str("Corrected palate notes."),
                        "finish": optional_str("Corrected finish notes."),
                        "score_100": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Corrected 100-point score.",
                        },
                        "verdict": {
                            "type": "string",
                            "enum": list(VERDICTS),
                            "description": "Corrected verdict.",
                        },
                        "notes": optional_str("Corrected freeform notes."),
                    },
                    "required": ["uid", "candidate_id"],
                },
            },
        ],
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi Tasting Notes Integration</title></head>
      <body>
        <h1>Omi Tasting Notes Integration</h1>
        <p>Structured tasting cards for wine, coffee, whiskey, and beer — captured
        ambiently from Omi conversations or logged explicitly via chat.</p>
        <p><a href="/.well-known/omi-tools.json">Tool manifest</a></p>
      </body>
    </html>
    """
