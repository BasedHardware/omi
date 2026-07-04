import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

import httpx
from fastapi import APIRouter, Depends

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
PROXY: Dict[str, str] = {
    "geminiFlashLive": "gemini-3-5-flash",
    "gptRealtime2": "gpt-5",
}
QUALITY_WEIGHT = 0.65
SPEED_WEIGHT = 0.35
SPEED_CAP = 250.0  # tokens/sec, for normalization
TTL_SECONDS = 24 * 3600
AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"


class _CacheEntry(TypedDict):
    provider: Optional[str]
    ts: float
    detail: Dict[str, Any]


_cache: _CacheEntry = {"provider": None, "ts": 0.0, "detail": {}}
_cache_lock = asyncio.Lock()


def _score(quality: float, speed: float) -> float:
    q = min(max(quality, 0.0), 100.0) / 100.0
    s = min(max(speed, 0.0), SPEED_CAP) / SPEED_CAP
    return QUALITY_WEIGHT * q + SPEED_WEIGHT * s


async def _fetch_and_score() -> Tuple[str, Dict[str, Any]]:
    key = os.getenv("ARTIFICIALANALYSIS_API_KEY")
    if not key:
        return "geminiFlashLive", {"reason": "no ARTIFICIALANALYSIS_API_KEY; default to Gemini"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(AA_URL, headers={"x-api-key": key})
        resp.raise_for_status()
        loaded: object = resp.json()
        data: Dict[str, Any] = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}
        models_raw: object = data.get("data", [])
        models: List[Dict[str, Any]] = cast(List[Dict[str, Any]], models_raw) if isinstance(models_raw, list) else []

    def best_score(substr: str) -> Optional[float]:
        best: Optional[float] = None
        for m in models:
            slug = (m.get("slug") or m.get("id") or m.get("name") or "").lower()
            if substr not in slug:
                continue
            evals_raw: object = m.get("evaluations") or {}
            evals: Dict[str, Any] = cast(Dict[str, Any], evals_raw) if isinstance(evals_raw, dict) else {}
            quality_raw: object = evals.get("artificial_analysis_intelligence_index")
            speed_raw: object = m.get("median_output_tokens_per_second")
            if quality_raw is None or speed_raw is None:
                continue
            quality = cast(float, quality_raw)
            speed = cast(float, speed_raw)
            sc = _score(quality, speed)
            if best is None or sc > best:
                best = sc
        return best

    scores_raw: Dict[str, Optional[float]] = {p: best_score(sub) for p, sub in PROXY.items()}
    scores: Dict[str, float] = {p: round(s, 4) for p, s in scores_raw.items() if s is not None}
    if not scores:
        return "geminiFlashLive", {"reason": "no matching AA models", "scores": {}}
    pick = max(scores, key=lambda k: scores[k])
    return pick, {"scores": scores}


@router.get("/v1/auto/model-pick")
async def auto_model_pick(uid: str = Depends(get_current_user_uid)) -> Dict[str, Any]:
    """Current best realtime-voice provider for 'Auto' users (daily-cached)."""
    now = time.time()
    if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
        # Serialize concurrent refreshes so a cache miss fires only one AA fetch.
        async with _cache_lock:
            now = time.time()  # re-check after acquiring the lock
            if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
                try:
                    provider, detail = await _fetch_and_score()
                    _cache["provider"] = provider
                    _cache["ts"] = now
                    _cache["detail"] = detail
                except Exception as e:
                    logger.error(f"auto model-pick fetch failed: {e}")
                    if _cache["provider"] is None:
                        _cache["provider"] = "geminiFlashLive"
                        _cache["ts"] = now
                        _cache["detail"] = {"reason": f"error: {e}"}
    return {
        "provider": _cache["provider"],
        "updated_at": _cache["ts"],
        "detail": _cache["detail"],
        "attribution": "https://artificialanalysis.ai/",
    }
