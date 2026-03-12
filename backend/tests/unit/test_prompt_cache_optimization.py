"""
Tests for prompt cache optimization (#4676).

Verifies:
1. llm_agent clients have prompt_cache_key configured
2. System prompt static prefix is stable across different users
3. CORE_TOOLS constant is fixed and not accidentally mutated
"""

import os
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# --- Stub database package and submodules ---
database_mod = _stub_module("database")
if not hasattr(database_mod, '__path__'):
    database_mod.__path__ = []
for submodule in [
    "redis_db",
    "memories",
    "conversations",
    "users",
    "tasks",
    "trends",
    "action_items",
    "folders",
    "calendar_meetings",
    "vector_db",
    "apps",
    "llm_usage",
    "_client",
    "chat",
    "goals",
    "knowledge_graph",
    "daily_summaries",
    "mem_db",
    "notifications",
    "auth",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

sys.modules["database.llm_usage"].record_llm_usage = MagicMock()
sys.modules["database.notifications"].get_mentor_notification_frequency = MagicMock(return_value=3)
sys.modules["database.notifications"].get_user_time_zone = MagicMock(return_value="America/Los_Angeles")
sys.modules["database.auth"].get_user_name = MagicMock(return_value="TestUser")
sys.modules["database.goals"].get_user_goal = MagicMock(return_value=None)
sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[])
sys.modules["database.redis_db"].get_enabled_apps = MagicMock(return_value=[])
sys.modules["database.redis_db"].get_filter_category_items = MagicMock(return_value=[])
sys.modules["database.redis_db"].add_filter_category_item = MagicMock()

# Stub LLM clients
mock_llm = MagicMock()
mock_llm.invoke = MagicMock(return_value=MagicMock(content="test"))

clients_mod = _stub_module("utils.llm.clients")
clients_mod.llm_mini = mock_llm
clients_mod.llm_mini_stream = mock_llm
clients_mod.llm_medium = mock_llm
clients_mod.llm_medium_stream = mock_llm
clients_mod.llm_medium_experiment = mock_llm
clients_mod.llm_agent = mock_llm
clients_mod.llm_agent_stream = mock_llm

llm_mod = _stub_module("utils.llm")
if not hasattr(llm_mod, '__path__'):
    llm_mod.__path__ = []
tracker_mod = _stub_module("utils.llm.usage_tracker")
tracker_mod.get_usage_callback = MagicMock(return_value=[])
tracker_mod.set_usage_context = MagicMock()
tracker_mod.reset_usage_context = MagicMock()
tracker_mod.Features = MagicMock()
tracker_mod.track_usage = MagicMock()

# Stub other modules needed by chat.py
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, '__path__'):
    llms_mod.__path__ = []
llms_memory_mod = _stub_module("utils.llms.memory")
llms_memory_mod.get_prompt_memories = MagicMock(return_value=("TestUser", "Some facts about user"))

obs_mod = _stub_module("utils.observability")
if not hasattr(obs_mod, '__path__'):
    obs_mod.__path__ = []
langsmith_mod = _stub_module("utils.observability.langsmith")
langsmith_mod.get_chat_tracer_callbacks = MagicMock(return_value=[])
langsmith_prompts_mod = _stub_module("utils.observability.langsmith_prompts")
langsmith_prompts_mod.get_agentic_system_prompt_template = MagicMock(side_effect=Exception("not available"))
langsmith_prompts_mod.render_prompt = MagicMock()
langsmith_prompts_mod.get_prompt_metadata = MagicMock(return_value=(None, None, None))


# ── Source-level tests ──


def _read_clients_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "llm" / "clients.py").read_text()


def _read_agentic_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "retrieval" / "agentic.py").read_text()


def _read_chat_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "llm" / "chat.py").read_text()


def test_llm_agent_has_prompt_cache_key():
    """llm_agent and llm_agent_stream should have prompt_cache_key configured."""
    source = _read_clients_source()
    assert "prompt_cache_key" in source, "clients.py should configure prompt_cache_key for agent models"
    assert "omi-agent-v1" in source, "prompt_cache_key should be 'omi-agent-v1'"


def test_llm_agent_uses_extra_body_for_cache_retention():
    """prompt_cache_retention must use extra_body (not model_kwargs) — SDK rejects it as a direct kwarg."""
    source = _read_clients_source()
    assert 'extra_body={"prompt_cache_retention"' in source, "prompt_cache_retention should be set via extra_body"
    # model_kwargs must NOT contain prompt_cache_retention (SDK rejects it there)
    mk_blocks = re.findall(r'model_kwargs\s*=\s*\{[^}]*\}', source)
    for block in mk_blocks:
        assert "prompt_cache_retention" not in block, f"prompt_cache_retention must not be in model_kwargs: {block}"


def test_core_tools_constant_exists():
    """CORE_TOOLS constant should be defined in agentic.py."""
    source = _read_agentic_source()
    assert "CORE_TOOLS = [" in source, "agentic.py should define CORE_TOOLS constant"


def test_core_tools_used_in_both_functions():
    """Both execute_agentic_chat and execute_agentic_chat_stream should use CORE_TOOLS."""
    source = _read_agentic_source()
    assert (
        source.count("list(CORE_TOOLS)") >= 2
    ), "Both execute functions should use list(CORE_TOOLS) instead of inline tool lists"


def test_no_duplicate_inline_tool_lists():
    """There should be no duplicate hardcoded tool lists in agentic.py."""
    source = _read_agentic_source()
    # After fix, `tools = [` with inline tool names should NOT appear — only CORE_TOOLS = [
    # Count occurrences of the module-level constant pattern vs inline assignment pattern
    assert source.count("CORE_TOOLS = [") == 1, "CORE_TOOLS should be defined exactly once"
    # There should be no `tools = [` followed by tool names (old inline pattern)
    inline_lists = re.findall(r"tools\s*=\s*\[\s*\n\s*get_conversations_tool", source)
    assert len(inline_lists) == 0, f"Found {len(inline_lists)} inline tool list assignments — should use CORE_TOOLS"


def test_system_prompt_static_prefix_is_stable():
    """The system prompt should start with static content (no user-specific data)."""
    source = _read_chat_source()

    # Find the fallback prompt start
    idx = source.find('base_prompt = f"""')
    assert idx != -1, "Should find fallback prompt definition"

    # Extract first 200 chars of the prompt content
    prompt_start = source[idx : idx + 300]

    # The first section should be <response_style> (static), not <assistant_role> (dynamic)
    assert (
        "<response_style>" in prompt_start
    ), "System prompt should start with static <response_style> section, not dynamic content"
    assert (
        "{user_name}" not in prompt_start
    ), "System prompt prefix should not contain {user_name} — dynamic content must be at the end"


def test_assistant_role_comes_after_static_sections():
    """<assistant_role> (dynamic, contains user_name) should come after static sections in the fallback prompt."""
    source = _read_chat_source()
    # Scope to the fallback prompt only (starts at base_prompt = f""")
    fallback_start = source.find('base_prompt = f"""')
    assert fallback_start != -1, "Should find fallback prompt definition"
    fallback = source[fallback_start:]
    idx_response_style = fallback.find("<response_style>")
    idx_assistant_role = fallback.find("<assistant_role>")
    assert idx_response_style != -1 and idx_assistant_role != -1
    assert (
        idx_response_style < idx_assistant_role
    ), "<response_style> (static) should come before <assistant_role> (dynamic) in the fallback prompt"


def test_static_prefix_has_no_dynamic_refs():
    """All static sections in the fallback prompt prefix should not contain dynamic template variables."""
    source = _read_chat_source()

    # Scope to fallback prompt only
    fallback_start = source.find('base_prompt = f"""')
    assert fallback_start != -1, "Should find fallback prompt definition"
    fallback = source[fallback_start:]

    # Extract the static prefix: from <response_style> to just before <assistant_role>
    start = fallback.find("<response_style>")
    end = fallback.find("<assistant_role>")
    assert start != -1 and end != -1 and start < end

    static_prefix = fallback[start:end]

    # These dynamic refs should NOT appear in the static prefix
    assert "{user_name}" not in static_prefix, "Static prefix should not contain {user_name}"
    assert "{tz}" not in static_prefix, "Static prefix should not contain {tz}"
    assert "{current_datetime" not in static_prefix, "Static prefix should not contain {current_datetime}"
    assert "{goal_section}" not in static_prefix, "Static prefix should not contain {goal_section}"
