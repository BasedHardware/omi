import os
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import database.goals as goals_db
import utils.llm.chat as llm_chat
from tests.unit.test_goals_any_active_goal import _Client, _goal

GOALS = {
    'goal_a': _goal('Read 12 books'),
    'goal_b': _goal('Run a 10k'),
    'goal_c': _goal('Learn Spanish'),
    'goal_d': _goal('Save 10000 dollars'),
}


def test_chat_prompt_lists_every_active_goal(monkeypatch):
    monkeypatch.setattr(goals_db, '_get_db', lambda firestore_client=None: _Client(GOALS))
    monkeypatch.setattr(llm_chat, 'get_user_name', MagicMock(return_value='Tester'))
    monkeypatch.setattr(llm_chat.notification_db, 'get_user_time_zone', MagicMock(return_value='UTC'))

    prompt = llm_chat._get_agentic_qa_prompt('u1')

    for goal in GOALS.values():
        assert goal['title'] in prompt
