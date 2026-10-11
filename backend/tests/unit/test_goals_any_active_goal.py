import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from contextlib import nullcontext
from types import SimpleNamespace

import database.goals as goals_db
import utils.llm.goals as llm_goals


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None

    def get(self):
        return self


class _Goals:
    def __init__(self, goals):
        self._goals = goals
        self._limit = None

    def where(self, **_kwargs):
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        docs = [_Doc(doc_id, self._goals[doc_id]) for doc_id in sorted(self._goals)]
        return docs if self._limit is None else docs[: self._limit]

    def document(self, doc_id):
        return _Doc(doc_id, self._goals.get(doc_id))


class _Client:
    def __init__(self, goals):
        self._goals = goals

    def collection(self, _name):
        return self

    def document(self, _doc_id):
        return SimpleNamespace(collection=lambda _name: _Goals(self._goals))


def _goal(title):
    return {'title': title, 'status': 'focused', 'is_active': True, 'current_value': 1, 'target_value': 10}


def _stub_goals(monkeypatch, goals, reply='Ship the landing page this week.'):
    prompts = []
    monkeypatch.setattr(goals_db, '_get_db', lambda firestore_client=None: _Client(goals))
    monkeypatch.setattr(
        llm_goals,
        '_get_goal_context',
        lambda *_a: {'conversation_context': '', 'chat_context': '', 'memory_context': ''},
    )
    monkeypatch.setattr(llm_goals, 'track_usage', lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(
        llm_goals,
        'get_llm',
        lambda _name: SimpleNamespace(invoke=lambda prompt: prompts.append(prompt) or SimpleNamespace(content=reply)),
    )
    return prompts


def test_advice_is_generated_for_an_active_goal_past_the_first_three(monkeypatch):
    prompts = _stub_goals(
        monkeypatch,
        {
            'goal_a': _goal('Read 12 books'),
            'goal_b': _goal('Run a 10k'),
            'goal_c': _goal('Learn Spanish'),
            'goal_d': _goal('Launch the side project'),
        },
    )

    advice = llm_goals.get_goal_advice('u1', 'goal_d')

    assert advice == 'Ship the landing page this week.'
    assert 'Launch the side project' in prompts[0]


def test_advice_for_an_achieved_goal_still_falls_back(monkeypatch):
    prompts = _stub_goals(monkeypatch, {'goal_a': {**_goal('Run a 10k'), 'status': 'achieved', 'is_active': False}})

    assert llm_goals.get_goal_advice('u1', 'goal_a') == 'Focus on the next small step toward your goal.'
    assert prompts == []


def test_progress_is_saved_for_an_active_goal_past_the_first_three(monkeypatch):
    _stub_goals(
        monkeypatch,
        {
            'goal_a': _goal('Read 12 books'),
            'goal_b': _goal('Run a 10k'),
            'goal_c': _goal('Learn Spanish'),
            'goal_d': _goal('Save 10000 dollars'),
        },
        reply='[{"goal_id": "goal_d", "found": true, "value": 2500}]',
    )
    saved = []
    monkeypatch.setattr(goals_db, 'update_goal_progress', lambda _uid, goal_id, value: saved.append((goal_id, value)))

    result = llm_goals.extract_and_update_goal_progress('u1', 'I have saved 2500 dollars so far')

    assert result['status'] == 'updated'
    assert saved == [('goal_d', 2500.0)]
