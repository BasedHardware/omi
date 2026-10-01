"""Unit tests for chat continuation protocol (Issue #20133).

Verifies that when a long chat answer stops at its output boundary or ends after
a partial response, replying with an unambiguous continuation request (e.g. "Continue")
resumes the immediately preceding assistant answer without restarting from scratch,
repeating already delivered content, or omitting text.
"""

from datetime import datetime, timezone
import pytest

from models.chat import Message
from utils.retrieval.continuation import (
    CONTINUATION_SYSTEM_CONTRACT,
    format_continuation_user_prompt,
    get_continuation_target,
    inject_continuation_directive,
    is_continuation_request,
    strip_continuation_overlap,
)

# ---------------------------------------------------------------------------
# Unit tests: is_continuation_request
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "continue",
        "Continue",
        "CONTINUE",
        "continue.",
        "continue!",
        "Continue...",
        "please continue",
        "Please continue",
        "pls continue",
        "continue please",
        "Continue please",
        "keep going",
        "Keep going",
        "keep going please",
        "go on",
        "Go on",
        "resume",
        "Resume",
        "carry on",
        "Carry on",
        "continue from where you left off",
        "Continue from where you left off",
        "continue where you left off",
        "can you continue",
        "Could you continue please?",
        "continue the response",
        "continue the answer",
        "continue your response",
        "continue your answer",
    ],
)
def test_is_continuation_request_matches_valid_patterns(text: str):
    assert is_continuation_request(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        None,
        "What is the capital of France?",
        "Can you summarize my meetings?",
        "Continue the story about aliens on Mars",
        "I will continue later tonight",
        "Should we continue?",
        "Why did you continue?",
        "tell me more",
        "more details please",
        "next topic",
    ],
)
def test_is_continuation_request_rejects_non_continuation(text: str):
    assert is_continuation_request(text) is False


# ---------------------------------------------------------------------------
# Unit tests: get_continuation_target
# ---------------------------------------------------------------------------


def test_get_continuation_target_returns_prior_assistant_message():
    ai_turn = Message(
        id="msg-1",
        text="Here is the summary of your morning: at 9:00 AM you met with Sarah regarding the Q3 budget.",
        created_at=datetime.now(timezone.utc),
        sender="ai",
        type="text",
    )
    user_turn = Message(
        id="msg-2",
        text="Continue",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )
    target = get_continuation_target([ai_turn, user_turn])
    assert target is ai_turn
    assert target.text == ai_turn.text


def test_get_continuation_target_returns_none_for_insufficient_history():
    user_turn = Message(
        id="msg-1",
        text="Continue",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )
    assert get_continuation_target([]) is None
    assert get_continuation_target([user_turn]) is None


def test_get_continuation_target_returns_none_when_prior_is_not_ai():
    user_turn1 = Message(
        id="msg-1",
        text="Hello",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )
    user_turn2 = Message(
        id="msg-2",
        text="Continue",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )
    assert get_continuation_target([user_turn1, user_turn2]) is None


def test_get_continuation_target_returns_none_when_prior_ai_message_is_empty():
    ai_turn = Message(
        id="msg-1",
        text="",
        created_at=datetime.now(timezone.utc),
        sender="ai",
        type="text",
    )
    user_turn = Message(
        id="msg-2",
        text="Continue",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )
    assert get_continuation_target([ai_turn, user_turn]) is None


# ---------------------------------------------------------------------------
# Unit tests: format_continuation_user_prompt & inject_continuation_directive
# ---------------------------------------------------------------------------


def test_format_continuation_user_prompt_includes_anchor_tail():
    prior_tail = "They decided to migrate the cluster to us-central1 by next Friday."
    formatted = format_continuation_user_prompt("Continue", prior_tail)
    assert "Continue" in formatted
    assert "[Instruction: Resume your immediately preceding answer" in formatted
    assert "Do NOT restart, summarize, or repeat already delivered content." in formatted
    assert "They decided to migrate the cluster to us-central1 by next Friday." in formatted


def test_inject_continuation_directive_updates_latest_user_message():
    messages = [
        {"role": "user", "content": "Tell me about my week."},
        {"role": "assistant", "content": "Monday was busy with two customer calls..."},
        {"role": "user", "content": "2026-10-01T14:00:00Z\n\nContinue"},
    ]
    updated = inject_continuation_directive(messages, "Monday was busy with two customer calls...")
    assert len(updated) == 3
    assert updated[0]["content"] == "Tell me about my week."
    assert "2026-10-01T14:00:00Z\n\nContinue" in updated[2]["content"]
    assert "Resume your immediately preceding answer" in updated[2]["content"]
    assert "Monday was busy with two customer calls..." in updated[2]["content"]


def test_inject_continuation_directive_handles_multimodal_list_content():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Continue"}]},
    ]
    updated = inject_continuation_directive(messages, "Ending of prior text.")
    assert len(updated[0]["content"]) == 2
    assert "Resume your immediately preceding answer" in updated[0]["content"][1]["text"]


# ---------------------------------------------------------------------------
# Unit tests: strip_continuation_overlap
# ---------------------------------------------------------------------------


def test_strip_continuation_overlap_removes_repeated_tail_words():
    prior_tail = "We concluded the review and decided to launch the feature on Monday morning."
    continuation = "decided to launch the feature on Monday morning. In addition, Tuesday will have QA sync."
    stripped = strip_continuation_overlap(continuation, prior_tail)
    assert stripped == "In addition, Tuesday will have QA sync."


def test_strip_continuation_overlap_preserves_distinct_continuation():
    prior_tail = "We concluded the review and decided to launch the feature on Monday morning."
    continuation = "After that launch, the backend team will monitor error rates."
    stripped = strip_continuation_overlap(continuation, prior_tail)
    assert stripped == continuation


def test_strip_continuation_overlap_handles_empty_inputs():
    assert strip_continuation_overlap("", "some tail") == ""
    assert strip_continuation_overlap("some text", "") == "some text"
    assert strip_continuation_overlap("some text", None) == "some text"


# ---------------------------------------------------------------------------
# Integration tests: persona stream with continuation contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persona_chat_stream_applies_continuation_contract(monkeypatch):
    from unittest.mock import MagicMock
    from models.app import App
    from utils.retrieval.graph import execute_persona_chat_stream

    app = App(
        id="app-1",
        name="Test Persona",
        description="A helpful assistant",
        category="general",
        author="Test Author",
        image="/images/test.png",
        capabilities=["chat"],
        persona_prompt="You are a helpful persona.",
    )

    ai_turn = Message(
        id="msg-1",
        text="Part one of the story: long ago in a distant kingdom...",
        created_at=datetime.now(timezone.utc),
        sender="ai",
        type="text",
    )
    user_turn = Message(
        id="msg-2",
        text="Continue",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text",
    )

    captured_messages = []

    class MockLLM:
        async def agenerate(self, messages, callbacks=None, **kwargs):
            nonlocal captured_messages
            captured_messages = messages[0]
            callback = callbacks[0]
            await callback.on_llm_new_token("in a distant kingdom... there was a castle.")
            await callback.end()
            return MagicMock()

    monkeypatch.setattr("utils.retrieval.graph.get_llm", lambda *a, **kw: MockLLM())

    from contextlib import contextmanager

    @contextmanager
    def mock_track_usage(*args, **kwargs):
        yield

    monkeypatch.setattr("utils.retrieval.graph.track_usage", mock_track_usage)

    callback_data = {}
    chunks = []
    async for chunk in execute_persona_chat_stream(
        uid="u1",
        messages=[ai_turn, user_turn],
        app=app,
        callback_data=callback_data,
    ):
        if chunk:
            chunks.append(chunk)

    # 1. SystemMessage has continuation contract
    assert any("<continuation_contract>" in m.content for m in captured_messages if m.type == "system")
    # 2. HumanMessage has instruction referencing prior tail
    assert any("Resume your immediately preceding answer" in m.content for m in captured_messages if m.type == "human")
    # 3. Repeated prefix was stripped from answer
    assert callback_data.get("answer") == "there was a castle."
