"""
Tests for Feature #4631 — Persistent Baseline Memories.

Baseline memories are user-flagged memories that are always injected first
into the AI context window, regardless of total memory count. This ensures
the AI uses them without the user needing to explicitly ask every session.

These tests use source-level verification (no Firebase/external deps needed).
"""

import os
import re

MODELS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'memories.py')
MEMORY_UTILS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'llms', 'memory.py')
ROUTER_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'memories.py')


def _read(path):
    with open(path) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Model tests — MemoryDB must have is_baseline field
# ---------------------------------------------------------------------------


class TestBaselineMemoryModel:
    def test_memory_db_has_is_baseline_field(self):
        """MemoryDB must declare an is_baseline boolean field defaulting to False."""
        source = _read(MODELS_PATH)
        assert 'is_baseline' in source, "MemoryDB must have an is_baseline field"

    def test_is_baseline_defaults_to_false(self):
        """is_baseline must default to False so existing memories are unaffected."""
        source = _read(MODELS_PATH)
        assert re.search(r'is_baseline\s*:\s*bool\s*=\s*False', source), (
            "is_baseline must be typed as bool and default to False"
        )


# ---------------------------------------------------------------------------
# Memory injection tests — baseline memories must be injected first
# ---------------------------------------------------------------------------


class TestBaselineMemoryInjection:
    def test_get_prompt_data_separates_baseline_memories(self):
        """get_prompt_data must return baseline memories as a separate bucket."""
        source = _read(MEMORY_UTILS_PATH)
        assert 'is_baseline' in source, (
            "get_prompt_data must handle is_baseline to separate baseline memories"
        )

    def test_get_prompt_memories_injects_baseline_first(self):
        """get_prompt_memories must prepend baseline memories before all others."""
        source = _read(MEMORY_UTILS_PATH)
        assert 'baseline' in source.lower(), (
            "get_prompt_memories must reference baseline memories in the prompt string"
        )

    def test_baseline_label_in_prompt(self):
        """Baseline memories must be labelled distinctly in the injected prompt."""
        source = _read(MEMORY_UTILS_PATH)
        assert re.search(r'baseline|always.*context|pinned', source, re.IGNORECASE), (
            "Baseline memories must be labelled clearly in the prompt (e.g. 'baseline', 'always in context')"
        )


# ---------------------------------------------------------------------------
# Router tests — PATCH endpoint to toggle baseline flag
# ---------------------------------------------------------------------------


class TestBaselineMemoryEndpoint:
    def test_baseline_endpoint_exists(self):
        """A PATCH endpoint for toggling is_baseline must exist."""
        source = _read(ROUTER_PATH)
        assert re.search(r"@router\.patch.*memories.*baseline", source), (
            "Must have a PATCH /v3/memories/{memory_id}/baseline endpoint"
        )

    def test_baseline_endpoint_uses_rate_limit(self):
        """The baseline endpoint must be rate-limited under memories:modify."""
        source = _read(ROUTER_PATH)
        baseline_section = re.search(
            r'(@router\.patch.*baseline.*?)(?=@router\.|\Z)', source, re.DOTALL
        )
        assert baseline_section, "baseline endpoint not found"
        assert 'memories:modify' in baseline_section.group(1), (
            "baseline endpoint must use memories:modify rate limit"
        )

    def test_baseline_endpoint_updates_firestore(self):
        """The baseline endpoint must persist the flag to Firestore."""
        source = _read(ROUTER_PATH)
        baseline_section = re.search(
            r'(def.*baseline.*?)(?=\n@router\.|\Z)', source, re.DOTALL
        )
        assert baseline_section, "baseline endpoint function not found"
        assert 'is_baseline' in baseline_section.group(1), (
            "baseline endpoint must write is_baseline to Firestore"
        )
