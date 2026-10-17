"""#20413 — explicit JSON nulls in a proactive-notification webhook payload.

data.get(k, default) only defaults on a MISSING key — {"prompt": null} used to
hit len()/iteration/.get with a TypeError. The fix coerces null to default.
"""

import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import utils.app_integrations as app_integrations


def _app(scopes=None):
    return SimpleNamespace(
        id='app1',
        name='App',
        has_capability=lambda c: True,
        filter_proactive_notification_scopes=lambda params: params if scopes is None else scopes,
    )


def _open_gates(monkeypatch, llm_text='a long enough notification message'):
    monkeypatch.setattr(app_integrations, '_hit_proactive_notification_rate_limits', lambda *a: False)
    monkeypatch.setattr(app_integrations, '_proactive_daily_cap_reached', lambda *a: False)
    monkeypatch.setattr(app_integrations, 'get_prompt_memories', lambda uid: ('user', []))
    monkeypatch.setattr(app_integrations, '_retrieve_contextual_memories', lambda uid, ctx: [])
    monkeypatch.setattr(app_integrations, 'get_app_messages', lambda *a, **k: [])
    monkeypatch.setattr(app_integrations, 'send_app_notification', lambda *a, **k: None)
    monkeypatch.setattr(app_integrations, '_set_proactive_noti_sent_at', lambda *a: None)
    monkeypatch.setattr(app_integrations, 'incr_daily_notification_count', lambda *a: None)
    monkeypatch.setattr(app_integrations, '_user_day_zone', lambda uid: 'UTC')

    @contextmanager
    def _noop(*a, **k):
        yield

    monkeypatch.setattr(app_integrations, 'track_usage', _noop)
    monkeypatch.setattr(
        app_integrations,
        'get_llm',
        lambda *a, **k: SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content=llm_text)),
    )


def test_explicit_null_prompt_coerces_to_default(monkeypatch):
    _open_gates(monkeypatch)
    # {"prompt": null} previously TypeError'd on len(None); now treated as ''.
    result = app_integrations._process_proactive_notification(
        'u1', _app(), {'prompt': None, 'params': [], 'context': {}}
    )
    assert result == 'a long enough notification message'


def test_explicit_null_params_and_context_dont_crash(monkeypatch):
    _open_gates(monkeypatch)
    result = app_integrations._process_proactive_notification(
        'u1', _app(), {'prompt': 'Tell the user something useful.', 'params': None, 'context': None}
    )
    assert result == 'a long enough notification message'


def test_all_nullable_fields_none(monkeypatch):
    _open_gates(monkeypatch)
    result = app_integrations._process_proactive_notification(
        'u1', _app(), {'prompt': None, 'params': None, 'context': None}
    )
    assert result is not None


def test_non_mapping_payload_rejected_not_crashed(monkeypatch):
    _open_gates(monkeypatch)
    for bad in ('raw string', 42, [1, 2]):
        assert app_integrations._process_proactive_notification('u1', _app(), bad) is None


def test_missing_keys_still_work(monkeypatch):
    _open_gates(monkeypatch)
    assert app_integrations._process_proactive_notification('u1', _app(), {'prompt': 'Valid prompt text.'}) is not None


def test_retrieve_contextual_memories_tolerates_null_and_malformed_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(app_integrations, 'generate_embedding', lambda text: [1.0] * 3072)

    def _fake_query(uid, vector, *, dates_filter, people, topics, entities, dates):
        captured['uid'] = uid
        captured['vector_head'] = vector[0]
        captured['people'] = people
        captured['topics'] = topics
        captured['entities'] = entities
        captured['dates'] = dates
        return ['c1']

    monkeypatch.setattr(app_integrations, 'query_vectors_by_metadata', _fake_query)
    monkeypatch.setattr(
        app_integrations.conversations_db,
        'get_conversations_by_id',
        lambda uid, ids: [{'id': 'c1', 'is_locked': False}, {'id': 'c2', 'is_locked': True}],
    )

    # Explicit null `filters` previously raised AttributeError on `None.get("people", [])`.
    convos = app_integrations._retrieve_contextual_memories('u1', {'question': 'What happened?', 'filters': None})
    assert [c['id'] for c in convos] == ['c1']
    assert captured['vector_head'] == 1.0
    assert captured['people'] == []
    assert captured['topics'] == []
    assert captured['entities'] == []
    assert captured['dates'] == []

    # Explicit null or mixed-type filter lists coerce to list[str] instead of passing None to Pinecone `$in`.
    app_integrations._retrieve_contextual_memories(
        'u1',
        {
            'question': None,
            'filters': {
                'people': None,
                'topics': ['work', None, 42],
                'entities': 'not-a-list',
                'dates': None,
            },
        },
    )
    assert captured['vector_head'] == 0.0
    assert captured['people'] == []
    assert captured['topics'] == ['work']
    assert captured['entities'] == []
    assert captured['dates'] == []

    # Non-mapping context or non-string question degrades cleanly without raising.
    app_integrations._retrieve_contextual_memories('u1', 'not-a-mapping')
    app_integrations._retrieve_contextual_memories('u1', {'question': 123, 'filters': ['not-a-mapping']})


def test_proactive_notification_real_retrieve_contextual_memories_null_filters(monkeypatch):
    real_retrieve = app_integrations._retrieve_contextual_memories
    _open_gates(monkeypatch)
    monkeypatch.setattr(app_integrations, '_retrieve_contextual_memories', real_retrieve)
    monkeypatch.setattr(app_integrations, 'generate_embedding', lambda text: [0.5] * 3072)
    monkeypatch.setattr(app_integrations, 'query_vectors_by_metadata', lambda *a, **k: [])
    monkeypatch.setattr(app_integrations.conversations_db, 'get_conversations_by_id', lambda uid, ids: [])

    result = app_integrations._process_proactive_notification(
        'u1',
        _app(scopes=['user_context']),
        {
            'prompt': 'Summarize {{user_context}}',
            'params': ['user_context'],
            'context': {'question': 'What did we decide?', 'filters': None},
        },
    )
    assert result == 'a long enough notification message'


def test_wrong_typed_prompt_params_and_context_do_not_crash(monkeypatch):
    _open_gates(monkeypatch)
    app = SimpleNamespace(
        id='app1',
        name='App',
        has_capability=lambda c: True,
        filter_proactive_notification_scopes=lambda params: [
            p for p in params if p in {'user_name', 'user_facts', 'user_context', 'user_chat'}
        ],
    )
    for payload in (
        {'prompt': 12345, 'params': 'user_name', 'context': 'bad-context'},
        {'prompt': ['list-prompt'], 'params': 99, 'context': [1, 2]},
        {'prompt': 'Hello {{user_name}}', 'params': ['user_name', None, 42], 'context': None},
    ):
        result = app_integrations._process_proactive_notification('u1', app, payload)
        assert result == 'a long enough notification message'


def test_trigger_external_integrations_ignores_non_string_message_without_aborting_sibling_apps(monkeypatch):
    import asyncio

    async def _run_blocking_inline(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    class _DummyAsyncCM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    app_bad = SimpleNamespace(
        id='app-bad',
        uid='dev1',
        enabled=True,
        triggers_on_conversation_creation=lambda: True,
        external_integration=SimpleNamespace(webhook_url='https://example.com/bad'),
    )
    app_good = SimpleNamespace(
        id='app-good',
        uid='dev1',
        enabled=True,
        triggers_on_conversation_creation=lambda: True,
        external_integration=SimpleNamespace(webhook_url='https://example.com/good'),
    )

    responses = {
        'https://example.com/bad?uid=u1': SimpleNamespace(
            status_code=200, text='{}', json=lambda: {'message': {'text': 'non-string-dict'}}
        ),
        'https://example.com/good?uid=u1': SimpleNamespace(
            status_code=200, text='{}', json=lambda: {'message': 'Valid app summary'}
        ),
    }

    class _Client:
        async def post(self, url, **kwargs):
            return responses[url]

    monkeypatch.setattr(app_integrations, 'run_blocking', _run_blocking_inline)
    monkeypatch.setattr(app_integrations, 'get_available_apps', lambda uid: [app_bad, app_good])
    monkeypatch.setattr(app_integrations, 'is_app_webhook_disabled', lambda app_id: False)
    monkeypatch.setattr(app_integrations, 'conversation_to_dict', lambda c: {'id': c.id})
    monkeypatch.setattr(app_integrations, 'redact_conversation_for_integration', lambda d: d)
    monkeypatch.setattr(app_integrations, 'serialize_datetimes', lambda d: d)
    monkeypatch.setattr(
        app_integrations,
        'safe_request_target',
        lambda url: (url, {'headers': {}, 'extensions': {}}),
    )
    monkeypatch.setattr(
        app_integrations,
        'get_webhook_circuit_breaker',
        lambda url: SimpleNamespace(
            allow_request=lambda: True, record_success=lambda: None, record_failure=lambda: None
        ),
    )
    monkeypatch.setattr(app_integrations, 'get_webhook_semaphore', lambda: _DummyAsyncCM())
    monkeypatch.setattr(app_integrations, 'get_webhook_client', lambda: _Client())
    monkeypatch.setattr(app_integrations, 'record_app_webhook_success', lambda app_id: None)
    monkeypatch.setattr(app_integrations, 'record_app_usage', lambda *a, **k: None)

    persisted = []

    def _strict_add_app_message(message, app_id, uid, conversation_id=None):
        if not isinstance(message, str):
            raise TypeError(f'Message.text must be str, got {type(message).__name__}')
        persisted.append((app_id, message))
        return f'{app_id}:{message}'

    monkeypatch.setattr(app_integrations, 'add_app_message', _strict_add_app_message)

    convo = SimpleNamespace(id='conv1', discarded=False, is_locked=False, source='omi', client_platform=None)
    out = asyncio.run(app_integrations.trigger_external_integrations('u1', convo))
    assert out == ['app-good:Valid app summary']
    assert persisted == [('app-good', 'Valid app summary')]


def test_realtime_integrations_non_string_message_does_not_drop_proactive_notification(monkeypatch):
    import asyncio

    async def _run_blocking_inline(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    class _DummyAsyncCM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    @contextmanager
    def _noop(*a, **k):
        yield

    app = SimpleNamespace(
        id='app-rt',
        name='RealtimeApp',
        uid='dev1',
        enabled=True,
        triggers_realtime=lambda: True,
        has_capability=lambda cap: cap == 'proactive_notification',
        external_integration=SimpleNamespace(webhook_url='https://example.com/rt'),
    )

    class _Client:
        async def post(self, url, **kwargs):
            # Integer `message` previously raised TypeError on `len(message) > 5` before
            # reaching the `notification` block, silently dropping the proactive notification.
            return SimpleNamespace(
                status_code=200,
                text='{}',
                json=lambda: {
                    'message': 123456,
                    'notification': {'prompt': 'Notify the user', 'params': []},
                },
            )

    monkeypatch.setattr(app_integrations, 'run_blocking', _run_blocking_inline)
    monkeypatch.setattr(app_integrations, 'is_trial_paywalled', lambda uid, source: False)
    monkeypatch.setattr(app_integrations, 'get_available_apps', lambda uid: [app])
    monkeypatch.setattr(app_integrations, 'is_app_webhook_disabled', lambda app_id: False)
    monkeypatch.setattr(
        app_integrations,
        'safe_request_target',
        lambda url: (url, {'headers': {}, 'extensions': {}}),
    )
    monkeypatch.setattr(
        app_integrations,
        'get_webhook_circuit_breaker',
        lambda url: SimpleNamespace(
            allow_request=lambda: True, record_success=lambda: None, record_failure=lambda: None
        ),
    )
    monkeypatch.setattr(app_integrations, 'get_webhook_semaphore', lambda: _DummyAsyncCM())
    monkeypatch.setattr(app_integrations, 'get_webhook_client', lambda: _Client())
    monkeypatch.setattr(app_integrations, 'record_app_webhook_success', lambda app_id: None)
    monkeypatch.setattr(app_integrations, 'record_app_usage', lambda *a, **k: None)
    monkeypatch.setattr(app_integrations, 'track_usage', _noop)
    monkeypatch.setattr(
        app_integrations,
        '_process_proactive_notification',
        lambda uid, a, notif: 'proactive notification delivered',
    )
    monkeypatch.setattr(app_integrations, 'add_app_message', lambda msg, app_id, uid: f'{app_id}:{msg}')
    monkeypatch.setattr(app_integrations.redis_db, 'publish_proactive_message', lambda *a, **k: None)

    out = asyncio.run(app_integrations._async_trigger_realtime_integrations('u1', [], 'conv1'))
    assert out == ['app-rt:proactive notification delivered']
