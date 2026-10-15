"""Decision coverage for lifecycle boundaries outside normal model assessment."""

from types import SimpleNamespace

import pytest

from utils.conversations.terminal_relevance import TERMINAL_PATHS, terminal_decision, valid_decision
from database import conversation_terminal_title as terminal


@pytest.mark.parametrize('path', sorted(TERMINAL_PATHS))
@pytest.mark.parametrize(
    'text,verdict,tier',
    [
        ('Huh?', 'discard', 'rule'),
        ('Remind me to call mom tomorrow', 'keep', 'rule'),
        ('Avocado sauce and jelly', 'keep', 'policy'),
        ('', 'discard', 'rule'),
    ],
)
def test_all_paths_have_total_rules_or_named_policy(path, text, verdict, tier):
    decision = terminal_decision(
        {'source': 'omi'}, path=path, texts=[text], decoded=True, assess=True, calendar_retains=lambda: False
    )
    assert valid_decision(decision)
    assert (decision['verdict'], decision['decided_by']) == (verdict, tier)
    assert decision['trigger'] == path


@pytest.mark.parametrize(
    'row',
    [
        {'has_photos': True},
        {'photos': [{'description': ''}]},
        {'sync_relevance_user_kept': True},
        {'user_title': 'My note'},
    ],
)
def test_protected_rows_never_discard(row):
    decision = terminal_decision(
        {'source': 'omi', **row},
        path='dead_letter',
        texts=['Huh?'],
        decoded=True,
        assess=True,
        calendar_retains=lambda: False,
    )
    assert decision['verdict'] == 'keep'


@pytest.mark.parametrize('calendar', [lambda: True, None])
def test_calendar_or_unavailable_calendar_keeps(calendar):
    decision = terminal_decision(
        {'source': 'omi'}, path='dead_letter', texts=['Huh?'], decoded=True, assess=True, calendar_retains=calendar
    )
    assert decision['verdict'] == 'keep'


def test_calendar_error_keeps():
    def broken():
        raise RuntimeError('unavailable')

    assert (
        terminal_decision(
            {'source': 'omi'}, path='dead_letter', texts=['Huh?'], decoded=True, assess=True, calendar_retains=broken
        )['verdict']
        == 'keep'
    )


def test_existing_rule_keep_survives_even_empty_current_transcript():
    prior = {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'explicit_reminder', 'trigger': 'capture_end'}
    assert (
        terminal_decision(
            {'relevance_decision': prior},
            path='dead_letter',
            texts=[],
            decoded=True,
            assess=True,
            calendar_retains=lambda: False,
        )
        == prior
    )


def test_unreadable_transcript_is_never_silence():
    assert (
        terminal_decision(
            {'source': 'omi'}, path='dead_letter', decoded=False, assess=True, calendar_retains=lambda: False
        )['verdict']
        == 'keep'
    )


def test_user_discard_stays_discarded():
    assert (
        terminal_decision(
            {'discarded': True}, path='dead_letter', texts=['Remind me to call mom'], decoded=True, assess=True
        )['verdict']
        == 'discard'
    )


def test_wake_word_stays_on_keep_policy():
    decision = terminal_decision(
        {'source': 'omi'}, path='dead_letter', texts=['Omi'], decoded=True, assess=True, calendar_retains=lambda: False
    )
    assert decision['verdict'] == 'keep'
    assert decision['decided_by'] == 'policy'


@pytest.mark.parametrize(
    'bad',
    [
        {},
        None,
        {'verdict': 'keep'},
        {'verdict': 'keep', 'decided_by': 'invented', 'reason': 'junk', 'trigger': 'capture_end'},
    ],
)
def test_invalid_records_are_replaced(bad):
    assert valid_decision(terminal_decision({'relevance_decision': bad}, path='dead_letter'))


@pytest.mark.parametrize(
    'text,verdict,tier',
    [
        ('Huh?', 'discard', 'rule'),
        ('Remind me to call mom', 'keep', 'rule'),
        ('Avocado sauce and jelly', 'keep', 'policy'),
    ],
)
def test_huh_completed_dead_letter_empty_decision_snapshot(monkeypatch, text, verdict, tier):
    row = {
        'source': 'omi',
        'id': 'ed296267-e37a-492c-9ce4-1abbb59c7f87',
        'status': 'completed',
        'discarded': False,
        'finalization_status': 'dead_letter',
        'relevance_decision': {},
        'structured': {'title': 'Huh?'},
        'transcript_segments': [{'text': text}],
    }
    monkeypatch.setattr(terminal, 'calendar_retains', lambda *_: False)
    monkeypatch.setattr(terminal, '_has_described_photo', lambda *_, **__: False)
    ref = SimpleNamespace(path='users/u/conversations/c')
    patch = terminal.dead_letter_conversation_updates('u', row, ref, object(), 'processing_failed', None)
    assert patch['relevance_decision']['verdict'] == verdict
    assert patch['relevance_decision']['decided_by'] == tier
    assert patch['discarded'] == (verdict == 'discard')


def test_decision_metrics_have_distinct_terminal_labels():
    from utils.metrics import CONVERSATION_RELEVANCE_DECISION_TOTAL, record_conversation_relevance

    for path in TERMINAL_PATHS:
        decision = terminal_decision({'source': 'omi'}, path=path)
        labels = {key: decision[key] for key in ('trigger', 'verdict', 'decided_by', 'reason')}
        counter = CONVERSATION_RELEVANCE_DECISION_TOTAL.labels(**labels)
        before = counter._value.get()
        record_conversation_relevance(**labels)
        assert counter._value.get() == before + 1


def test_new_rules_do_not_change_server_recovery_policy():
    from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger, RelevancePolicy

    assert PROCESSING_MODES[ProcessingTrigger.SERVER_RECOVERY].relevance is RelevancePolicy.KEEP


@pytest.mark.parametrize(
    'mode,expected', [('no_overlap', False), ('provider_error', None), ('missing_token', None), ('truncated', None)]
)
def test_real_terminal_calendar_probe_distinguishes_unavailable_evidence(monkeypatch, mode, expected):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock
    from database import calendar_meetings, users
    from utils.conversations import calendar_linking
    from utils.conversations.terminal_calendar import calendar_retains

    monkeypatch.setattr(calendar_meetings, 'get_meetings_in_time_range', lambda *_: [])
    integration = {'connected': True, 'access_token': 'test-token'}
    if mode == 'missing_token':
        integration.pop('access_token')
    monkeypatch.setattr(users, 'get_integration', lambda *_: integration)
    fetch = AsyncMock(return_value=[{}] * 20 if mode == 'truncated' else [])
    if mode == 'provider_error':
        fetch.side_effect = RuntimeError('calendar unavailable')
    monkeypatch.setattr(calendar_linking, 'get_google_calendar_events', fetch)
    now = datetime.now(timezone.utc)
    row = {'source': 'omi', 'started_at': now, 'finished_at': now + timedelta(minutes=1)}
    if mode == 'provider_error':
        with pytest.raises(RuntimeError):
            calendar_retains('u', row)
    else:
        assert calendar_retains('u', row) is expected
    decision = terminal_decision(
        {'source': 'omi', **row},
        path='dead_letter',
        texts=['Huh?'],
        decoded=True,
        assess=True,
        calendar_retains=lambda: calendar_retains('u', row),
    )
    assert decision['verdict'] == ('discard' if mode == 'no_overlap' else 'keep')


@pytest.mark.parametrize(
    'source', ['workflow', 'external_integration', 'openglass', 'screenpipe', 'onboarding', 'unknown', None]
)
def test_non_audio_terminal_never_infers_silence_from_other_content(source):
    decision = terminal_decision(
        {'source': source}, path='dead_letter', texts=[], decoded=True, assess=True, calendar_retains=lambda: False
    )
    assert decision['verdict'] == 'keep'
    assert decision['decided_by'] == 'policy'
