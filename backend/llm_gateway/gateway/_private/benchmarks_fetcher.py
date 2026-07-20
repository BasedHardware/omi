"""Fetch live LLM benchmarks from Artificial Analysis (https://artificialanalysis.ai).

v3 replaces the static `benchmarks.example.json` mock with live data from
`https://artificialanalysis.ai/api/v2/data/llms/models` for LLM tasks.
STT / embedding tasks are NOT covered by AA, so the example data is
preserved for those tasks (union merge).

Behavior:

  1. If `AA_API_KEY` env var is missing → fall back to `benchmarks.example.json`
     (logs WARNING at startup so operators know they're on mock data).
  2. If `AA_API_KEY` is set, call the AA API.
     - On 2xx: parse, cache in `benchmarks.json` (gitignored, 24h TTL).
     - On 4xx/5xx: fall back to `benchmarks.example.json`, log WARNING.
     - On network error / timeout (>15s): fall back, log WARNING.
  3. STT / embedding tasks (`transcription`, `screenshot_embedding`) are NOT
     in the AA response — preserve them from `benchmarks.example.json`
     regardless of source.

Score normalization (AA → internal format):

    quality_score  = mean of `evaluations[].value` (all in [0, 1])
    latency_score  = 1.0 - clamp(median_latency_seconds / 5.0, 0, 1)
                     (0s → 1.0, 5s+ → 0.0)
    cost_score     = 1.0 - clamp(price_1m_input_tokens_usd / 30.0, 0, 1)
                     ($0 → 1.0, $30+ → 0.0)

The mapping is documented here so future readers understand why AA's
raw fields produce the [0, 1] scores the scoring engine expects.

Uses `utils.http_client.get_web_fetch_client()` (shared httpx pool, 15s
read timeout, 5s connect) — matches the backend AGENTS.md async rules.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from utils.http_client import get_web_fetch_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AA_API_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
AA_ENV_VAR = "AA_API_KEY"
CACHE_FILE_ENV_VAR = "AA_CACHE_PATH"  # override for tests

# Defaults if AA returns no model at all (shouldn't happen, but defensive)
COST_NORMALIZATION_USD_PER_1M = 30.0
LATENCY_NORMALIZATION_SECONDS = 5.0

# Tasks that AA does NOT cover. Their candidates come from benchmarks.example.json
# (or the cached file if it contains them) regardless of AA's response.
AA_UNCOVERED_TASKS = frozenset({"transcription", "screenshot_embedding"})


# ---------------------------------------------------------------------------
# Module-level singleton + reset (matches the pattern of UserPrefsStore)
# ---------------------------------------------------------------------------

_benchmarks_fetcher: Optional["BenchmarksFetcher"] = None
_benchmarks_fetcher_lock = asyncio.Lock()


def get_benchmarks_fetcher() -> "BenchmarksFetcher":
    """Return the process-wide BenchmarksFetcher (lazy-initialized)."""
    global _benchmarks_fetcher
    if _benchmarks_fetcher is None:
        _benchmarks_fetcher = BenchmarksFetcher()
    return _benchmarks_fetcher


def reset_benchmarks_fetcher_for_testing() -> None:
    """Drop the singleton. Test helper."""
    global _benchmarks_fetcher
    _benchmarks_fetcher = None


# ---------------------------------------------------------------------------
# BenchmarksFetcher
# ---------------------------------------------------------------------------


class BenchmarksFetcher:
    """Fetch and cache LLM benchmarks from Artificial Analysis.

    Returns a dict in the same shape as `benchmarks.example.json`:
        {
            "tasks": [{"name": str, "quality_weight": float, ...}, ...],
            "models": {"<task_name>": [{"id": str, ...}, ...], ...}
        }

    The `source` field ("aa" | "example") and `refreshed_at` (ISO 8601)
    are exposed via `fetch_with_metadata()` for observability.
    """

    DEFAULT_CACHE_PATH = "benchmarks.json"
    DEFAULT_EXAMPLE_PATH = "benchmarks.example.json"
    CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h, matches daily_refresh.py

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        example_path: Optional[Path] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        clock: Any = None,
    ):
        """Construct a BenchmarksFetcher.

        All args are injectable for testing:
          cache_path: where to cache successful AA responses (default: gitignored benchmarks.json)
          example_path: fallback file (default: benchmarks.example.json)
          http_client: httpx client (default: shared web_fetch_client)
          clock: time function (default: time.time); for cache TTL checks

        Default paths are resolved relative to this module's directory
        (so they work regardless of cwd), not the process cwd.
        """
        import pathlib

        module_dir = pathlib.Path(__file__).resolve().parent
        env_cache = os.environ.get(CACHE_FILE_ENV_VAR)
        self._cache_path = pathlib.Path(cache_path or env_cache or (module_dir / self.DEFAULT_CACHE_PATH))
        self._example_path = pathlib.Path(example_path or (module_dir / self.DEFAULT_EXAMPLE_PATH))
        self._http_client = http_client  # None = use shared pool (production)
        self._clock = clock or time.time

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    async def fetch(self, force: bool = False) -> Tuple[Dict[str, Any], str, Optional[str]]:
        """Fetch benchmarks, returning (data, source, refreshed_at).

        Args:
            force: skip the 24h cache and always call AA (used by admin refresh)

        Returns:
            data: benchmarks dict (tasks + models)
            source: "aa" if from Artificial Analysis, "example" if from fallback
            refreshed_at: ISO 8601 timestamp of when the source was last refreshed
                (None if no benchmarks.json exists yet — fallback-only mode)

        Flow:
            1. Check cache (if not force). If fresh, return cached data.
            2. If AA_API_KEY is missing → load example, return (example, "example", None)
            3. Call AA API. On success → save to cache, return (parsed, "aa", now)
            4. On any error → load example, return (example, "example", None)
        """
        # 1. Check cache.
        if not force:
            cached = self._read_cache_if_fresh()
            if cached is not None:
                return cached, "aa", self._cache_file_modified_iso()

        # 2-4. Try AA, fall back to example.
        api_key = os.environ.get(AA_ENV_VAR, "").strip()
        if not api_key:
            logger.warning(
                "BenchmarksFetcher: %s env var not set, falling back to benchmarks.example.json. "
                "Set %s to enable live data.",
                AA_ENV_VAR,
                AA_ENV_VAR,
            )
            return self._load_example(), "example", None

        try:
            aa_data = await self._fetch_from_aa(api_key)
        except Exception as e:
            logger.warning(
                "BenchmarksFetcher: AA fetch failed (%s: %s), falling back to benchmarks.example.json",
                type(e).__name__,
                e,
            )
            return self._load_example(), "example", None

        # Merge with example for AA-uncovered tasks (STT, embedding).
        merged = self._merge_with_uncovered_tasks(aa_data, self._load_example())

        # Cache the merged result for next time.
        self._write_cache(merged)
        return merged, "aa", self._cache_file_modified_iso()

    async def fetch_with_metadata(self, force: bool = False) -> Dict[str, Any]:
        """Convenience: fetch + wrap the result with source/refreshed_at metadata.

        Returns a dict shaped like:
            {
                "data": {tasks, models},    # same as benchmarks.example.json
                "source": "aa" | "example",
                "refreshed_at": "2026-06-25T10:00:00Z" | None
            }
        """
        data, source, refreshed_at = await self.fetch(force=force)
        return {"data": data, "source": source, "refreshed_at": refreshed_at}

    # ---------------------------------------------------------------------------
    # AA API
    # ---------------------------------------------------------------------------

    async def _fetch_from_aa(self, api_key: str) -> Dict[str, Any]:
        """Call the AA API and parse into {tasks, models} format.

        Raises on any error (network, 4xx/5xx, malformed JSON). Caller handles fallback.
        """
        client = self._http_client or get_web_fetch_client()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        response = await client.get(AA_API_URL, headers=headers)
        response.raise_for_status()
        raw = response.json()

        # Parse AA's response shape. We accept either:
        #   {"data": [...]} (AA's actual format per their public docs)
        #   [...]                       (some endpoints wrap differently)
        items: List[Dict[str, Any]]
        if isinstance(raw, dict) and "data" in raw:
            items = raw["data"]
        elif isinstance(raw, list):
            items = raw
        else:
            raise ValueError(f"AA response has unexpected shape: {type(raw).__name__}")

        # Group models by task. AA doesn't have per-task metadata — all models
        # in the response are LLM candidates. We map them to the LLM tasks
        # (everything in benchmarks.example.json EXCEPT AA_UNCOVERED_TASKS).
        example = self._load_example()
        llm_tasks = [t["name"] for t in example["tasks"] if t["name"] not in AA_UNCOVERED_TASKS]

        models_by_task: Dict[str, List[Dict[str, Any]]] = {name: [] for name in llm_tasks}
        for item in items:
            parsed = self._parse_aa_model(item)
            if parsed is None:
                continue
            for task_name in llm_tasks:
                models_by_task[task_name].append(dict(parsed))

        return {"tasks": example["tasks"], "models": models_by_task}

    @staticmethod
    def _parse_aa_model(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse one AA model entry into the internal {id, provider, *_score} format.

        Returns None if the entry is missing required fields (e.g., no name).
        """
        model_id = item.get("id") or item.get("name") or item.get("slug")
        if not model_id or not isinstance(model_id, str):
            return None

        creator = item.get("model_creator") or {}
        provider = ""
        if isinstance(creator, dict):
            provider = creator.get("name", "") or creator.get("id", "")
        if not provider:
            provider = item.get("provider", "") or ""

        # Quality score: mean of evaluations[].value (all in [0, 1]).
        evaluations = item.get("evaluations") or []
        quality_values = [
            float(e["value"])
            for e in evaluations
            if isinstance(e, dict) and "value" in e and isinstance(e["value"], (int, float))
        ]
        quality_score = sum(quality_values) / len(quality_values) if quality_values else 0.0
        quality_score = max(0.0, min(1.0, quality_score))

        # Latency score: 1 - clamp(latency_seconds / 5s, 0, 1).
        latency_seconds = item.get("median_latency_seconds") or item.get("median_latency") or 0.0
        try:
            latency_seconds = float(latency_seconds)
        except (TypeError, ValueError):
            latency_seconds = 0.0
        latency_score = max(0.0, min(1.0, 1.0 - (latency_seconds / LATENCY_NORMALIZATION_SECONDS)))

        # Cost score: 1 - clamp(price_per_1m_input / $30, 0, 1).
        pricing = item.get("pricing") or {}
        price_per_1m = pricing.get("price_1m_input_tokens_usd") or pricing.get("price_1m_input") or 0.0
        try:
            price_per_1m = float(price_per_1m)
        except (TypeError, ValueError):
            price_per_1m = 0.0
        cost_score = max(0.0, min(1.0, 1.0 - (price_per_1m / COST_NORMALIZATION_USD_PER_1M)))

        return {
            "id": model_id,
            "provider": provider,
            "quality_score": quality_score,
            "latency_score": latency_score,
            "cost_score": cost_score,
        }

    # ---------------------------------------------------------------------------
    # Merging: AA + example (for STT/embedding)
    # ---------------------------------------------------------------------------

    def _merge_with_uncovered_tasks(self, aa_data: Dict[str, Any], example_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge AA-derived LLM candidates with example-derived STT/embedding candidates.

        AA covers LLMs (ptt_response, screenshot_understanding, general_assistant).
        The example covers all 5 task types. We use AA for LLMs and example for
        STT/embedding — gives us live data where possible, mocked data where not.
        """
        merged_models: Dict[str, List[Dict[str, Any]]] = dict(aa_data.get("models", {}))
        for task_name in AA_UNCOVERED_TASKS:
            example_models = example_data.get("models", {}).get(task_name, [])
            if example_models:
                merged_models[task_name] = example_models
        return {"tasks": aa_data.get("tasks", example_data["tasks"]), "models": merged_models}

    # ---------------------------------------------------------------------------
    # Cache
    # ---------------------------------------------------------------------------

    def _read_cache_if_fresh(self) -> Optional[Dict[str, Any]]:
        """Return cached data if it exists and is within TTL, else None."""
        if not self._cache_path.exists():
            return None
        age = self._clock() - self._cache_path.stat().st_mtime
        if age >= self.CACHE_TTL_SECONDS:
            return None
        try:
            with self._cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("BenchmarksFetcher: cache file corrupt (%s), ignoring", e)
            return None

    def _write_cache(self, data: Dict[str, Any]) -> None:
        """Write data to the cache file. Best-effort (failure logged, not raised)."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.warning("BenchmarksFetcher: cache write failed (%s)", e)

    def _cache_file_modified_iso(self) -> Optional[str]:
        """ISO 8601 timestamp of the cache file's last modification, or None if missing."""
        if not self._cache_path.exists():
            return None
        mtime = self._cache_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    # ---------------------------------------------------------------------------
    # Example data (fallback)
    # ---------------------------------------------------------------------------

    def _load_example(self) -> Dict[str, Any]:
        """Load the committed benchmarks.example.json (mock data)."""
        with self._example_path.open("r", encoding="utf-8") as f:
            return json.load(f)
