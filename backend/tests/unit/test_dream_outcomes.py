"""Owner-decision telemetry on Dream changes and the low-volume Undo backstop."""

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from config.dream_agent import Caps
from database import dream_store
from tests.unit.test_dream_harness_runtime import runtime, store  # noqa: F401  (fixtures)
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


# --- review fixes -------------------------------------------------------------------------------


def _journal(edit_key, edit_kind, *, undone=True, days_ago=1):
    return {
        'edit_key': edit_key,
        'phase': 'applied',
        'created_at': NOW - timedelta(days=days_ago),
        'change': {'undone': undone, 'edit_kind': edit_kind},
    }


def test_demotion_uses_the_policy_kind_not_the_key_segment(monkeypatch):
    # Memory-target spelling keys use 'memory'; accepted proposals are re-keyed 'agent:user:'.
    spelling = [_journal('agent:memory:synthetic', 'spelling', days_ago=day) for day in (1, 2, 3)]
    accepted = [_journal('agent:user:synthetic', 'merge_people', days_ago=day) for day in (1, 2, 3)]
    assert _demoted(monkeypatch, *spelling, *accepted) == {'spelling', 'merge_people'}


def test_change_kind_prefers_edit_kind_and_ignores_non_dream_changes():
    assert dream_telemetry.change_kind(_journal('agent:user:x', 'merge_people')) == 'merge_people'
    assert dream_telemetry.change_kind({'edit_key': 'agent:spelling:x', 'change': {}}) == 'spelling'
    assert dream_telemetry.change_kind(_journal('user:edit:x', 'spelling')) is None
    assert dream_telemetry.change_kind(None) is None


def test_record_outcome_never_raises_even_when_error_accounting_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(dream_telemetry, 'outcome_payload', boom)
    monkeypatch.setattr(dream_telemetry, 'ERRORS', SimpleNamespace(labels=boom))
    dream_telemetry.record_outcome('spelling', 'undo')


def test_accepting_an_already_present_vocabulary_proposal_counts_as_an_accept(monkeypatch):
    from utils.agent_capabilities import tools

    seen = []
    monkeypatch.setattr(tools, 'revalidate_proposal', lambda uid, source: {})
    monkeypatch.setattr(tools, 'apply_vocabulary', lambda *a, **kw: 'unchanged')
    monkeypatch.setattr(dream_telemetry, 'record_outcome', lambda kind, decision, **kw: seen.append((kind, decision)))
    proposal = SimpleNamespace(operation=None, edit=None, vocabulary=object())
    assert tools.answer_proposal('synthetic-owner', proposal, {'edit_key': 'agent:vocabulary:x'}, 'accept') is False
    assert seen == [('vocabulary', 'accept')]


def test_dismiss_records_the_proposal_kind(monkeypatch):
    from utils.agent_capabilities import tools

    seen = []
    monkeypatch.setattr(tools.review_changes, 'suppress_agent_change', lambda uid, key: None)
    monkeypatch.setattr(dream_telemetry, 'record_outcome', lambda kind, decision, **kw: seen.append((kind, decision)))
    proposal = SimpleNamespace(operation=SimpleNamespace(kind='spelling'), edit=None)
    tools.answer_proposal('synthetic-owner', proposal, {'edit_key': 'agent:memory:x'}, 'dismiss')
    assert seen == [('spelling', 'dismiss')]


def test_undo_redo_of_an_applied_dream_change_each_emit_once(runtime, monkeypatch):
    import asyncio

    import pytest

    from database import review_changes, review_store
    from tests.unit.test_dream_cleanup_edits import UID
    from tests.unit.test_dream_harness_runtime import scripted
    from utils import dream_agent

    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))
    assert report['outcomes'][0]['status'] == 'applied'
    change_id = next(
        review_store.decode_doc(UID, row)['change']['change_id']
        for key, row in runtime.rows.items()
        if key[2:3] == ('review_changes',) and review_store.decode_doc(UID, row)
    )
    seen = []
    monkeypatch.setattr(dream_telemetry, 'record_outcome', lambda kind, decision, **kw: seen.append((kind, decision)))
    review_changes.set_undone(UID, change_id, True)
    review_changes.set_undone(UID, change_id, True)  # unchanged: no second record
    review_changes.set_undone(UID, change_id, False)
    assert seen == [('dismiss_person', 'undo'), ('dismiss_person', 'redo')]
