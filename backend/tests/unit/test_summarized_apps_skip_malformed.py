"""A malformed configured summary-app doc must be skipped, not fail the whole conversation.

`get_default_conversation_summarized_apps` builds `App(**app_data)` from each configured summary
app id (Redis list or the `CONVERSATION_SUMMARIZED_APP_IDS` env fallback). A legacy/partial stored
app record raises `ValidationError` there, and `trigger_conversation_apps` only catches
`ExplicitAppSelectionFailedError` — so one malformed configured app id fails processing for every
conversation of that deployment/user. Same class as the chat/app fetch guards (#19584, #19687).
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import utils.conversations.process_conversation as pc

_VALID_APP = {
    'id': 'good',
    'name': 'Summary assistant',
    'category': 'productivity',
    'author': 'omi',
    'description': 'Summarizes conversations',
    'image': '',
    'capabilities': [],
}


def _app_lookup(records):
    def _get(app_id):
        return records.get(app_id)

    return _get


def test_redis_configured_malformed_app_is_skipped(monkeypatch):
    monkeypatch.setattr(pc.redis_db, 'get_conversation_summary_app_ids', lambda: ['good', 'corrupt'])
    monkeypatch.setattr(pc, 'get_app_by_id_db', _app_lookup({'good': dict(_VALID_APP), 'corrupt': {'id': 'corrupt'}}))

    apps = pc.get_default_conversation_summarized_apps()

    assert [a.id for a in apps] == ['good']


def test_env_fallback_skips_malformed_app(monkeypatch):
    monkeypatch.setattr(pc.redis_db, 'get_conversation_summary_app_ids', lambda: [])
    monkeypatch.setenv('CONVERSATION_SUMMARIZED_APP_IDS', 'good,corrupt')
    monkeypatch.setattr(pc, 'get_app_by_id_db', _app_lookup({'good': dict(_VALID_APP), 'corrupt': {'id': 'corrupt'}}))

    apps = pc.get_default_conversation_summarized_apps()

    assert [a.id for a in apps] == ['good']
