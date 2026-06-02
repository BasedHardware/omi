import logging
import os
import time

import httpx
from fastapi import APIRouter

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

_cache = {"provider": None, "ts": 0.0, "detail": {}}


def _score(quality, speed):
    q = min(max(quality, 0.0), 100.0) / 100.0
    s = min(max(speed, 0.0), SPEED_CAP) / SPEED_CAP
    return QUALITY_WEIGHT * q + SPEED_WEIGHT * s


async def _fetch_and_score():
    key = os.getenv("ARTIFICIALANALYSIS_API_KEY")
    if not key:
        return "geminiFlashLive", {"reason": "no ARTIFICIALANALYSIS_API_KEY; default to Gemini"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(AA_URL, headers={"x-api-key": key})
        resp.raise_for_status()
        models = resp.json().get("data", [])

    def best_score(substr):
        best = None
        for m in models:
            slug = (m.get("slug") or m.get("id") or m.get("name") or "").lower()
            if substr not in slug:
                continue
            evals = m.get("evaluations") or {}
            quality = evals.get("artificial_analysis_intelligence_index")
            speed = m.get("median_output_tokens_per_second")
            if quality is None or speed is None:
                continue
            sc = _score(quality, speed)
            if best is None or sc > best:
                best = sc
        return best

    scores = {p: best_score(sub) for p, sub in PROXY.items()}
    scores = {p: round(s, 4) for p, s in scores.items() if s is not None}
    if not scores:
        return "geminiFlashLive", {"reason": "no matching AA models", "scores": {}}
    pick = max(scores, key=scores.get)
    return pick, {"scores": scores}


@router.get("/v1/auto/model-pick")
async def auto_model_pick():
    """Current best realtime-voice provider for 'Auto' users (daily-cached)."""
    now = time.time()
    if _cache["provider"] is None or (now - _cache["ts"]) > TTL_SECONDS:
        try:
            provider, detail = await _fetch_and_score()
            _cache.update(provider=provider, ts=now, detail=detail)
        except Exception as e:
            logger.error(f"auto model-pick fetch failed: {e}")
            if _cache["provider"] is None:
                _cache.update(provider="geminiFlashLive", ts=now, detail={"reason": f"error: {e}"})
    return {
        "provider": _cache["provider"],
        "updated_at": _cache["ts"],
        "detail": _cache["detail"],
        "attribution": "https://artificialanalysis.ai/",
    }
