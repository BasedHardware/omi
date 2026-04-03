"""
Integration tests for prompt cache optimization (#4676).

Unlike the source-level tests in test_prompt_cache_optimization.py, these tests
actually import and call the real production functions to verify:

1. _get_agentic_qa_prompt() produces byte-identical static prefixes for different users
2. CORE_TOOLS is the right length/type and list() creates independent copies
3. llm_agent clients carry the correct model_kwargs at runtime
4. Tool list construction: core tools first, app tools appended after
5. Static prefix exceeds OpenAI's 1,024-token minimum for cache eligibility
6. Dynamic sections actually vary per user (otherwise the split is pointless)
"""

import os
import sys
import types
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Module stubbing (same pattern as other unit tests)
# ---------------------------------------------------------------------------


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# --- database stubs ---
database_mod = _stub_module("database")
if not hasattr(database_mod, "__path__"):
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
sys.modules["database.auth"].get_user_name = MagicMock(return_value="Alice")
sys.modules["database.goals"].get_user_goal = MagicMock(return_value=None)
sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[])
sys.modules["database.redis_db"].get_enabled_apps = MagicMock(return_value=[])
sys.modules["database.redis_db"].get_filter_category_items = MagicMock(return_value=[])
sys.modules["database.redis_db"].add_filter_category_item = MagicMock()
sys.modules["database.conversations"].get_conversations = MagicMock(return_value=[])
sys.modules["database.memories"].get_memories = MagicMock(return_value=[])
sys.modules["database.vector_db"].query_vectors_enhanced = MagicMock(return_value=[])

# --- LLM client stubs ---
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
clients_mod.anthropic_client = MagicMock()
clients_mod.ANTHROPIC_AGENT_MODEL = "claude-sonnet-4-6-20250514"
clients_mod.ANTHROPIC_AGENT_COMPLEX_MODEL = "claude-opus-4-6-20250414"
clients_mod.embeddings = MagicMock()
clients_mod.encoding = MagicMock()
clients_mod.num_tokens_from_string = MagicMock(return_value=100)

llm_mod = _stub_module("utils.llm")
if not hasattr(llm_mod, "__path__"):
    llm_mod.__path__ = []
tracker_mod = _stub_module("utils.llm.usage_tracker")
tracker_mod.get_usage_callback = MagicMock(return_value=[])
tracker_mod.set_usage_context = MagicMock()
tracker_mod.reset_usage_context = MagicMock()
tracker_mod.Features = MagicMock()
tracker_mod.track_usage = MagicMock()

# --- LLMs/memory stubs ---
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, "__path__"):
    llms_mod.__path__ = []
llms_memory_mod = _stub_module("utils.llms.memory")
llms_memory_mod.get_prompt_memories = MagicMock(return_value=("TestUser", "Some facts"))

# --- Observability stubs ---
obs_mod = _stub_module("utils.observability")
if not hasattr(obs_mod, "__path__"):
    obs_mod.__path__ = []
langsmith_mod = _stub_module("utils.observability.langsmith")
langsmith_mod.get_chat_tracer_callbacks = MagicMock(return_value=[])
langsmith_mod.is_langsmith_enabled = MagicMock(return_value=False)
langsmith_prompts_mod = _stub_module("utils.observability.langsmith_prompts")
langsmith_prompts_mod.get_agentic_system_prompt_template = MagicMock(side_effect=Exception("not available"))
langsmith_prompts_mod.render_prompt = MagicMock()
langsmith_prompts_mod.get_prompt_metadata = MagicMock(return_value=(None, None, None))

# --- Other stubs ---
other_mod = _stub_module("utils.other")
if not hasattr(other_mod, "__path__"):
    other_mod.__path__ = []
endpoints_mod = _stub_module("utils.other.endpoints")


def _passthrough_timeit(fn):
    """No-op replacement for @timeit decorator."""
    return fn


endpoints_mod.timeit = _passthrough_timeit

retrieval_mod = _stub_module("utils.retrieval")
if not hasattr(retrieval_mod, "__path__"):
    retrieval_mod.__path__ = []

safety_mod = _stub_module("utils.retrieval.safety")
safety_mod.AgentSafetyGuard = MagicMock()
safety_mod.SafetyGuardError = type("SafetyGuardError", (Exception,), {})

# --- MCP client stub ---
mcp_mod = _stub_module("utils.mcp_client")
mcp_mod.call_mcp_tool = MagicMock()


# ---------------------------------------------------------------------------
# Import real production modules (with stubs in place)
# ---------------------------------------------------------------------------


def _load_module_from_file(module_name: str, file_path: Path):
    """Import a module from a file path, adding it to sys.modules."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# We need to load models first since chat.py imports them
_stub_module("models")
sys.modules["models"].__path__ = [str(BACKEND_DIR / "models")]
# Load real model modules
_load_module_from_file("models.app", BACKEND_DIR / "models" / "app.py")
_load_module_from_file("models.other", BACKEND_DIR / "models" / "other.py")

# Stub firebase_admin (used by endpoints.py and auth)
firebase_mod = _stub_module("firebase_admin")
firebase_mod.auth = MagicMock()
firebase_mod.auth.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})
_stub_module("firebase_admin.auth")
sys.modules["firebase_admin.auth"].InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

# Stub google cloud modules
_stub_module("google")
sys.modules["google"].__path__ = []
_stub_module("google.cloud")
sys.modules["google.cloud"].__path__ = []
_stub_module("google.cloud.firestore")
_stub_module("google.cloud.firestore_v1")
_stub_module("google.auth")
_stub_module("google.auth.credentials")

# Stub additional modules needed by model imports
_stub_module("pydub")
sys.modules["pydub"].AudioSegment = MagicMock()


# ---------------------------------------------------------------------------
# Helpers to load production functions
# ---------------------------------------------------------------------------


def _get_chat_module():
    """Load and return the real utils.llm.chat module."""
    return _load_module_from_file("utils.llm.chat", BACKEND_DIR / "utils" / "llm" / "chat.py")


def _set_user(chat_mod, name: str, tz: str, goal=None):
    """
    Patch the already-bound references inside the loaded chat module.

    chat.py does `from database.auth import get_user_name` at the top, so
    reassigning on sys.modules["database.auth"] doesn't work after import.
    We must patch the name on the chat module itself.
    """
    chat_mod.get_user_name = MagicMock(return_value=name)
    chat_mod.notification_db.get_user_time_zone = MagicMock(return_value=tz)
    chat_mod.goals_db.get_user_goal = MagicMock(return_value=goal)
    chat_mod.goals_db.get_user_goals = MagicMock(return_value=[goal] if goal else [])


def _get_agentic_module():
    """Load and return the real utils.retrieval.agentic module."""
    # First make sure tool submodules are stubbed (they import from database)
    tools_pkg = _stub_module("utils.retrieval.tools")
    if not hasattr(tools_pkg, "__path__"):
        tools_pkg.__path__ = [str(BACKEND_DIR / "utils" / "retrieval" / "tools")]

    # Create mock tools with names that look like real LangChain tools
    tool_names = [
        "get_conversations_tool",
        "search_conversations_tool",
        "get_memories_tool",
        "search_memories_tool",
        "get_action_items_tool",
        "create_action_item_tool",
        "update_action_item_tool",
        "get_omi_product_info_tool",
        "perplexity_web_search_tool",
        "get_calendar_events_tool",
        "create_calendar_event_tool",
        "update_calendar_event_tool",
        "delete_calendar_event_tool",
        "get_gmail_messages_tool",
        "get_apple_health_steps_tool",
        "get_apple_health_sleep_tool",
        "get_apple_health_heart_rate_tool",
        "get_apple_health_workouts_tool",
        "get_apple_health_summary_tool",
        "search_files_tool",
        "manage_daily_summary_tool",
        "create_chart_tool",
        "get_screen_activity_tool",
        "search_screen_activity_tool",
        "save_user_preference_tool",
    ]
    for name in tool_names:
        mock_tool = MagicMock()
        mock_tool.name = name
        # Add args_schema for _convert_tools to work
        mock_schema = MagicMock()
        mock_schema.schema.return_value = {"properties": {"query": {"type": "string"}}, "required": ["query"]}
        mock_tool.args_schema = mock_schema
        mock_tool.description = f"Mock tool: {name}"
        setattr(tools_pkg, name, mock_tool)

    # Stub sub-modules
    _stub_module("utils.retrieval.tools.preference_tools")

    # Stub app_tools
    app_tools_mod = _stub_module("utils.retrieval.tools.app_tools")
    app_tools_mod.load_app_tools = MagicMock(return_value=[])
    app_tools_mod.get_tool_status_message = MagicMock(return_value=None)

    # Stub Anthropic client
    anthropic_mod = _stub_module("anthropic")
    anthropic_mod.AsyncAnthropic = MagicMock

    # Stub langsmith traceable
    langsmith_mod = _stub_module("langsmith")
    langsmith_mod.traceable = lambda **kwargs: lambda func: func

    return _load_module_from_file("utils.retrieval.agentic", BACKEND_DIR / "utils" / "retrieval" / "agentic.py")


# ---------------------------------------------------------------------------
# Tests: System prompt static prefix is byte-identical across users
# ---------------------------------------------------------------------------


def test_static_prefix_identical_for_different_users():
    """
    The static prefix of the fallback prompt must be byte-identical for
    different users so OpenAI's prefix cache can match them.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    # Generate prompts for two different users
    _set_user(chat_mod, "Alice", "America/New_York")
    prompt_alice = fn("user_alice")

    _set_user(chat_mod, "Bob", "Europe/London")
    prompt_bob = fn("user_bob")

    # Extract static prefix: everything before <assistant_role>
    marker = "<assistant_role>"
    alice_prefix = prompt_alice[: prompt_alice.index(marker)]
    bob_prefix = prompt_bob[: prompt_bob.index(marker)]

    assert alice_prefix == bob_prefix, (
        "Static prefix must be byte-identical across users for prompt cache hits.\n"
        f"Alice prefix length: {len(alice_prefix)}, Bob prefix length: {len(bob_prefix)}\n"
        f"First diff at: {_find_first_diff(alice_prefix, bob_prefix)}"
    )


def test_static_prefix_identical_with_and_without_goal():
    """
    Static prefix stays the same whether the user has a goal set or not.
    Goal section is dynamic and comes after <assistant_role>.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    # Without goal
    _set_user(chat_mod, "TestUser", "America/Los_Angeles", goal=None)
    prompt_no_goal = fn("uid_1")

    # With goal
    _set_user(
        chat_mod, "TestUser", "America/Los_Angeles", goal={"title": "Run 5K", "current_value": 2, "target_value": 5}
    )
    prompt_with_goal = fn("uid_1")

    marker = "<assistant_role>"
    prefix_no_goal = prompt_no_goal[: prompt_no_goal.index(marker)]
    prefix_with_goal = prompt_with_goal[: prompt_with_goal.index(marker)]

    assert prefix_no_goal == prefix_with_goal, "Static prefix must not change when user has a goal set"

    # But the full prompts should differ (goal section is dynamic)
    assert prompt_no_goal != prompt_with_goal, "Full prompts should differ when goal is set"
    assert "<user_goals>" in prompt_with_goal
    assert "<user_goals>" not in prompt_no_goal


def test_dynamic_sections_actually_vary_per_user():
    """
    Dynamic sections must contain user-specific data — otherwise the
    static/dynamic split is pointless.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "Alice", "US/Pacific")
    prompt_alice = fn("uid_alice")

    _set_user(chat_mod, "Bob", "Asia/Tokyo")
    prompt_bob = fn("uid_bob")

    # Dynamic suffix (from <assistant_role> onward) must differ
    marker = "<assistant_role>"
    alice_suffix = prompt_alice[prompt_alice.index(marker) :]
    bob_suffix = prompt_bob[prompt_bob.index(marker) :]

    assert alice_suffix != bob_suffix, "Dynamic suffix should differ between users"
    assert "Alice" in alice_suffix, "Alice's name should be in her dynamic suffix"
    assert "Bob" in bob_suffix, "Bob's name should be in his dynamic suffix"
    assert "US/Pacific" in alice_suffix, "Alice's timezone should be in her dynamic suffix"
    assert "Asia/Tokyo" in bob_suffix, "Bob's timezone should be in his dynamic suffix"


def test_static_prefix_contains_all_expected_sections():
    """
    The static prefix must contain all the cache-critical sections in order.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "TestUser", "UTC")
    prompt = fn("uid_test")

    marker = "<assistant_role>"
    static_prefix = prompt[: prompt.index(marker)]

    expected_sections = [
        "<response_style>",
        "</response_style>",
        "<mentor_behavior>",
        "</mentor_behavior>",
        "<notification_controls>",
        "</notification_controls>",
        "<citing_instructions>",
        "</citing_instructions>",
        "<quality_control>",
        "</quality_control>",
        "<task>",
        "</task>",
        "<critical_accuracy_rules>",
        "</critical_accuracy_rules>",
        "<chart_visualization>",
        "</chart_visualization>",
        "<conversation_retrieval_strategies>",
        "</conversation_retrieval_strategies>",
    ]

    for section in expected_sections:
        assert section in static_prefix, f"Static prefix missing expected section: {section}"

    # Verify ordering: each section should come after the previous
    positions = [static_prefix.index(s) for s in expected_sections]
    assert positions == sorted(positions), (
        "Static sections are not in the expected order. " f"Positions: {list(zip(expected_sections, positions))}"
    )


def test_static_prefix_has_no_user_specific_content():
    """
    The static prefix must not contain any user-specific template variables
    that would break byte-identity across users.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "UniqueNameXYZ123", "Pacific/Fiji")
    prompt = fn("uid_test")

    marker = "<assistant_role>"
    static_prefix = prompt[: prompt.index(marker)]

    # None of these user-specific values should appear in the static prefix
    assert "UniqueNameXYZ123" not in static_prefix, "User name leaked into static prefix"
    assert "Pacific/Fiji" not in static_prefix, "Timezone leaked into static prefix"


def test_prompt_starts_with_response_style():
    """
    The very first XML tag in the prompt must be <response_style> (static),
    not <assistant_role> (dynamic), to maximize the cacheable prefix.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "TestUser", "UTC")
    prompt = fn("uid_test")

    # Find first XML tag
    first_tag_start = prompt.index("<")
    first_tag_end = prompt.index(">", first_tag_start) + 1
    first_tag = prompt[first_tag_start:first_tag_end]

    assert first_tag == "<response_style>", f"Prompt should start with <response_style> but starts with {first_tag}"


# ---------------------------------------------------------------------------
# Tests: Static prefix token count (cache eligibility)
# ---------------------------------------------------------------------------


def test_static_prefix_exceeds_minimum_cache_tokens():
    """
    OpenAI requires at least 1,024 tokens for prefix caching.
    The static prefix (before <assistant_role>) should comfortably exceed this.
    We use a conservative 4-chars-per-token estimate.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "TestUser", "UTC")
    prompt = fn("uid_test")

    marker = "<assistant_role>"
    static_prefix = prompt[: prompt.index(marker)]

    # Conservative estimate: ~4 chars per token for English text
    estimated_tokens = len(static_prefix) / 4
    assert estimated_tokens > 1024, (
        f"Static prefix estimated at ~{int(estimated_tokens)} tokens "
        f"({len(static_prefix)} chars) — must exceed 1,024 for OpenAI cache eligibility"
    )


# ---------------------------------------------------------------------------
# Tests: CORE_TOOLS constant
# ---------------------------------------------------------------------------


def test_core_tools_has_25_tools():
    """CORE_TOOLS must contain exactly 25 tools."""
    agentic_mod = _get_agentic_module()
    assert len(agentic_mod.CORE_TOOLS) == 25, f"CORE_TOOLS has {len(agentic_mod.CORE_TOOLS)} tools, expected 25"


def test_core_tools_list_creates_independent_copy():
    """
    list(CORE_TOOLS) must create an independent copy so that appending
    app tools to one request's list doesn't mutate the shared constant.
    """
    agentic_mod = _get_agentic_module()

    tools_a = list(agentic_mod.CORE_TOOLS)
    tools_b = list(agentic_mod.CORE_TOOLS)

    # They should be equal but NOT the same object
    assert tools_a == tools_b
    assert tools_a is not tools_b
    assert tools_a is not agentic_mod.CORE_TOOLS

    # Mutating one should not affect the other
    mock_app_tool = MagicMock()
    mock_app_tool.name = "custom_app_tool"
    tools_a.append(mock_app_tool)

    assert len(tools_a) == 26
    assert len(tools_b) == 25
    assert len(agentic_mod.CORE_TOOLS) == 25, "CORE_TOOLS was mutated!"


def test_core_tools_order_matches_exports():
    """
    CORE_TOOLS order must match the __all__ export order from tools/__init__.py
    to ensure deterministic serialization.
    """
    agentic_mod = _get_agentic_module()

    expected_names = [
        "get_conversations_tool",
        "search_conversations_tool",
        "get_memories_tool",
        "search_memories_tool",
        "get_action_items_tool",
        "create_action_item_tool",
        "update_action_item_tool",
        "get_omi_product_info_tool",
        "perplexity_web_search_tool",
        "get_calendar_events_tool",
        "create_calendar_event_tool",
        "update_calendar_event_tool",
        "delete_calendar_event_tool",
        "get_gmail_messages_tool",
        "get_apple_health_steps_tool",
        "get_apple_health_sleep_tool",
        "get_apple_health_heart_rate_tool",
        "get_apple_health_workouts_tool",
        "get_apple_health_summary_tool",
        "search_files_tool",
        "manage_daily_summary_tool",
        "create_chart_tool",
        "get_screen_activity_tool",
        "search_screen_activity_tool",
        "save_user_preference_tool",
    ]

    actual_names = [t.name for t in agentic_mod.CORE_TOOLS]
    assert (
        actual_names == expected_names
    ), f"CORE_TOOLS order mismatch.\nExpected: {expected_names}\nActual: {actual_names}"


def test_core_tools_not_accidentally_duplicated():
    """No tool should appear twice in CORE_TOOLS."""
    agentic_mod = _get_agentic_module()
    names = [t.name for t in agentic_mod.CORE_TOOLS]
    assert len(names) == len(set(names)), f"Duplicate tools in CORE_TOOLS: {[n for n in names if names.count(n) > 1]}"


# ---------------------------------------------------------------------------
# Tests: LLM client cache configuration (runtime check)
# ---------------------------------------------------------------------------


def test_llm_agent_model_kwargs_via_real_instantiation():
    """
    Load clients.py with a FakeChatOpenAI to capture actual constructor kwargs.
    Verifies prompt_cache_key is passed at runtime,
    not just present in source text.
    """
    captured_calls = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured_calls.append(kwargs)

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs):
            pass

    # Temporarily remove cached module so we get a fresh load
    saved = sys.modules.pop("utils.llm.clients_real", None)

    # Stub the dependencies that clients.py imports
    fake_langchain_openai = _stub_module("langchain_openai_fake")
    fake_langchain_openai.ChatOpenAI = FakeChatOpenAI
    fake_langchain_openai.OpenAIEmbeddings = FakeOpenAIEmbeddings

    fake_tiktoken = _stub_module("tiktoken_fake")
    fake_tiktoken.encoding_for_model = MagicMock(return_value=MagicMock())

    # Read source, replace imports, exec in isolated namespace
    source = (BACKEND_DIR / "utils" / "llm" / "clients.py").read_text()
    source = source.replace("from langchain_openai import ChatOpenAI, OpenAIEmbeddings", "")
    source = source.replace("import tiktoken", "")
    source = source.replace("import anthropic", "")
    source = source.replace("from langchain_core.output_parsers import PydanticOutputParser", "")
    source = source.replace("from models.conversation import Structured", "")
    source = source.replace("from utils.llm.usage_tracker import get_usage_callback", "")

    # Create a fake anthropic module with AsyncAnthropic
    fake_anthropic = _stub_module("anthropic_fake")
    fake_anthropic.AsyncAnthropic = MagicMock

    ns = {
        "os": os,
        "ChatOpenAI": FakeChatOpenAI,
        "OpenAIEmbeddings": FakeOpenAIEmbeddings,
        "tiktoken": fake_tiktoken,
        "anthropic": fake_anthropic,
        "PydanticOutputParser": MagicMock(),
        "Structured": MagicMock(),
        "get_usage_callback": MagicMock(return_value=[]),
        "List": list,
    }
    exec(source, ns)

    # Find clients that have prompt cache kwargs (should be exactly the 2 agent clients)
    cache_clients = [c for c in captured_calls if "prompt_cache_key" in c.get("model_kwargs", {})]
    assert len(cache_clients) == 2, f"Expected exactly 2 clients with prompt_cache_key, found {len(cache_clients)}"

    for call in cache_clients:
        mkw = call["model_kwargs"]
        assert mkw["prompt_cache_key"] == "omi-agent-v1", f"Wrong prompt_cache_key: {mkw}"
        assert call["model"] == "gpt-5.1", f"Cache kwargs should only be on gpt-5.1, got {call['model']}"

    # Verify one is streaming, one is not
    streaming_cache = [c for c in cache_clients if c.get("streaming")]
    non_streaming_cache = [c for c in cache_clients if not c.get("streaming")]
    assert len(streaming_cache) == 1, "Should have exactly 1 streaming agent with cache"
    assert len(non_streaming_cache) == 1, "Should have exactly 1 non-streaming agent with cache"

    # Verify non-cache clients do NOT have prompt_cache_key
    non_cache_clients = [c for c in captured_calls if "prompt_cache_key" not in c.get("model_kwargs", {})]
    assert len(non_cache_clients) > 0, "Should have some clients without cache kwargs"
    for call in non_cache_clients:
        mkw = call.get("model_kwargs", {})
        assert "prompt_cache_key" not in mkw, f"Client {call.get('model')} should not have prompt_cache_key"


# ---------------------------------------------------------------------------
# Tests: Tool list construction in execute functions
# ---------------------------------------------------------------------------


def test_convert_tools_produces_valid_anthropic_schemas():
    """
    _convert_tools should produce valid Anthropic tool schemas from CORE_TOOLS,
    filtering out the 'config' parameter and preserving tool order.
    """
    agentic_mod = _get_agentic_module()

    tool_schemas, tool_registry = agentic_mod._convert_tools(agentic_mod.CORE_TOOLS)

    assert len(tool_schemas) == len(agentic_mod.CORE_TOOLS), "Should produce one schema per tool"
    assert len(tool_registry) == len(agentic_mod.CORE_TOOLS), "Should register all tools"

    for schema in tool_schemas:
        assert "name" in schema, "Schema must have a name"
        assert "description" in schema, "Schema must have a description"
        assert "input_schema" in schema, "Schema must have input_schema"
        # Config parameter should be filtered out
        props = schema["input_schema"].get("properties", {})
        assert "config" not in props, f"Tool {schema['name']} should not expose 'config' parameter"
        # Core tools should NOT have defer_loading
        assert "defer_loading" not in schema, f"Core tool {schema['name']} should not have defer_loading"


def test_convert_tools_defers_app_tools():
    """
    App tools should be marked with defer_loading=True and tool_search_tool
    should be added when app tools are present.
    """
    agentic_mod = _get_agentic_module()

    mock_app_tool = MagicMock()
    mock_app_tool.name = "custom_weather_app"
    mock_schema = MagicMock()
    mock_schema.schema.return_value = {"properties": {"query": {"type": "string"}}, "required": ["query"]}
    mock_app_tool.args_schema = mock_schema
    mock_app_tool.description = "Mock app tool"

    tool_schemas, tool_registry = agentic_mod._convert_tools(agentic_mod.CORE_TOOLS, [mock_app_tool])

    # Should have tool_search_tool + core tools + 1 app tool
    assert len(tool_schemas) == len(agentic_mod.CORE_TOOLS) + 2  # +1 search tool, +1 app tool

    # First should be tool_search_tool
    assert tool_schemas[0]["type"] == "tool_search_tool_regex_20251119"

    # Last should be the deferred app tool
    assert tool_schemas[-1]["name"] == "custom_weather_app"
    assert tool_schemas[-1]["defer_loading"] is True

    # Registry should include all tools
    assert "custom_weather_app" in tool_registry


def test_convert_tools_preserves_core_tool_order():
    """
    Tool schemas should be in the same order as CORE_TOOLS to ensure
    deterministic serialization for prompt caching.
    """
    agentic_mod = _get_agentic_module()

    tool_schemas, _ = agentic_mod._convert_tools(agentic_mod.CORE_TOOLS)

    schema_names = [s["name"] for s in tool_schemas]
    core_names = [t.name for t in agentic_mod.CORE_TOOLS]
    assert schema_names == core_names, "Tool schema order must match CORE_TOOLS order"


# ---------------------------------------------------------------------------
# Tests: Persona app bypasses cache optimization (expected)
# ---------------------------------------------------------------------------


def test_persona_app_overrides_system_prompt():
    """
    When app.is_a_persona() is True, the entire system prompt is replaced,
    bypassing the cache-optimized structure. This is expected behavior.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "TestUser", "UTC")

    mock_app = MagicMock()
    mock_app.is_a_persona.return_value = True
    mock_app.persona_prompt = "You are a pirate captain. Talk like a pirate."
    mock_app.chat_prompt = "fallback"

    prompt = fn("uid_test", app=mock_app)

    assert prompt == "You are a pirate captain. Talk like a pirate."
    assert "<response_style>" not in prompt, "Persona prompt should not contain cache-optimized structure"


# ---------------------------------------------------------------------------
# Tests: Plugin app preserves static prefix
# ---------------------------------------------------------------------------


def test_plugin_app_does_not_break_static_prefix():
    """
    Regular (non-persona) apps add a <plugin_instructions> section but
    should NOT affect the static prefix before <assistant_role>.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "TestUser", "UTC")

    # No app
    prompt_no_app = fn("uid_test")

    # Regular app (not persona)
    mock_app = MagicMock()
    mock_app.is_a_persona.return_value = False
    mock_app.name = "WeatherBot"
    mock_app.description = "A weather assistant"

    prompt_with_app = fn("uid_test", app=mock_app)

    marker = "<assistant_role>"
    prefix_no_app = prompt_no_app[: prompt_no_app.index(marker)]
    prefix_with_app = prompt_with_app[: prompt_with_app.index(marker)]

    assert prefix_no_app == prefix_with_app, "Plugin app should not alter the static prefix"
    assert "<plugin_instructions>" in prompt_with_app, "Plugin section should be in the full prompt"


# ---------------------------------------------------------------------------
# Tests: Page context and file context are in dynamic section
# ---------------------------------------------------------------------------


def test_page_context_in_dynamic_section():
    """
    Page context (<current_context>) should appear in the dynamic section,
    not the static prefix.
    """
    chat_mod = _get_chat_module()
    fn = chat_mod._get_agentic_qa_prompt

    _set_user(chat_mod, "TestUser", "UTC")

    mock_context = MagicMock()
    mock_context.type = "conversation"
    mock_context.id = "conv_123"
    mock_context.title = "Meeting with team"

    prompt = fn("uid_test", context=mock_context)

    marker = "<assistant_role>"
    static_prefix = prompt[: prompt.index(marker)]
    dynamic_suffix = prompt[prompt.index(marker) :]

    assert "<current_context>" not in static_prefix, "Page context leaked into static prefix"
    assert "<current_context>" in dynamic_suffix, "Page context should be in dynamic suffix"
    assert "Meeting with team" in dynamic_suffix


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _find_first_diff(a: str, b: str) -> str:
    """Find the position and context of the first character difference."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            ctx_start = max(0, i - 20)
            return (
                f"position {i}: "
                f"a[{ctx_start}:{i+20}]='{a[ctx_start:i+20]}' vs "
                f"b[{ctx_start}:{i+20}]='{b[ctx_start:i+20]}'"
            )
    if len(a) != len(b):
        return f"strings differ in length: {len(a)} vs {len(b)}"
    return "no difference found"
