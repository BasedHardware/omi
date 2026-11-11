"""Tests for the oversized chat-input guard (utils/retrieval/safety.py).

The guard keeps the most recent turns that fit a token budget and flags when the newest turn
alone is too large. Extremely long messages otherwise blow the model's context window, the agent
loop swallows the resulting error, and the mobile client is left with no finalized reply. These
tests exercise the pure decision logic with an injected token counter, so they need none of the
heavy chat/LLM import stack.
"""

from types import SimpleNamespace

from utils.retrieval.safety import (
    INPUT_TOO_LONG_MESSAGE,
    MAX_CHAT_INPUT_TOKENS,
    fit_within_budget,
    message_text,
)

# Deterministic counter: 1 token per character.
CHARS = len


def _text(item):
    return item


class TestMessageText:
    def test_plain_string(self):
        assert message_text("hello") == "hello"

    def test_block_list_joins_text_blocks(self):
        content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        assert message_text(content) == "a\nb"

    def test_block_list_skips_non_text_blocks(self):
        content = [
            {"type": "text", "text": "keep"},
            {"type": "image", "source": {"data": "..."}},
            {"type": "tool_result", "content": "..."},
        ]
        assert message_text(content) == "keep"

    def test_bare_string_list(self):
        assert message_text(["x", "y"]) == "x\ny"

    def test_non_text_content_is_empty(self):
        assert message_text(None) == ""
        assert message_text(123) == ""
        assert message_text([{"type": "image"}]) == ""


class TestFitWithinBudget:
    def test_empty_input(self):
        kept, too_long = fit_within_budget([], _text, CHARS, limit=10)
        assert kept == []
        assert too_long is False

    def test_single_message_under_budget_is_kept(self):
        kept, too_long = fit_within_budget(["abc"], _text, CHARS, limit=10)
        assert kept == ["abc"]
        assert too_long is False

    def test_newest_message_over_budget_is_rejected(self):
        kept, too_long = fit_within_budget(["a" * 20], _text, CHARS, limit=10)
        assert kept == []
        assert too_long is True

    def test_history_over_budget_drops_oldest_keeps_recent(self):
        # tokens: aaaa=4, bbbb=4, cccc=4, dd=2; budget 10 -> keep dd(2)+cccc(4)+bbbb(4)=10, drop aaaa.
        items = ["aaaa", "bbbb", "cccc", "dd"]
        kept, too_long = fit_within_budget(items, _text, CHARS, limit=10)
        assert kept == ["bbbb", "cccc", "dd"]
        assert too_long is False

    def test_always_keeps_newest_even_when_it_fills_budget(self):
        # newest "b"*10 exactly fills the budget; the older turn must be dropped, newest kept.
        items = ["aaaa", "b" * 10]
        kept, too_long = fit_within_budget(items, _text, CHARS, limit=10)
        assert kept == ["b" * 10]
        assert too_long is False

    def test_newest_at_exactly_limit_is_not_rejected(self):
        kept, too_long = fit_within_budget(["x" * 10], _text, CHARS, limit=10)
        assert kept == ["x" * 10]
        assert too_long is False

    def test_all_fit_preserves_order(self):
        items = ["a", "bb", "ccc"]
        kept, too_long = fit_within_budget(items, _text, CHARS, limit=100)
        assert kept == ["a", "bb", "ccc"]
        assert too_long is False

    def test_message_like_objects_with_text_attr(self):
        msgs = [
            SimpleNamespace(text="old" * 10),  # 30
            SimpleNamespace(text="mid" * 5),  # 15
            SimpleNamespace(text="new"),  # 3
        ]
        kept, too_long = fit_within_budget(msgs, lambda m: m.text or "", CHARS, limit=20)
        # keep new(3)+mid(15)=18, drop old(30).
        assert [m.text for m in kept] == ["mid" * 5, "new"]
        assert too_long is False

    def test_null_text_is_treated_as_empty(self):
        # A stored message can have null text; the extractor must not crash on it.
        msgs = [SimpleNamespace(text=None), SimpleNamespace(text="hi")]
        kept, too_long = fit_within_budget(msgs, lambda m: m.text or "", CHARS, limit=10)
        assert [m.text for m in kept] == [None, "hi"]
        assert too_long is False

    def test_default_limit_is_used_when_omitted(self):
        # Under the real default budget, a normal message is always kept.
        kept, too_long = fit_within_budget(["a short message"], _text, CHARS)
        assert kept == ["a short message"]
        assert too_long is False


class TestConstants:
    def test_default_budget_is_positive_and_reasonable(self):
        assert MAX_CHAT_INPUT_TOKENS > 0
        # Must sit below the 200k model window with headroom for prompt/tools/reply.
        assert MAX_CHAT_INPUT_TOKENS <= 200_000

    def test_too_long_message_is_actionable(self):
        assert "shorten" in INPUT_TOO_LONG_MESSAGE.lower()


# ---------------------------------------------------------------------------
# Wiring guard: parse the agent source (no import, so no heavy chat/LLM deps) and assert the
# oversized-input check runs before the model producer task is ever started. Mirrors the AST
# style of test_chat_file_stream_async.py and stops a refactor from silently dropping the guard.
# ---------------------------------------------------------------------------

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENTIC_FILE = BACKEND_DIR / 'utils' / 'retrieval' / 'agentic.py'
AGENT_FN = 'execute_agentic_chat_stream'


def _load_function(name):
    tree = ast.parse(AGENTIC_FILE.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {AGENTIC_FILE}')


def _call_line(fn_node, callee):
    """First line where `callee(...)` is called inside fn_node, or None."""
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, 'attr', None)
            if name == callee:
                return node.lineno
    return None


class TestGuardWiredIntoAgentStream:
    def test_agent_stream_calls_fit_within_budget(self):
        fn = _load_function(AGENT_FN)
        assert (
            _call_line(fn, 'fit_within_budget') is not None
        ), f'{AGENT_FN} must call fit_within_budget to bound oversized input'

    def test_guard_runs_before_producer_task_starts(self):
        fn = _load_function(AGENT_FN)
        guard_line = _call_line(fn, 'fit_within_budget')
        producer_line = _call_line(fn, 'create_task')
        assert guard_line is not None and producer_line is not None
        assert guard_line < producer_line, (
            'input guard must run before the Anthropic producer task is created, '
            'otherwise oversized input still reaches the model'
        )
