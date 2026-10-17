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
