"""A developer webhook's proactive-notification payload with explicit-null optional fields must not
crash the processor.

`{"notification": {"prompt": null}}` passes the earlier `Mapping`/empty guards, then `len(None)`
raised `TypeError`; the dispatch boundary's `except Exception: pass` swallowed it and silently
dropped the notification every run (the same silent drop the file already documents for absent
payloads). Same for `params: null`/non-string elements and `context: null` / non-mapping / null
nested filters.
"""

import contextlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from utils import app_integrations

MESSAGE = 'A proper notification'


def _stub_app():
    app = MagicMock()
    app.id = 'app-1'
    app.name = 'Test App'
    app.has_capability.return_value = True
    # Mirror the real method: membership in a `Set[str]` hashes each element, so an unhashable
    # element (e.g. a nested list) raises there exactly as it does in production.
    scopes = {'user_name', 'user_facts', 'user_context', 'user_chat'}
    app.filter_proactive_notification_scopes.side_effect = lambda params: [p for p in params if p in scopes]
    return app


def _process(payload, *, content=''):
    app = _stub_app()
    with patch.object(app_integrations, '_hit_proactive_notification_rate_limits', return_value=False), patch.object(
        app_integrations, '_proactive_daily_cap_reached', return_value=False
    ), patch.object(app_integrations, 'get_prompt_memories', return_value=('Name', {})), patch.object(
        app_integrations, 'track_usage', return_value=contextlib.nullcontext()
    ), patch.object(
        app_integrations, 'query_vectors_by_metadata', return_value=[]
    ) as query, patch.object(
        app_integrations.conversations_db, 'get_conversations_by_id', return_value=[]
    ), patch.object(
        app_integrations, 'send_app_notification'
    ) as send, patch.object(
        app_integrations, '_set_proactive_noti_sent_at'
    ), patch.object(
        app_integrations, 'incr_daily_notification_count'
    ), patch.object(
        app_integrations, '_user_day_zone', return_value='UTC'
    ), patch.object(
        app_integrations, 'get_llm'
    ) as get_llm:
        get_llm.return_value.invoke.return_value.content = content
        result = app_integrations._process_proactive_notification('uid-1', app, payload)
    return SimpleNamespace(result=result, get_llm=get_llm, send=send, query=query)


def test_explicit_null_prompt_is_treated_as_absent():
    out = _process({'prompt': None}, content='')
    assert out.result is None
    out.get_llm.return_value.invoke.assert_called_once_with('')


def test_non_string_prompt_is_treated_as_absent():
    out = _process({'prompt': 123}, content='')
    assert out.result is None
    out.get_llm.return_value.invoke.assert_called_once_with('')


def test_explicit_null_params_still_processes_the_prompt():
    out = _process({'prompt': 'hello', 'params': None}, content=MESSAGE)
    out.get_llm.return_value.invoke.assert_called_once_with('hello')
    assert out.result == MESSAGE
    out.send.assert_called_once()


def test_non_string_params_are_ignored():
    out = _process({'prompt': 'hello', 'params': [['user_context'], 5, 'user_name']}, content=MESSAGE)
    out.get_llm.return_value.invoke.assert_called_once_with('hello')
    assert out.result == MESSAGE


def test_explicit_null_context_still_processes_the_prompt():
    out = _process({'prompt': 'hello', 'params': ['user_context'], 'context': None}, content=MESSAGE)
    out.get_llm.return_value.invoke.assert_called_once_with('hello')
    assert out.result == MESSAGE


def test_non_mapping_context_still_processes_the_prompt():
    out = _process({'prompt': 'hello', 'params': ['user_context'], 'context': 'nope'}, content=MESSAGE)
    out.get_llm.return_value.invoke.assert_called_once_with('hello')
    assert out.result == MESSAGE


def test_null_nested_filter_values_are_normalized_to_lists():
    payload = {'prompt': 'hello', 'params': ['user_context'], 'context': {'filters': {'people': None, 'topics': None}}}
    out = _process(payload, content=MESSAGE)
    assert out.result == MESSAGE
    kwargs = out.query.call_args.kwargs
    assert kwargs['people'] == []
    assert kwargs['topics'] == []
    assert kwargs['entities'] == []
    assert kwargs['dates'] == []
