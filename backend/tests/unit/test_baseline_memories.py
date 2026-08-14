"""
Behavioral tests for Feature #4631 — Persistent Baseline Memories.

Baseline memories are user-flagged memories that are always injected first into the AI
context window, regardless of total memory count.

Tests exercise:
  - MemoryDB model instantiation and serialization (no external deps)
  - get_prompt_data() bucket routing (legacy path, DB stubbed via import_isolation)
  - get_prompt_memories() prompt-string formatting (legacy path, DB stubbed)

No Firebase, Redis, stripe, anthropic, or network connections are required.
Heavy transitive deps (database.memories → stripe, utils.memory.memory_service → anthropic)
are blocked at import time using the project's sanctioned stub_modules + load_module_fresh
isolation primitives from testing/import_isolation.py.
"""

import pytest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_memory(
    content: str,
    *,
    is_baseline: bool = False,
    manually_added: bool = False,
    is_locked: bool = False,
) -> dict:
    """Return a minimal raw memory dict compatible with MemoryDB.model_validate."""
    return {
        'id': 'mem-test-1',
        'uid': 'user-test-1',
        'content': content,
        'category': 'interesting',
        'created_at': '2024-01-01T00:00:00+00:00',
        'updated_at': '2024-01-01T00:00:00+00:00',
        'visibility': 'private',
        'reviewed': False,
        'user_review': None,
        'manually_added': manually_added,
        'edited': False,
        'deleted': False,
        'is_locked': is_locked,
        'is_baseline': is_baseline,
    }


# ---------------------------------------------------------------------------
# Session fixture: load utils.llms.memory with heavy deps stubbed
# ---------------------------------------------------------------------------


@pytest.fixture(scope='session')
def mem_module():
    """Load utils.llms.memory fresh with the heavy database chain stubbed out.

    Import chain that pulls in heavy packages (stripe, anthropic, …):
      database.memories → database.helpers → database.users → utils.subscription → stripe
      utils.memory.memory_service → database.vector_db → utils.llm.clients → anthropic

    We stub exactly those two top-level modules.  All other imports
    (models.memories, utils.memory.memory_system, database._client) are loaded
    for real since google-cloud-firestore is available in this environment.
    The loaded module is returned as-is; tests patch individual attributes with
    patch.object() inside each test, which auto-restores after the with block.
    """
    from testing.import_isolation import AutoMockModule, stub_modules, load_module_fresh

    stubs = {
        'database.memories': AutoMockModule('database.memories'),
        'database.auth': AutoMockModule('database.auth'),
        'utils.memory.memory_service': AutoMockModule('utils.memory.memory_service'),
    }
    with stub_modules(stubs):
        mod = load_module_fresh('utils.llms.memory', 'utils/llms/memory.py')
    # mod's top-level names were bound against the stubs at load time; they
    # remain valid as module attributes even after stub_modules restores sys.modules.
    return mod


# ---------------------------------------------------------------------------
# Model behavioral tests — MemoryDB.is_baseline field
# ---------------------------------------------------------------------------


class TestBaselineMemoryModel:
    def test_is_baseline_defaults_to_false(self):
        """MemoryDB must default is_baseline to False so existing memories are unaffected."""
        from models.memories import MemoryDB

        memory = MemoryDB.model_validate(_raw_memory('Some fact'))
        assert memory.is_baseline is False

    def test_is_baseline_can_be_set_true(self):
        """MemoryDB.is_baseline must accept True when explicitly provided."""
        from models.memories import MemoryDB

        memory = MemoryDB.model_validate(_raw_memory('Pinned fact', is_baseline=True))
        assert memory.is_baseline is True

    def test_is_baseline_present_in_dict_output(self):
        """is_baseline must be included in model_dump() output."""
        from models.memories import MemoryDB

        memory = MemoryDB.model_validate(_raw_memory('Pinned fact', is_baseline=True))
        d = memory.model_dump()
        assert 'is_baseline' in d, "is_baseline must appear in model_dump() output"
        assert d['is_baseline'] is True

    def test_is_baseline_survives_dict_roundtrip(self):
        """is_baseline=True must survive a dict → MemoryDB → dict roundtrip."""
        from models.memories import MemoryDB

        original = MemoryDB.model_validate(_raw_memory('Pinned fact', is_baseline=True))
        restored = MemoryDB.model_validate(original.model_dump())
        assert restored.is_baseline is True

    def test_is_baseline_false_survives_roundtrip(self):
        """is_baseline=False must also survive a roundtrip without flipping."""
        from models.memories import MemoryDB

        original = MemoryDB.model_validate(_raw_memory('Normal fact'))
        restored = MemoryDB.model_validate(original.model_dump())
        assert restored.is_baseline is False


# ---------------------------------------------------------------------------
# Prompt injection behavioral tests
# ---------------------------------------------------------------------------


class TestBaselineMemoryInjection:
    """
    Each test patches exactly the three callables that get_prompt_data uses at runtime:
      - resolve_memory_system  → forced to MemorySystem.LEGACY so the legacy read path runs
      - memories_db.get_memories  → returns our controlled list of raw memory dicts
      - get_user_name  → returns 'Alice'

    mem_module is a session-scoped fixture that loaded utils.llms.memory against
    AutoMockModule stubs for database.memories and utils.memory.memory_service.
    After loading, the module attributes are bound to those stub objects, so
    patch.object(mem_module, …) and patch.object(mem_module.memories_db, …) are correct.
    """

    def test_baseline_memory_lands_in_first_bucket(self, mem_module):
        """get_prompt_data must route is_baseline=True memories into the baseline bucket."""
        from utils.memory.memory_system import MemorySystem

        raw = [
            _raw_memory('Always remember this', is_baseline=True),
            _raw_memory('A regular fact'),
        ]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, baseline, user_made, generated = mem_module.get_prompt_data('user-1')

        assert len(baseline) == 1, f"Expected 1 baseline memory, got {len(baseline)}"
        assert baseline[0].content == 'Always remember this'
        assert len(generated) == 1
        assert generated[0].content == 'A regular fact'
        assert len(user_made) == 0

    def test_manually_added_memory_lands_in_user_bucket(self, mem_module):
        """get_prompt_data must route manually_added=True memories into the user_made bucket."""
        from utils.memory.memory_system import MemorySystem

        raw = [_raw_memory('User told the AI this', manually_added=True)]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, baseline, user_made, generated = mem_module.get_prompt_data('user-1')

        assert len(user_made) == 1
        assert len(baseline) == 0
        assert len(generated) == 0

    def test_generated_memory_lands_in_generated_bucket(self, mem_module):
        """get_prompt_data must route ordinary auto-extracted memories into the generated bucket."""
        from utils.memory.memory_system import MemorySystem

        raw = [_raw_memory('Auto-extracted fact')]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, baseline, user_made, generated = mem_module.get_prompt_data('user-1')

        assert len(generated) == 1
        assert len(baseline) == 0
        assert len(user_made) == 0

    def test_prompt_string_contains_baseline_label(self, mem_module):
        """get_prompt_memories must include a distinct baseline label when baselines exist."""
        from utils.memory.memory_system import MemorySystem

        raw = [_raw_memory('Core fact about user', is_baseline=True)]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, memories_str = mem_module.get_prompt_memories('user-1')

        has_label = 'baseline' in memories_str.lower() or 'always in context' in memories_str.lower()
        assert has_label, f"Expected a baseline label in prompt, got: {memories_str!r}"
        assert 'Core fact about user' in memories_str

    def test_prompt_string_omits_baseline_section_when_none_exist(self, mem_module):
        """get_prompt_memories must not include a baseline section when there are no baselines."""
        from utils.memory.memory_system import MemorySystem

        raw = [_raw_memory('A regular fact')]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, memories_str = mem_module.get_prompt_memories('user-1')

        assert (
            'baseline' not in memories_str.lower()
        ), "Prompt must not include a baseline section when no baseline memories exist"
        assert 'A regular fact' in memories_str

    def test_locked_memories_excluded_from_all_buckets(self, mem_module):
        """get_prompt_data must skip memories with is_locked=True in all buckets."""
        from utils.memory.memory_system import MemorySystem

        raw = [
            _raw_memory('Locked premium content', is_locked=True),
            _raw_memory('Normal fact'),
        ]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, baseline, user_made, generated = mem_module.get_prompt_data('user-1')

        all_memories = baseline + user_made + generated
        assert len(all_memories) == 1, f"Expected 1 unlocked memory, got {len(all_memories)}"
        assert all_memories[0].content == 'Normal fact'

    def test_baseline_flag_takes_precedence_over_manually_added(self, mem_module):
        """A memory with both is_baseline=True and manually_added=True must land in the baseline bucket."""
        from utils.memory.memory_system import MemorySystem

        raw = [_raw_memory('Pinned user note', is_baseline=True, manually_added=True)]
        with (
            patch.object(mem_module, 'resolve_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(mem_module.memories_db, 'get_memories', return_value=raw),
            patch.object(mem_module, 'get_user_name', return_value='Alice'),
        ):
            _, baseline, user_made, generated = mem_module.get_prompt_data('user-1')

        assert len(baseline) == 1, "is_baseline=True must win over manually_added=True"
        assert len(user_made) == 0
