"""Owner-decision telemetry on Dream changes and the low-volume Undo backstop."""

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from config.dream_agent import Caps
from database import dream_store
from utils import dream_telemetry

NOW = datetime.now(timezone.utc)


def _rows(*rows):
    query = SimpleNamespace()
    query.where = lambda **kw: query
    query.order_by = lambda *a, **kw: query
    query.limit = lambda n: query
    query.stream = lambda: iter([SimpleNamespace(to_dict=lambda row=row: row) for row in rows])
    return SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda uid: SimpleNamespace(collection=lambda name: query))
    )


def _change(kind, *, undone, days_ago):
    return {
        'edit_key': f'agent:{kind}:synthetic',
        'phase': 'applied',
        'created_at': NOW - timedelta(days=days_ago),
        'change': {'undone': undone},
    }


def _demoted(monkeypatch, *rows, **caps):
    monkeypatch.setattr(dream_store, '_review_store', lambda: SimpleNamespace(decode_doc=lambda uid, row: row))
    return dream_store.demoted_types('synthetic-owner', Caps(**caps), firestore_client=_rows(*rows))


def test_three_recent_undos_pause_a_kind_below_the_sample_floor(monkeypatch):
    rows = [_change('dismiss_person', undone=True, days_ago=day) for day in (1, 2, 3)]
    assert _demoted(monkeypatch, *rows) == {'dismiss_person'}


def test_two_recent_undos_or_three_old_ones_do_not(monkeypatch):
    recent = [_change('dismiss_person', undone=True, days_ago=day) for day in (1, 2)]
    old = [_change('merge_people', undone=True, days_ago=day) for day in (10, 12, 14)]
    assert _demoted(monkeypatch, *recent, *old) == set()


def test_rate_rule_still_demotes_at_the_sample_floor(monkeypatch):
    rows = [_change('spelling', undone=index < 3, days_ago=20) for index in range(10)]
    assert _demoted(monkeypatch, *rows) == {'spelling'}
    assert _demoted(monkeypatch, *rows, undo_recent_count=1, undo_recent_days=7) == {'spelling'}


def test_recent_backstop_is_configurable(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_UNDO_RECENT_COUNT', '5')
    monkeypatch.setenv('DREAM_AGENT_UNDO_RECENT_DAYS', '14')
    caps = Caps.from_env()
    assert (caps.undo_recent_count, caps.undo_recent_days) == (5, 14)
    monkeypatch.setenv('DREAM_AGENT_UNDO_RECENT_COUNT', '0')
    assert Caps.from_env().undo_recent_count == 1


def test_outcome_record_is_bounded_and_content_free():
    payload = dream_telemetry.outcome_payload('dismiss_person', 'undo', applied_at=NOW - timedelta(hours=3), now=NOW)
    assert payload == {'event': 'dream_outcome', 'kind': 'dismiss_person', 'decision': 'undo', 'age': 'lt1d'}
    odd = dream_telemetry.outcome_payload('people/abc Anna', 'something', applied_at='yesterday', now=NOW)
    assert odd == {'event': 'dream_outcome', 'kind': 'other', 'decision': 'other', 'age': 'none'}
    ages = [
        dream_telemetry.outcome_payload('spelling', 'redo', applied_at=NOW - timedelta(days=d), now=NOW)['age']
        for d in (0.5, 3, 20, 40)
    ]
    assert ages == ['lt1d', 'lt7d', 'lt30d', 'gte30d']


def test_dream_kind_reads_only_dream_edit_keys():
    assert dream_telemetry.dream_kind('agent:merge_people:abc') == 'merge_people'
    assert dream_telemetry.dream_kind('dream:spelling:abc') == 'spelling'
    assert dream_telemetry.dream_kind('user:spelling:abc') is None
    assert dream_telemetry.dream_kind(None) is None


def test_record_outcome_emits_one_json_line(caplog):
    with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
        dream_telemetry.record_outcome('merge_people', 'accept')
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.getMessage().startswith('{')]
    assert lines == [{'event': 'dream_outcome', 'kind': 'merge_people', 'decision': 'accept', 'age': 'none'}]


def test_pass_record_carries_bounded_verifier_outcomes_by_kind():
    payload = dream_telemetry.pass_payload(
        {
            'status': 'complete',
            'verifier_by_kind': {'dismiss_person': {'agree': 3, 'unverified': 1}, 'people/x': {'agree': 1}},
        }
    )
    assert payload['verifier_by_kind'] == {'dismiss_person': {'agree': 3, 'unverified': 1}, 'other': {'agree': 1}}
