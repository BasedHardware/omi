import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException

from models.auto_model import AutoModelPick
from utils.log_sanitizer import sanitize
from utils.other.endpoints import get_current_user_uid

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

_cache: Dict[str, Any] = {"provider": None, "ts": 0.0, "detail": {}}
_cache_lock = asyncio.Lock()


def _reset_cache() -> None:
    """Testing helper to clear cached model pick."""
    global _cache_lock
    _cache.update(provider=None, ts=0.0, detail={})
    _cache_lock = asyncio.Lock()


def _score(quality: Any, speed: Any) -> Optional[float]:
    try:
        q_val = float(quality)
        s_val = float(speed)
    except (ValueError, TypeError):
        return None
    q = min(max(q_val, 0.0), 100.0) / 100.0
    s = min(max(s_val, 0.0), SPEED_CAP) / SPEED_CAP
    return QUALITY_WEIGHT * q + SPEED_WEIGHT * s


async def _fetch_and_score() -> Tuple[str, Dict[str, Any]]:
    key = os.getenv("ARTIFICIALANALYSIS_API_KEY")
    if not key:
        return "geminiFlashLive", {"reason": "no ARTIFICIALANALYSIS_API_KEY; default to Gemini"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(AA_URL, headers={"x-api-key": key})
        resp.raise_for_status()
        data = resp.json()
        models = data.get("data", []) if isinstance(data, dict) else []

    def best_score(substr: str) -> Optional[float]:
        best: Optional[float] = None
        for m in models:
            if not isinstance(m, dict):
                continue
            slug = m.get("slug") or m.get("id") or m.get("name") or ""
            if not isinstance(slug, str) or substr not in slug.lower():
                continue
            evals = m.get("evaluations")
            if not isinstance(evals, dict):
                continue
            quality = evals.get("artificial_analysis_intelligence_index")
            speed = m.get("median_output_tokens_per_second")
            if quality is None or speed is None:
                continue
            sc = _score(quality, speed)
            if sc is not None and (best is None or sc > best):
                best = sc
        return best

    scores = {p: best_score(sub) for p, sub in PROXY.items()}
    valid_scores = {p: round(s, 4) for p, s in scores.items() if s is not None}
    if not valid_scores:
        return "geminiFlashLive", {"reason": "no matching AA models", "scores": {}}
    pick = max(valid_scores, key=valid_scores.get)
    return pick, {"scores": valid_scores}


@router.get("/v1/auto/model-pick", response_model=AutoModelPick)
async def auto_model_pick(uid: str = Depends(get_current_user_uid)):
    """Current best realtime-voice provider for 'Auto' users (daily-cached)."""
    if not uid or not str(uid).strip():
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = time.time()
    if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
        # Serialize concurrent refreshes so a cache miss fires only one AA fetch.
        async with _cache_lock:
            now = time.time()  # re-check after acquiring the lock
            if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
                try:
                    provider, detail = await _fetch_and_score()
                    _cache.update(provider=provider, ts=now, detail=detail)
                except Exception as e:
                    logger.error("auto model-pick fetch failed: %s", sanitize(str(e)), exc_info=True)
                    if _cache["provider"] is None:
                        _cache.update(
                            provider="geminiFlashLive",
                            ts=now,
                            detail={"reason": "model scoring fetch failed; default to Gemini"},
                        )
    return {
        "provider": _cache["provider"],
        "updated_at": _cache["ts"],
        "detail": _cache["detail"],
        "attribution": "https://artificialanalysis.ai/",
    }
