import asyncio
import logging
import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException

from models.auto_model import AutoModelPick
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)

# "Auto" realtime-voice model selection.
#
# Picks the realtime provider whose underlying model scores best on a simple
# quality/speed formula, refreshed once a day from Artificial Analysis
# (https://artificialanalysis.ai — attribution required). Done server-side so the
# AA key never ships in the client and the response is cached (per AA's terms).
# All desktop clients on "Auto" read the same pick from /v1/auto/model-pick.

# Desktop provider id -> AA model slug substring used as the quality/speed proxy
# (the realtime audio variants aren't in AA's LLM index, so we use the closest
# representative model).
PROXY = {
    "geminiFlashLive": "gemini-3-5-flash",
    "gptRealtime2": "gpt-5",
}
QUALITY_WEIGHT = 0.65
SPEED_WEIGHT = 0.35
SPEED_CAP = 250.0  # tokens/sec, for normalization
TTL_SECONDS = 24 * 3600
AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"

# Client-safe fallback texts. These are the ONLY strings from this module that a
# caller may see in `detail["reason"]`. Upstream exception text can carry internal
# hostnames, upstream URLs (httpx.HTTPStatusError embeds the request URL), or
# status payloads, so it must never be reflected to a client.
_FALLBACK_REASON = "model scoring fetch failed; default to Gemini"
_FALLBACK_NO_MODELS = "no matching AA models"
_FALLBACK_NO_KEY = "no ARTIFICIALANALYSIS_API_KEY; default to Gemini"

_cache = {"provider": None, "ts": 0.0, "detail": {}}
_cache_lock = asyncio.Lock()


def _score(quality, speed):
    q = min(max(quality, 0.0), 100.0) / 100.0
    s = min(max(speed, 0.0), SPEED_CAP) / SPEED_CAP
    return QUALITY_WEIGHT * q + SPEED_WEIGHT * s


def _as_float(value):
    """Coerce an upstream metric to float, or return None if it is not numeric.

    The scoring API is third-party; a string, bool, list or dict in a metric
    field must not raise a TypeError deep inside the scoring loop and take the
    whole refresh down.
    """
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _best_score(models, substr):
    best = None
    for m in models:
        if not isinstance(m, dict):
            continue
        slug = (m.get("slug") or m.get("id") or m.get("name") or "").lower()
        if not isinstance(slug, str) or substr not in slug:
            continue
        evals = m.get("evaluations")
        if not isinstance(evals, dict):
            evals = {}
        quality = _as_float(evals.get("artificial_analysis_intelligence_index"))
        speed = _as_float(m.get("median_output_tokens_per_second"))
        if quality is None or speed is None:
            continue
        sc = _score(quality, speed)
        if best is None or sc > best:
            best = sc
    return best


async def _fetch_and_score():
    key = os.getenv("ARTIFICIALANALYSIS_API_KEY")
    if not key:
        return "geminiFlashLive", {"reason": _FALLBACK_NO_KEY}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(AA_URL, headers={"x-api-key": key})
        resp.raise_for_status()
        payload = resp.json()

    # A malformed body (not an object, or "data" not a list) must degrade to the
    # default pick rather than raise.
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return "geminiFlashLive", {"reason": _FALLBACK_NO_MODELS, "scores": {}}

    scores = {}
    for provider, sub in PROXY.items():
        sc = _best_score(models, sub)
        if sc is not None:
            scores[provider] = round(sc, 4)
    if not scores:
        return "geminiFlashLive", {"reason": _FALLBACK_NO_MODELS, "scores": {}}
    pick = max(scores, key=scores.get)
    return pick, {"scores": scores}


async def _refresh_cache():
    """Fetch, score and update the cache. Never raises.

    Any upstream failure is absorbed here and turned into the last-resort default
    pick with a client-safe reason. The raw exception text is logged through
    `sanitize` so tokens or credentials appearing in a third-party trace are
    masked before they reach the log.
    """
    now = time.time()
    try:
        provider, detail = await _fetch_and_score()
        _cache.update(provider=provider, ts=now, detail=detail)
    except Exception as e:  # noqa: BLE001 — the endpoint must never 500 on upstream failure
        logger.error("auto model-pick fetch failed: %s", sanitize(str(e)))
        if _cache["provider"] is None:
            _cache.update(provider="geminiFlashLive", ts=now, detail={"reason": _FALLBACK_REASON})


@router.get("/v1/auto/model-pick", response_model=AutoModelPick)
async def auto_model_pick(uid: str = Depends(auth.get_current_user_uid)):
    """Current best realtime-voice provider for 'Auto' users (daily-cached)."""
    # The auth dependency normally supplies a non-empty uid, but it is optional at
    # the type level and a caller may reach this handler with a blank subject.
    if not uid or not str(uid).strip():
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = time.time()
    if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
        # Serialize concurrent refreshes so a cache miss fires only one AA fetch.
        async with _cache_lock:
            now = time.time()  # re-check after acquiring the lock
            if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
                await _refresh_cache()
    return {
        "provider": _cache["provider"],
        "updated_at": _cache["ts"],
        "detail": _cache["detail"],
        "attribution": "https://artificialanalysis.ai/",
    }
