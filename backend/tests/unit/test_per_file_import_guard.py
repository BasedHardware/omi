"""
Tests for the per-file local-file import guard.

Regression goal: the desktop onboarding scan historically emitted one memory
per indexed file (up to 2800 "The user's local projects include <path>"
entries per scan). Those buried users' real memories and were bulk-purged in
July 2026. `is_per_file_local_import_tags` is the server-side backstop that
keeps clients released before the fix from recreating the spam, while letting
the aggregate local_files facts (profile/project/technology) through.

The backstop must hold in every MEMORY_IMPORT_WRITE_BLOCK_MODE: the import
write guard consumes `import_write_violation_for_guard`, which exempts
per-file items so enforce mode cannot 409 an old desktop build's batch before
the endpoints acknowledge-and-drop those items. Endpoint wiring is asserted
source-level (the memories router import chain needs production env vars —
same pattern as test_memories_create.py).
"""

import os
import re

from utils.memory.import_write_guard import (
    import_write_block_mode,
    import_write_violation,
    import_write_violation_for_guard,
    is_per_file_local_import_tags,
)

ROUTER_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'memories.py')


def _read_router() -> str:
    with open(ROUTER_PATH, encoding='utf-8') as f:
        return f.read()


PER_FILE_PAYLOAD = {
    "content": "The user's local projects include ~/projects/foo/main.py (py).",
    "tags": ["local_files", "onboarding", "projects", "py"],
    "source": "local_files",
    "category": "system",
}
AGGREGATE_IMPORT_PAYLOAD = {
    "content": "The user works on a local project named foo.",
    "tags": ["local_files", "onboarding", "project"],
    "source": "local_files",
    "category": "system",
}


class TestIsPerFileLocalImportTags:
    def test_per_file_folder_variants_are_dropped(self):
        for folder in ("projects", "documents", "downloads"):
            assert is_per_file_local_import_tags(["local_files", "onboarding", folder, "py"]) is True

    def test_recent_file_variant_is_dropped(self):
        assert is_per_file_local_import_tags(["local_files", "onboarding", "recent_file"]) is True

    def test_aggregate_local_file_facts_pass(self):
        for aggregate in ("profile", "project", "technology"):
            assert is_per_file_local_import_tags(["local_files", "onboarding", aggregate]) is False

    def test_requires_both_import_markers(self):
        # "projects" alone (e.g. a conversation memory about the user's
        # projects) must not be treated as a file-import item.
        assert is_per_file_local_import_tags(["projects", "py"]) is False
        assert is_per_file_local_import_tags(["local_files", "projects"]) is False
        assert is_per_file_local_import_tags(["onboarding", "projects"]) is False

    def test_other_import_sources_pass(self):
        assert is_per_file_local_import_tags(["gmail", "onboarding", "profile"]) is False
        assert is_per_file_local_import_tags(["calendar", "onboarding", "profile"]) is False

    def test_normalization_of_case_and_separators(self):
        assert is_per_file_local_import_tags(["Local_Files", "Onboarding", "Recent-File"]) is True
        assert is_per_file_local_import_tags([" local_files ", "onboarding", "Projects", "PY"]) is True

    def test_non_list_and_empty_inputs_pass(self):
        assert is_per_file_local_import_tags(None) is False
        assert is_per_file_local_import_tags("local_files") is False
        assert is_per_file_local_import_tags([]) is False
        assert is_per_file_local_import_tags([None, 42]) is False


class TestGuardExemptionUnderEnforce:
    """Per-file items must never reach the 409 path, in any block mode."""

    def test_per_file_payload_is_exempt_from_guard(self):
        # Would be a violation via source AND tags — but per-file items are
        # acknowledged-and-dropped by the endpoints, never persisted, so the
        # guard must not see them.
        assert import_write_violation(PER_FILE_PAYLOAD) is not None
        assert import_write_violation_for_guard(PER_FILE_PAYLOAD) is None

    def test_aggregate_import_payload_still_hits_guard(self):
        # Non-per-file import writes keep the existing guard semantics
        # (logged today, 409 once enforce mode is enabled).
        assert import_write_violation_for_guard(AGGREGATE_IMPORT_PAYLOAD) == import_write_violation(
            AGGREGATE_IMPORT_PAYLOAD
        )
        assert import_write_violation_for_guard(AGGREGATE_IMPORT_PAYLOAD) is not None

    def test_non_import_payload_unaffected(self):
        payload = {"content": "GUARD-TEST: the user enjoys hiking.", "tags": [], "category": "interesting"}
        assert import_write_violation_for_guard(payload) is None

    def test_enforce_mode_env_is_honored(self, monkeypatch):
        monkeypatch.setenv("MEMORY_IMPORT_WRITE_BLOCK_MODE", "enforce")
        assert import_write_block_mode() == "enforce"
        # Even in enforce mode the guard input for a per-file item is "no
        # violation" — the mode can only 409 what the guard actually flags.
        assert import_write_violation_for_guard(PER_FILE_PAYLOAD) is None


class TestRouterWiring:
    """Source-level assertions on routers/memories.py (its import chain needs
    production env vars, so behavior is pinned the same way as
    test_memories_create.py)."""

    def test_guard_uses_exempting_violation_helper(self):
        src = _read_router()
        guard_body = src.split("async def _guard_import_memory_write", 1)[1].split("\nasync def", 1)[0]
        assert "import_write_violation_for_guard(payload)" in guard_body
        # The unexempted helper must not be called anywhere in the router —
        # otherwise enforce mode could 409 per-file items on some path.
        assert re.search(r"[^_]import_write_violation\(", src) is None

    def test_single_create_acknowledges_and_drops_per_file(self):
        src = _read_router()
        create_body = src.split("async def create_memory(", 1)[1].split("\nasync def", 1)[0]
        drop_idx = create_body.find("is_per_file_local_import_tags(memory.tags)")
        assert drop_idx != -1
        # The drop returns the ghost response before any persistence call.
        persist_idx = create_body.find("create_memory,")
        assert persist_idx == -1 or drop_idx < persist_idx
        assert "_legacy_memory_response(memory_db)" in create_body[drop_idx:]

    def test_batch_filters_per_file_before_building_writes(self):
        src = _read_router()
        batch_body = src.split("async def create_memories_batch(", 1)[1].split("\nasync def", 1)[0]
        filter_idx = batch_body.find("is_per_file_local_import_tags(m.tags)")
        build_idx = batch_body.find("for memory in accepted_memories")
        assert filter_idx != -1 and build_idx != -1 and filter_idx < build_idx
