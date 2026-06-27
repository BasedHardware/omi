import asyncio
import hmac
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from database import model_routes as model_routes_db
from utils.llm import model_config
from utils.llm.auto_router import (
    ARTIFICIAL_ANALYSIS_URL,
    AUTO_ROUTER_ATTRIBUTION,
    AUTO_ROUTER_TTL_SECONDS,
    build_auto_route_table,
)
from utils.other.endpoints import get_current_user_uid

router = APIRouter()
logger = logging.getLogger(__name__)

# "Auto" realtime-voice model selection.
#
# Picks the realtime provider whose underlying model scores best on a simple
# quality/speed formula, refreshed once a day from Artificial Analysis
# (https://artificialanalysis.ai - attribution required). Done server-side so the
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
AA_URL = ARTIFICIAL_ANALYSIS_URL

_cache = {"provider": None, "ts": 0.0, "detail": {}}
_cache_lock = asyncio.Lock()

_route_cache: Dict[str, Any] = {"payload": None, "ts": 0.0}
_route_cache_lock = asyncio.Lock()
_route_refresh_task: Optional[asyncio.Task] = None


def _load_persisted_route_table(profile: str) -> Optional[Dict[str, Any]]:
    return model_routes_db.get_active_model_routes(profile)


model_config.set_dynamic_route_loader(_load_persisted_route_table)


def _score(quality, speed):
    q = min(max(quality, 0.0), 100.0) / 100.0
    s = min(max(speed, 0.0), SPEED_CAP) / SPEED_CAP
    return QUALITY_WEIGHT * q + SPEED_WEIGHT * s


async def _fetch_artificial_analysis_payload() -> Dict[str, Any]:
    key = os.getenv("ARTIFICIALANALYSIS_API_KEY")
    if not key:
        raise RuntimeError("ARTIFICIALANALYSIS_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(AA_URL, headers={"x-api-key": key})
        resp.raise_for_status()
        return resp.json()


async def _fetch_and_score():
    if not os.getenv("ARTIFICIALANALYSIS_API_KEY"):
        return "geminiFlashLive", {"reason": "no ARTIFICIALANALYSIS_API_KEY; default to Gemini"}

    payload = await _fetch_artificial_analysis_payload()
    models = payload.get("data", [])

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


def _verify_admin_key(x_admin_key: str = Header(..., alias='X-Admin-Key')) -> str:
    expected = os.getenv('MODEL_AUTO_ROUTER_ADMIN_KEY') or os.getenv('ADMIN_KEY', '')
    if not expected or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=403, detail='Invalid admin key')
    return 'admin'


def _is_table_current(route_table: Optional[Dict[str, Any]]) -> bool:
    if not route_table:
        return False
    expires_at = route_table.get("expires_at")
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > datetime.now(timezone.utc)


async def refresh_model_routes(force: bool = False, persist: bool = True) -> Dict[str, Any]:
    """Refresh or load the backend LLM auto-router table."""

    profile = model_config.get_active_profile_name()
    now = time.time()
    cached = _route_cache.get("payload")
    if not force and cached and _is_table_current(cached) and now - _route_cache["ts"] < AUTO_ROUTER_TTL_SECONDS:
        return cached

    async with _route_cache_lock:
        now = time.time()
        cached = _route_cache.get("payload")
        if not force and cached and _is_table_current(cached) and now - _route_cache["ts"] < AUTO_ROUTER_TTL_SECONDS:
            return cached

        if not force:
            persisted = _load_persisted_route_table(profile)
            if _is_table_current(persisted):
                model_config.set_dynamic_model_routes(persisted)
                _route_cache.update(payload=persisted, ts=now)
                return persisted

        benchmark_payload = None
        disabled_reason = None
        try:
            benchmark_payload = await _fetch_artificial_analysis_payload()
        except Exception as e:
            disabled_reason = f"benchmark_fetch_failed:{type(e).__name__}"
            logger.warning("model auto-router benchmark fetch failed: %s", e)

        route_table = build_auto_route_table(
            profile_name=profile,
            static_profile=model_config.get_active_profile(),
            benchmark_payload=benchmark_payload,
            structured_output_features=model_config._STRUCTURED_OUTPUT_FEATURES,
            anthropic_only_features=model_config._ANTHROPIC_ONLY_FEATURES,
            perplexity_only_features=model_config._PERPLEXITY_ONLY_FEATURES,
            pinned_features=model_config._PINNED_FEATURES,
            disabled_reason=disabled_reason,
        )

        model_config.set_dynamic_model_routes(route_table)
        _route_cache.update(payload=route_table, ts=now)

        if persist and benchmark_payload is not None:
            model_routes_db.set_active_model_routes(profile, route_table)
            model_routes_db.record_model_route_run(profile, route_table)

        return route_table


async def _model_route_refresh_loop() -> None:
    startup_delay = float(os.getenv("MODEL_AUTO_ROUTER_STARTUP_DELAY_SECONDS", "5"))
    await asyncio.sleep(max(startup_delay, 0.0))
    while True:
        try:
            await refresh_model_routes(force=False, persist=True)
        except Exception as e:
            logger.warning("model auto-router refresh loop failed: %s", e)
        await asyncio.sleep(AUTO_ROUTER_TTL_SECONDS)


def start_model_auto_router() -> None:
    global _route_refresh_task
    if not model_config.is_auto_router_enabled():
        return
    if _route_refresh_task is None or _route_refresh_task.done():
        _route_refresh_task = asyncio.create_task(_model_route_refresh_loop())


async def stop_model_auto_router() -> None:
    global _route_refresh_task
    if _route_refresh_task is None:
        return
    _route_refresh_task.cancel()
    try:
        await _route_refresh_task
    except asyncio.CancelledError:
        pass
    _route_refresh_task = None


@router.get("/v1/auto/model-pick")
async def auto_model_pick(uid: str = Depends(get_current_user_uid)):
    """Current best realtime-voice provider for 'Auto' users (daily-cached)."""
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
                    logger.error(f"auto model-pick fetch failed: {e}")
                    if _cache["provider"] is None:
                        _cache.update(provider="geminiFlashLive", ts=now, detail={"reason": f"error: {e}"})
    return {
        "provider": _cache["provider"],
        "updated_at": _cache["ts"],
        "detail": _cache["detail"],
        "attribution": AUTO_ROUTER_ATTRIBUTION,
    }


@router.get("/v1/auto/model-routes")
async def auto_model_routes(uid: str = Depends(get_current_user_uid)):
    """Current backend LLM feature route table, refreshed from cache when needed."""
    return await refresh_model_routes(force=False, persist=True)


@router.post("/v1/admin/auto/model-routes/refresh", tags=["admin"])
async def refresh_auto_model_routes(
    force: bool = Query(default=True),
    admin_id: str = Depends(_verify_admin_key),
):
    """Force-refresh the backend LLM route table from Artificial Analysis."""
    return await refresh_model_routes(force=force, persist=True)
