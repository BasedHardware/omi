"""INV-MEM-5 static ratchets for universal memory and task authority."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

TASK_AUTHORITY_FILES = (
    "routers/canonical_task_access.py",
    "database/candidates.py",
    "database/goals.py",
    "database/workstreams.py",
    "database/task_recommendations.py",
    "database/chat_first_intents.py",
    "database/recurrence_inbox.py",
    "utils/task_intelligence/rollout.py",
    "utils/task_intelligence/conversation_capture.py",
    "utils/task_intelligence/workstream_association.py",
    "utils/task_intelligence/workstream_index.py",
)

MEMORY_SURFACE_FILES = (
    "routers/memories.py",
    "routers/developer.py",
    "routers/integration.py",
    "routers/conversations.py",
    "routers/mcp.py",
    "routers/mcp_sse.py",
    "utils/conversations/memories.py",
    "utils/conversations/merge_conversations.py",
    "utils/conversations/process_conversation.py",
    "utils/retrieval/tool_services/memories.py",
    "utils/retrieval/tools/memory_tools.py",
    "utils/retrieval/tools/preference_tools.py",
    "utils/x_connector.py",
)


def test_uid_memory_entitlement_module_is_deleted():
    assert not (BACKEND / "config/canonical_memory_cohort.py").exists()


def test_task_authority_does_not_import_memory_enrollment_or_system_selection():
    forbidden = (
        "canonical_memory_cohort",
        "is_canonical_memory_user",
        "resolve_memory_system",
        "pin_memory_system",
        "CANONICAL_MEMORY_USERS",
    )
    for relative in TASK_AUTHORITY_FILES:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        assert not any(marker in source for marker in forbidden), relative


def test_released_memory_surfaces_have_one_service_authority():
    forbidden = (
        "resolve_memory_system(",
        "pin_memory_system(",
        "canonical_read_enabled(",
        "canonical_write_decision(",
        "memories_db.create_memory(",
        "memories_db.save_memories(",
        "memories_db.edit_memory(",
        "memories_db.review_memory(",
        "memories_db.change_memory_visibility(",
        "memories_db.invalidate_memory(",
    )
    for relative in MEMORY_SURFACE_FILES:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        assert "MemoryService" in source, relative
        assert not any(marker in source for marker in forbidden), relative


def test_canonical_apply_boundary_owns_global_intake_fence():
    source = (BACKEND / "database/memory_apply_store.py").read_text(encoding="utf-8")
    assert "def _require_canonical_intake_enabled()" in source
    assert "MemoryRolloutMode.write" in source
    assert "MemoryRolloutMode.read" in source
    assert source.count("_require_canonical_intake_enabled()") >= 3


def test_runtime_contract_rejects_retired_uid_inventory():
    source = (BACKEND / "scripts/runtime_env_memory_contract.py").read_text(encoding="utf-8")
    assert "MEMORY_ENABLED_USERS" in source
    assert "retired" in source.lower() or "forbidden" in source.lower()
