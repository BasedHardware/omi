"""The canned quota reply names the window the 402 detail carries (FREE_CHAT_QUESTIONS_PER_DAY)."""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import utils.chat_turn as chat_turn  # noqa: E402
from models.chat import SendMessageRequest  # noqa: E402

_MONTH_RESET = 1793491200  # 2026-11-01T00:00:00Z
_DAY_RESET = 1792713600  # 2026-10-23T00:00:00Z


def _reply(monkeypatch, detail):
    persisted = []
    monkeypatch.setattr(chat_turn, '_persist_message', lambda uid, payload: persisted.append(payload))
    monkeypatch.setattr(chat_turn.chat_db, 'add_message_to_chat_session', lambda *a, **k: None, raising=False)
    reply = chat_turn._build_quota_exceeded_reply('uid', SendMessageRequest(text='hi'), None, detail)
    return reply.text


def test_daily_window_copy(monkeypatch):
    text = _reply(
        monkeypatch,
        {
            'error': 'quota_exceeded',
            'plan': 'Free',
            'plan_type': 'basic',
            'unit': 'questions',
            'used': 2,
            'limit': 2.0,
            'reset_at': _DAY_RESET,
            'period': 'day',
            'resets_at': '2026-10-23T00:00:00+00:00',
        },
    )
    assert 'your 2 daily chat question limit on the Free plan' in text
    assert 'resets at midnight UTC' in text
    assert 'monthly' not in text


def test_monthly_copy_is_unchanged(monkeypatch):
    text = _reply(
        monkeypatch,
        {
            'error': 'quota_exceeded',
            'plan': 'Free',
            'plan_type': 'basic',
            'unit': 'questions',
            'used': 30,
            'limit': 30.0,
            'reset_at': _MONTH_RESET,
        },
    )
    assert 'your 30 monthly chat question limit on the Free plan' in text
    assert 'Your limit resets on November 1.' in text
