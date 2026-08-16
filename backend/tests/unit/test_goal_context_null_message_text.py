"""Regression test: a null message text must not drop the whole chat block from goal context.

utils.llm.goals._get_goal_context builds goal-advice context from recent chat messages with
text = msg.get('text', '')[:200]. get's default only applies to an ABSENT key, so a stored
message with text=None makes None[:200] raise; the broad except then leaves chat_context empty,
dropping the entire recent-chat block from the goal-advice prompt. The memory block below already
guards with if m.get('content'). Null text now coerces to '' and is skipped, keeping the rest.
"""

import utils.llm.goals as goals


def _isolate(monkeypatch, messages):
    monkeypatch.setattr(goals, 'vector_search', lambda *a, **k: [])
    monkeypatch.setattr(goals.conversations_db, 'get_conversations', lambda *a, **k: [])
    monkeypatch.setattr(goals.memories_db, 'get_memories', lambda *a, **k: [])
    monkeypatch.setattr(goals.chat_db, 'get_messages', lambda *a, **k: messages)


def test_null_text_message_does_not_drop_chat_block(monkeypatch):
    _isolate(
        monkeypatch,
        [
            {'sender': 'human', 'text': None},
            {'sender': 'human', 'text': 'I want to run a marathon'},
        ],
    )

    result = goals._get_goal_context('u1', 'fitness')

    assert 'I want to run a marathon' in result['chat_context']


def test_all_valid_messages_present(monkeypatch):
    _isolate(monkeypatch, [{'sender': 'human', 'text': 'hello'}, {'sender': 'ai', 'text': 'hi there'}])

    result = goals._get_goal_context('u1', 'fitness')

    assert 'User: hello' in result['chat_context']
    assert 'Omi: hi there' in result['chat_context']
