"""Tests for append-only message window optimization (#4692).

Validates that compute_append_window_limit produces cache-friendly windows:
- Window grows append-only (preserving prefix for OpenAI prompt caching)
- Resets at max_window boundary by dropping oldest min_context messages
- Between resets, every request's message prefix is identical to previous + 1 new message
"""

import sys
import types

# Stub out heavy dependencies so we can import routers.chat without them
_STUBS = {}


def _stub_module(name, attrs=None):
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    _STUBS[name] = mod


# Stub database and other heavy modules
_stub_module('google.cloud', {'firestore': types.ModuleType('firestore')})
_stub_module('google.cloud.firestore')
_stub_module('google.cloud.firestore_v1', {'FieldFilter': None})
_stub_module('database')
_stub_module('database._client', {'db': None})
_stub_module(
    'database.helpers',
    {
        'set_data_protection_level': lambda **kw: (lambda f: f),
        'prepare_for_write': lambda **kw: (lambda f: f),
        'prepare_for_read': lambda **kw: (lambda f: f),
    },
)
_stub_module('database.chat')
_stub_module('database.conversations')
_stub_module('database.apps', {'record_app_usage': None})
_stub_module('database.users')
_stub_module('database.redis_db', {'get_filter_category_items': None})
_stub_module('database.vector_db', {'query_vectors_by_metadata': None})
_stub_module('database.notifications', {'get_user_time_zone': None})
_stub_module('utils.encryption', {'encrypt': None, 'decrypt': None})
_stub_module('utils.other')
_stub_module('utils.other.endpoints', {'timeit': lambda f: f, 'get_current_user_uid': None})
_stub_module('utils.other.storage')
_stub_module('utils.other.chat_file', {'FileChatTool': None})
_stub_module('utils.apps', {'get_available_app_by_id': None})
_stub_module(
    'utils.chat',
    {
        'process_voice_message_segment': None,
        'process_voice_message_segment_stream': None,
        'resolve_voice_message_language': None,
        'transcribe_voice_message_segment': None,
    },
)
_stub_module('utils.llm')
_stub_module('utils.llm.persona', {'initial_persona_chat_message': None})
_stub_module('utils.llm.chat', {'initial_chat_message': None})
_stub_module('utils.llm.goals', {'extract_and_update_goal_progress': None})
_stub_module('utils.llm.usage_tracker', {'set_usage_context': None, 'reset_usage_context': None, 'Features': None})
_stub_module('utils.retrieval')
_stub_module(
    'utils.retrieval.graph',
    {
        'execute_graph_chat': None,
        'execute_graph_chat_stream': None,
        'execute_persona_chat_stream': None,
    },
)
_stub_module(
    'utils.retrieval.agentic',
    {
        'execute_agentic_chat': None,
        'execute_agentic_chat_stream': None,
    },
)
_stub_module('utils.app_integrations', {'get_github_docs_content': None})
_stub_module('utils.observability')
_stub_module('utils.observability.langsmith', {'get_chat_tracer_callbacks': None})
_stub_module('utils.observability.langsmith_prompts', {'get_prompt_metadata': None})
_stub_module('models')
_stub_module('models.app', {'App': None, 'UsageHistoryType': None})
_stub_module(
    'models.chat',
    {
        'ChatSession': None,
        'Message': None,
        'SendMessageRequest': None,
        'MessageSender': type('MessageSender', (), {'ai': 'ai'}),
        'ResponseMessage': None,
        'MessageConversation': None,
        'FileChat': None,
        'PageContext': None,
    },
)
_stub_module('models.conversation', {'Conversation': None})
_stub_module('models.other', {'Person': None})
_stub_module('routers.sync', {'retrieve_file_paths': None, 'decode_files_to_wav': None})
_stub_module(
    'fastapi',
    {
        'APIRouter': lambda: type(
            'Router',
            (),
            {
                'post': lambda *a, **kw: (lambda f: f),
                'get': lambda *a, **kw: (lambda f: f),
                'delete': lambda *a, **kw: (lambda f: f),
            },
        )(),
        'Depends': lambda f: None,
        'HTTPException': Exception,
        'UploadFile': None,
        'File': lambda *a, **kw: None,
        'Form': lambda *a, **kw: None,
    },
)
_stub_module('fastapi.responses', {'StreamingResponse': None})
_stub_module('multipart')
_stub_module('multipart.multipart', {'shutil': None})

# Now import the function under test
from routers.chat import compute_append_window_limit


class TestComputeAppendWindowLimit:
    """Test the append-only window calculation."""

    def test_small_conversation_returns_total(self):
        """Conversations smaller than max_window return all messages."""
        assert compute_append_window_limit(1) == 1
        assert compute_append_window_limit(5) == 5
        assert compute_append_window_limit(10) == 10
        assert compute_append_window_limit(15) == 15
        assert compute_append_window_limit(20) == 20

    def test_first_reset_at_max_window_plus_one(self):
        """At max_window+1, window resets: drops oldest min_context."""
        # total=21 -> resets=1, start=10, limit=11
        assert compute_append_window_limit(21) == 11

    def test_window_grows_after_reset(self):
        """After reset, window grows append-only again."""
        assert compute_append_window_limit(22) == 12
        assert compute_append_window_limit(25) == 15
        assert compute_append_window_limit(30) == 20  # hits max again

    def test_second_reset(self):
        """Second reset at total=31."""
        assert compute_append_window_limit(31) == 11
        assert compute_append_window_limit(35) == 15
        assert compute_append_window_limit(40) == 20

    def test_third_reset(self):
        """Third reset at total=41."""
        assert compute_append_window_limit(41) == 11
        assert compute_append_window_limit(50) == 20

    def test_zero_or_negative_returns_min_context(self):
        """Edge case: zero or negative total returns min_context fallback."""
        assert compute_append_window_limit(0) == 10
        assert compute_append_window_limit(-1) == 10

    def test_custom_parameters(self):
        """Custom min_context and max_window."""
        # min=5, max=15
        assert compute_append_window_limit(15, min_context=5, max_window=15) == 15
        assert compute_append_window_limit(16, min_context=5, max_window=15) == 11
        assert compute_append_window_limit(20, min_context=5, max_window=15) == 15
        assert compute_append_window_limit(21, min_context=5, max_window=15) == 11

    def test_window_never_exceeds_max(self):
        """Window size never exceeds max_window."""
        for total in range(1, 200):
            limit = compute_append_window_limit(total)
            assert limit <= 20, f"total={total} produced limit={limit} > 20"

    def test_window_always_at_least_min_context_after_enough_messages(self):
        """Once total >= min_context, window is always >= min_context."""
        for total in range(10, 200):
            limit = compute_append_window_limit(total)
            assert limit >= 10, f"total={total} produced limit={limit} < 10"

    def test_non_multiple_min_max_ratio(self):
        """Non-multiple min_context/max_window (e.g., 6/20) still behaves correctly."""
        # min=6, max=20: reset at 21, window_start jumps by 6
        assert compute_append_window_limit(20, min_context=6, max_window=20) == 20
        assert compute_append_window_limit(21, min_context=6, max_window=20) == 15  # 21 - 6 = 15
        assert compute_append_window_limit(26, min_context=6, max_window=20) == 20  # 26 - 6 = 20
        assert compute_append_window_limit(27, min_context=6, max_window=20) == 15  # 27 - 12 = 15
        # Bounds still hold
        for total in range(1, 100):
            limit = compute_append_window_limit(total, min_context=6, max_window=20)
            assert limit <= 20, f"total={total} produced limit={limit} > 20"
            if total >= 6:
                assert limit >= 6, f"total={total} produced limit={limit} < 6"

    def test_degenerate_min_equals_max(self):
        """When min_context == max_window, every message triggers a reset."""
        # min=10, max=10: at total=11, excess=1, resets=1, start=10, limit=1
        assert compute_append_window_limit(10, min_context=10, max_window=10) == 10
        assert compute_append_window_limit(11, min_context=10, max_window=10) == 1
        assert compute_append_window_limit(20, min_context=10, max_window=10) == 10
        assert compute_append_window_limit(21, min_context=10, max_window=10) == 1

    def test_prefix_stability_between_resets(self):
        """Between resets, older messages are always included (append-only prefix).

        For consecutive totals within the same window epoch, the messages
        included at total=N should be a prefix of messages at total=N+1.
        This is the key property for prompt cache reuse.
        """
        for total in range(1, 100):
            limit_now = compute_append_window_limit(total)
            limit_next = compute_append_window_limit(total + 1)
            # The window start for 'now': total - limit_now
            # The window start for 'next': (total+1) - limit_next
            start_now = total - limit_now
            start_next = (total + 1) - limit_next
            # Between resets, start should not change (prefix stable)
            # After a reset, start jumps forward by min_context
            if start_now != start_next:
                # This is a reset point: start should jump by exactly min_context
                assert start_next == start_now + 10, (
                    f"total={total}: start jumped from {start_now} to {start_next}, " f"expected jump of 10"
                )
