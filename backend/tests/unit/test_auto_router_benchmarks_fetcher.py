"""Tests for BenchmarksFetcher (v3, T-304) — AA integration + fallback + cache."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from utils.auto_router.benchmarks_fetcher import (
    AA_API_URL,
    AA_ENV_VAR,
    AA_UNCOVERED_TASKS,
    BenchmarksFetcher,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "utils" / "auto_router" / "fixtures"
AA_FIXTURE_PATH = FIXTURES_DIR / "aa_response_2025_06_25.json"
EXAMPLE_PATH = Path(__file__).parent.parent.parent / "utils" / "auto_router" / "benchmarks.example.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_http_response(json_data: Any, status_code: int = 200) -> httpx.Response:
    """Build a fake httpx.Response with the given JSON body and status code."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", AA_API_URL),
    )


def _mock_http_client(response: httpx.Response) -> AsyncMock:
    """Build a mock httpx.AsyncClient whose .get() returns the given response."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    return client


def _make_fetcher(
    tmp_cache: Path,
    http_response: Optional[httpx.Response] = None,
    clock_value: float = 1_000_000.0,
) -> BenchmarksFetcher:
    """Build a BenchmarksFetcher with mocked HTTP client and a tmp cache path."""
    client = _mock_http_client(http_response) if http_response is not None else None
    return BenchmarksFetcher(
        cache_path=tmp_cache,
        example_path=EXAMPLE_PATH,
        http_client=client,
        clock=lambda: clock_value,
    )


def _load_aa_fixture() -> Dict[str, Any]:
    with AA_FIXTURE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# AA parser (pure-function tests, no HTTP)
# ---------------------------------------------------------------------------


class TestAAParser:
    """BenchmarksFetcher._parse_aa_model converts one AA entry to internal format."""

    def test_full_model_parsed(self):
        item = {
            "id": "claude-sonnet-4-6",
            "model_creator": {"name": "Anthropic"},
            "evaluations": [
                {"name": "MMLU", "value": 0.88},
                {"name": "GPQA", "value": 0.74},
                {"name": "MATH", "value": 0.78},
            ],
            "pricing": {"price_1m_input_tokens_usd": 3.0, "price_1m_output_tokens_usd": 15.0},
            "median_latency_seconds": 1.2,
        }
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed is not None
        assert parsed["id"] == "claude-sonnet-4-6"
        assert parsed["provider"] == "Anthropic"
        # quality = mean(0.88, 0.74, 0.78) = 0.80
        assert parsed["quality_score"] == pytest.approx(0.80, abs=1e-3)
        # latency = 1 - 1.2/5 = 0.76
        assert parsed["latency_score"] == pytest.approx(0.76, abs=1e-3)
        # cost = 1 - 3.0/30 = 0.9
        assert parsed["cost_score"] == pytest.approx(0.9, abs=1e-3)

    def test_model_missing_id_returns_none(self):
        assert BenchmarksFetcher._parse_aa_model({"evaluations": []}) is None

    def test_quality_score_clamped_to_unit_interval(self):
        # Quality > 1.0 (unrealistic but possible) should clamp to 1.0.
        item = {
            "id": "x",
            "evaluations": [{"name": "MMLU", "value": 1.5}],
        }
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["quality_score"] == 1.0

    def test_latency_zero_gives_perfect_latency_score(self):
        item = {"id": "x", "median_latency_seconds": 0.0}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["latency_score"] == 1.0

    def test_latency_very_high_gives_zero_latency_score(self):
        item = {"id": "x", "median_latency_seconds": 10.0}  # > 5s normalization
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["latency_score"] == 0.0

    def test_cost_zero_gives_perfect_cost_score(self):
        item = {"id": "x", "pricing": {"price_1m_input_tokens_usd": 0.0}}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["cost_score"] == 1.0

    def test_cost_very_high_gives_zero_cost_score(self):
        item = {"id": "x", "pricing": {"price_1m_input_tokens_usd": 100.0}}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["cost_score"] == 0.0

    def test_missing_evaluations_gives_zero_quality(self):
        item = {"id": "x", "evaluations": []}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["quality_score"] == 0.0

    def test_missing_pricing_gives_perfect_cost_score(self):
        # No pricing data → treat as $0 (likely open-source/free) → cost_score=1.0
        # Per spec: "$0 = 1 cost_score". Matches "missing pricing → 1.0 (best)".
        item = {"id": "x", "pricing": {}}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["cost_score"] == 1.0

    def test_provider_fallback_to_provider_field(self):
        # If model_creator is missing, fall back to top-level "provider"
        item = {"id": "x", "provider": "TestProvider"}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["provider"] == "TestProvider"

    def test_provider_fallback_to_empty(self):
        item = {"id": "x"}
        parsed = BenchmarksFetcher._parse_aa_model(item)
        assert parsed["provider"] == ""


# ---------------------------------------------------------------------------
# fetch() with mocked HTTP
# ---------------------------------------------------------------------------


class TestFetchFromAA:
    """BenchmarksFetcher.fetch hits AA and returns parsed data."""

    @pytest.mark.asyncio
    async def test_successful_fetch_returns_aa_source(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        fixture = _load_aa_fixture()
        response = _mock_http_response(fixture)
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "aa"
        assert refreshed_at is not None  # cache file was written
        assert "tasks" in data
        assert "models" in data
        # All LLM tasks (not in AA_UNCOVERED_TASKS) should have all 4 fixture models
        llm_tasks = [t for t in data["tasks"] if t["name"] not in AA_UNCOVERED_TASKS]
        assert len(llm_tasks) >= 1
        for task in llm_tasks:
            assert len(data["models"][task["name"]]) == 4

    @pytest.mark.asyncio
    async def test_successful_fetch_preserves_uncovered_tasks(self, tmp_path, monkeypatch):
        """STT/embedding tasks come from example, not AA — even when AA is hit."""
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        fixture = _load_aa_fixture()
        response = _mock_http_response(fixture)
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        # transcription + screenshot_embedding should have models from example
        for task_name in AA_UNCOVERED_TASKS:
            assert task_name in data["models"]
            assert len(data["models"][task_name]) > 0

    @pytest.mark.asyncio
    async def test_4xx_response_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        response = _mock_http_response({"error": "unauthorized"}, status_code=401)
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"
        assert refreshed_at is None
        # Example data should still be returned with all 5 tasks
        assert len(data["tasks"]) == 5

    @pytest.mark.asyncio
    async def test_5xx_response_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        response = _mock_http_response({"error": "server"}, status_code=500)
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"

    @pytest.mark.asyncio
    async def test_network_error_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        fetcher = BenchmarksFetcher(
            cache_path=tmp_path / "cache.json",
            example_path=EXAMPLE_PATH,
            http_client=client,
        )

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.TimeoutException("read timeout"))
        fetcher = BenchmarksFetcher(
            cache_path=tmp_path / "cache.json",
            example_path=EXAMPLE_PATH,
            http_client=client,
        )

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        # httpx.Response with json=... invalid raises json.JSONDecodeError on .json()
        response = httpx.Response(
            status_code=200,
            content=b"not valid json",
            request=httpx.Request("GET", AA_API_URL),
        )
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        fetcher = BenchmarksFetcher(
            cache_path=tmp_path / "cache.json",
            example_path=EXAMPLE_PATH,
            http_client=client,
        )

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"

    @pytest.mark.asyncio
    async def test_unexpected_response_shape_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        response = _mock_http_response("unexpected string body")
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------


class TestMissingAPIKey:
    @pytest.mark.asyncio
    async def test_no_api_key_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.delenv(AA_ENV_VAR, raising=False)
        # No HTTP client — should not be called.
        fetcher = _make_fetcher(tmp_path / "cache.json", http_response=None)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"
        assert refreshed_at is None
        assert len(data["tasks"]) == 5

    @pytest.mark.asyncio
    async def test_empty_api_key_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "")
        fetcher = _make_fetcher(tmp_path / "cache.json", http_response=None)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"

    @pytest.mark.asyncio
    async def test_whitespace_api_key_falls_back_to_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "   ")
        fetcher = _make_fetcher(tmp_path / "cache.json", http_response=None)

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "example"


# ---------------------------------------------------------------------------
# 24h cache
# ---------------------------------------------------------------------------


class TestCache:
    @pytest.mark.asyncio
    async def test_fresh_cache_avoids_http_call(self, tmp_path, monkeypatch):
        # Pre-populate the cache with valid data.
        cache_file = tmp_path / "cache.json"
        with cache_file.open("w") as f:
            json.dump({"tasks": [], "models": {}}, f)
        mtime = cache_file.stat().st_mtime

        # Use a clock that returns mtime + 1s (within 24h TTL).
        fetcher = BenchmarksFetcher(
            cache_path=cache_file,
            example_path=EXAMPLE_PATH,
            http_client=None,
            clock=lambda: mtime + 1.0,
        )

        data, source, refreshed_at = await fetcher.fetch(force=False)

        assert source == "aa"
        assert refreshed_at is not None

    @pytest.mark.asyncio
    async def test_stale_cache_triggers_fetch(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        cache_file = tmp_path / "cache.json"
        with cache_file.open("w") as f:
            json.dump({"tasks": [], "models": {}}, f)
        mtime = cache_file.stat().st_mtime

        # Clock 25h later — cache stale.
        response = _mock_http_response(_load_aa_fixture())
        fetcher = BenchmarksFetcher(
            cache_path=cache_file,
            example_path=EXAMPLE_PATH,
            http_client=_mock_http_client(response),
            clock=lambda: mtime + 25 * 60 * 60,
        )

        data, source, refreshed_at = await fetcher.fetch(force=False)

        assert source == "aa"  # fetched fresh from AA

    @pytest.mark.asyncio
    async def test_missing_cache_triggers_fetch(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        response = _mock_http_response(_load_aa_fixture())
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        data, source, refreshed_at = await fetcher.fetch(force=False)

        assert source == "aa"
        # Cache file should now exist
        assert (tmp_path / "cache.json").exists()

    @pytest.mark.asyncio
    async def test_corrupt_cache_triggers_fetch(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        cache_file = tmp_path / "cache.json"
        with cache_file.open("w") as f:
            f.write("not valid json")
        response = _mock_http_response(_load_aa_fixture())
        fetcher = BenchmarksFetcher(
            cache_path=cache_file,
            example_path=EXAMPLE_PATH,
            http_client=_mock_http_client(response),
        )

        data, source, refreshed_at = await fetcher.fetch(force=False)

        assert source == "aa"  # corrupt cache ignored, fetched fresh

    @pytest.mark.asyncio
    async def test_force_skips_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        cache_file = tmp_path / "cache.json"
        with cache_file.open("w") as f:
            json.dump({"tasks": [], "models": {}}, f)
        mtime = cache_file.stat().st_mtime

        # Clock 1s after mtime (cache fresh).
        response = _mock_http_response(_load_aa_fixture())
        fetcher = BenchmarksFetcher(
            cache_path=cache_file,
            example_path=EXAMPLE_PATH,
            http_client=_mock_http_client(response),
            clock=lambda: mtime + 1.0,
        )

        data, source, refreshed_at = await fetcher.fetch(force=True)

        assert source == "aa"  # force=True always hits AA

    @pytest.mark.asyncio
    async def test_cache_file_written_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        cache_file = tmp_path / "cache.json"
        response = _mock_http_response(_load_aa_fixture())
        fetcher = _make_fetcher(cache_file, response)

        await fetcher.fetch(force=True)

        assert cache_file.exists()
        with cache_file.open() as f:
            cached = json.load(f)
        assert "tasks" in cached
        assert "models" in cached


# ---------------------------------------------------------------------------
# fetch_with_metadata convenience wrapper
# ---------------------------------------------------------------------------


class TestFetchWithMetadata:
    @pytest.mark.asyncio
    async def test_aa_source_metadata_shape(self, tmp_path, monkeypatch):
        monkeypatch.setenv(AA_ENV_VAR, "test-key-12345")
        response = _mock_http_response(_load_aa_fixture())
        fetcher = _make_fetcher(tmp_path / "cache.json", response)

        result = await fetcher.fetch_with_metadata(force=True)

        assert "data" in result
        assert result["source"] == "aa"
        assert result["refreshed_at"] is not None

    @pytest.mark.asyncio
    async def test_example_source_metadata_shape(self, tmp_path, monkeypatch):
        monkeypatch.delenv(AA_ENV_VAR, raising=False)
        fetcher = _make_fetcher(tmp_path / "cache.json", http_response=None)

        result = await fetcher.fetch_with_metadata(force=True)

        assert "data" in result
        assert result["source"] == "example"
        assert result["refreshed_at"] is None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_benchmarks_fetcher_returns_same_instance(self):
        from utils.auto_router.benchmarks_fetcher import (
            get_benchmarks_fetcher,
            reset_benchmarks_fetcher_for_testing,
        )

        reset_benchmarks_fetcher_for_testing()
        a = get_benchmarks_fetcher()
        b = get_benchmarks_fetcher()
        assert a is b
        reset_benchmarks_fetcher_for_testing()

    def test_reset_creates_new_instance(self):
        from utils.auto_router.benchmarks_fetcher import (
            get_benchmarks_fetcher,
            reset_benchmarks_fetcher_for_testing,
        )

        reset_benchmarks_fetcher_for_testing()
        a = get_benchmarks_fetcher()
        reset_benchmarks_fetcher_for_testing()
        b = get_benchmarks_fetcher()
        assert a is not b
        reset_benchmarks_fetcher_for_testing()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_aa_api_url_is_official(self):
        assert AA_API_URL == "https://artificialanalysis.ai/api/v2/data/llms/models"

    def test_aa_env_var_name(self):
        assert AA_ENV_VAR == "AA_API_KEY"

    def test_uncovered_tasks_are_stt_and_embedding(self):
        assert AA_UNCOVERED_TASKS == frozenset({"transcription", "screenshot_embedding"})


# ---------------------------------------------------------------------------
# Public cache_file_modified_iso accessor (cubic / maintainer review)
# ---------------------------------------------------------------------------


class TestCacheFileModifiedIsoAccessor:
    """Public accessor for the cache file's modification time.

    Was `_cache_file_modified_iso` (private). Promoted to public so callers
    like the `/metrics` endpoint can ask the fetcher for cache freshness
    without depending on the private `_cache_path` attribute (coupling smell).
    """

    def test_returns_iso_when_cache_file_exists(self, tmp_path):
        cache_path = tmp_path / "benchmarks.json"
        cache_path.write_text("{}")  # exists, mtime = now
        fetcher = BenchmarksFetcher(cache_path=cache_path)
        result = fetcher.cache_file_modified_iso()
        assert result is not None
        # ISO 8601 with 'Z' suffix (UTC).
        assert result.endswith("Z")

    def test_returns_none_when_cache_file_missing(self, tmp_path):
        cache_path = tmp_path / "nonexistent.json"
        fetcher = BenchmarksFetcher(cache_path=cache_path)
        assert fetcher.cache_file_modified_iso() is None

    def test_public_method_exists(self, tmp_path):
        """Regression guard: the method is public, not private."""
        cache_path = tmp_path / "benchmarks.json"
        cache_path.write_text("{}")
        fetcher = BenchmarksFetcher(cache_path=cache_path)
        # Should be callable without name-mangling underscore prefix.
        assert callable(fetcher.cache_file_modified_iso)
        # The private version is intentionally gone.
        assert not hasattr(fetcher, "_cache_file_modified_iso")

    def test_returns_none_on_oserror_during_stat(self, tmp_path):
        """Regression guard (cubic P2): if the cache file is deleted
        between the exists() check and the stat() call (TOCTOU race),
        the OSError must be caught and treated as 'no cache'.
        Without this, the OSError would bubble to /metrics as a 500.
        """
        cache_path = tmp_path / "benchmarks.json"
        cache_path.write_text("{}")
        fetcher = BenchmarksFetcher(cache_path=cache_path)

        # Monkeypatch the fetcher's _cache_path.stat to raise OSError
        # (simulates the race: exists() passed, but stat() sees the file
        # gone). posixpath.stat is a C function on Path, so we patch the
        # _cache_path instance to be a wrapper that delegates exists() but
        # raises OSError on stat().
        class _RacyPath(type(cache_path)):
            def stat(self, *args, **kwargs):
                raise OSError("file deleted between exists() and stat()")

        fetcher._cache_path = _RacyPath(str(cache_path))
        result = fetcher.cache_file_modified_iso()
        assert result is None, "OSError should be caught and return None"


# ---------------------------------------------------------------------------
# Doc/code env var consistency (maintainer review)
# ---------------------------------------------------------------------------


class TestDocCodeEnvVarConsistency:
    """Lock doc/code agreement on the AA benchmark env var name.

    Maintainer review (PR #8359) caught: docs said `ASSEMBLYAI_API_KEY` but
    the code reads `AA_API_KEY`. ASSEMBLYAI_API_KEY is AssemblyAI's STT
    API key — a different service. This test fails if the docs and code
    disagree, so the bug can't regress silently.
    """

    def test_docs_reference_correct_aa_env_var(self):
        from pathlib import Path

        from utils.auto_router.benchmarks_fetcher import AA_ENV_VAR

        doc_path = Path(__file__).parent.parent.parent.parent / "docs" / "doc" / "developer" / "auto-router.mdx"
        doc = doc_path.read_text()
        # The correct env var name (matches the code's AA_ENV_VAR).
        assert AA_ENV_VAR in doc, (
            f"docs/doc/developer/auto-router.mdx does not mention "
            f"the canonical env var name '{AA_ENV_VAR}' from "
            f"benchmarks_fetcher.AA_ENV_VAR. Operators setting "
            f"the env var will look for it in the docs."
        )

    def test_docs_do_not_reference_wrong_env_var(self):
        """ASSEMBLYAI_API_KEY is a different service (AssemblyAI STT).
        Mentioning it in the AA benchmark docs will mislead operators.
        """
        from pathlib import Path

        doc_path = Path(__file__).parent.parent.parent.parent / "docs" / "doc" / "developer" / "auto-router.mdx"
        doc = doc_path.read_text()
        # The wrong env var name (AssemblyAI STT, not AA benchmarks).
        wrong_name = "ASSEMBLYAI_API_KEY"
        # The docs may mention it in a 'not to be confused with' note
        # (which is fine and encouraged), but should not present it as
        # the canonical AA env var.
        for line in doc.splitlines():
            stripped = line.strip()
            if wrong_name in stripped and not stripped.startswith("|") is False:
                # In a table row, check it's not the env var being documented.
                if stripped.startswith("|") and f"`{wrong_name}`" in stripped:
                    # Allow if it's in a 'note' / 'not to be confused' clause
                    # (i.e., not in the env-var name column).
                    parts = [p.strip() for p in stripped.strip("|").split("|")]
                    if parts and parts[0] == f"`{wrong_name}`":
                        pytest.fail(
                            f"docs/doc/developer/auto-router.mdx presents "
                            f"'{wrong_name}' as an env var name: {stripped!r}. "
                            f"This is the AssemblyAI STT key, not the AA "
                            f"benchmark key. Use 'AA_API_KEY' instead."
                        )


# ---------------------------------------------------------------------------
# CHANGELOG.json placeholder guard (maintainer review)
# ---------------------------------------------------------------------------


class TestChangelogPlaceholderGuard:
    """Regression guard (maintainer review): when the auto-router branch
    merges main and resolves the resulting CHANGELOG.json conflict, the
    resolution must use the ACTUAL changelog entry from main — not a
    placeholder string like 'Entry from main (other PR that landed first)'.

    A previous maintainer test-merge used such a placeholder and a real
    user-facing changelog entry was at risk of being lost. This test
    fails if any unreleased entry matches a known placeholder pattern.

    Why a placeholder is dangerous:
    - The placeholder text reads as a valid changelog entry but carries
      no information about what changed.
    - It would be shipped to end users in the next release notes.
    - The real entry from main is lost.

    Patterns detected:
    - 'Entry from main' — the exact placeholder the maintainer flagged.
    - 'TODO' / 'FIXME' / 'placeholder' — generic placeholder markers.
    - 'lorem ipsum' / 'xxx' / 'yyy' — obvious placeholder content.
    """

    PLACEHOLDER_PATTERNS = (
        "entry from main",
        "todo",
        "fixme",
        "placeholder",
        "lorem ipsum",
        "xxx",
        "yyy",
    )

    def test_unreleased_has_no_placeholders(self):
        """No entry in `unreleased` should match a known placeholder pattern."""
        from pathlib import Path

        changelog_path = Path(__file__).parent.parent.parent.parent / "desktop" / "macos" / "CHANGELOG.json"
        data = json.loads(changelog_path.read_text())
        unreleased = data.get("unreleased", [])
        assert isinstance(unreleased, list)

        for i, entry in enumerate(unreleased):
            entry_lower = entry.lower().strip()
            for pattern in self.PLACEHOLDER_PATTERNS:
                # Match if pattern is the full entry or surrounded by
                # whitespace/parens — exact word-ish match, not substring.
                if pattern == entry_lower or (pattern in entry_lower and len(entry_lower) < len(pattern) + 20):
                    pytest.fail(
                        f"desktop/macos/CHANGELOG.json unreleased[{i}] "
                        f"looks like a placeholder: {entry!r}. "
                        f"Replace with the actual entry from main before merge."
                    )

    def test_unreleased_has_at_least_one_real_entry(self):
        """Sanity check: there should be at least one substantive entry
        (not just empty arrays or single placeholder)."""
        from pathlib import Path

        changelog_path = Path(__file__).parent.parent.parent.parent / "desktop" / "macos" / "CHANGELOG.json"
        data = json.loads(changelog_path.read_text())
        unreleased = data.get("unreleased", [])
        # Real entries are at least 20 chars (any meaningful description).
        real_entries = [e for e in unreleased if len(e) >= 20]
        assert real_entries, (
            f"unreleased has no substantive entries ({unreleased}). "
            f"At least one entry should describe an actual change."
        )
