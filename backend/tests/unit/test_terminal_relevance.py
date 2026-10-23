"""Decision coverage for lifecycle boundaries outside normal model assessment."""

from types import SimpleNamespace

import pytest

from utils.conversation_relevance_labels import TERMINAL_PATHS
from utils.conversations.terminal_relevance import terminal_decision, valid_decision
from database import conversation_terminal_title as terminal


def test_current_processing_triggers_preserve_valid_prior_decisions():
    from utils.conversations.processing_trigger import ProcessingTrigger

    for trigger in ProcessingTrigger:
        prior = dict(verdict='keep', decided_by='policy', reason=trigger.value, trigger=trigger.value)
        assert valid_decision(prior)
        assert terminal_decision({'relevance_decision': prior}, path='lifecycle_terminal') == prior


@pytest.mark.parametrize(
    'path,assess',
    sorted(
        (path, path in {'dead_letter', 'byok_abandoned', 'orphan_terminal', 'oversized_terminal'})
        for path in TERMINAL_PATHS
    ),
)
@pytest.mark.parametrize(
    'text,verdict,tier',
    [
        ('Huh?', 'discard', 'rule'),
        ('Remind me to call mom tomorrow', 'keep', 'rule'),
        ('Avocado sauce and jelly', 'keep', 'policy'),
        ('', 'discard', 'rule'),
    ],
)
def test_all_paths_have_total_rules_or_named_policy(path, assess, text, verdict, tier):
    decision = terminal_decision(
        {'source': 'omi'}, path=path, texts=[text], decoded=True, assess=assess, calendar_retains=lambda: False
    )
    assert valid_decision(decision)
    expected = (verdict, tier) if assess else ('keep', 'user' if path == 'user_restore' else 'policy')
    assert (decision['verdict'], decision['decided_by']) == expected
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
    patch = terminal.dead_letter_conversation_updates(
        'u', row, ref, object(), 'processing_failed', None, lambda _: False
    )
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
    'source', ['workflow', 'external_integration', 'openglass', 'screenpipe', 'onboarding', 'unknown', None, {}, []]
)
def test_non_audio_terminal_never_infers_silence_from_other_content(source):
    decision = terminal_decision(
        {'source': source}, path='dead_letter', texts=[], decoded=True, assess=True, calendar_retains=lambda: False
    )
    assert decision['verdict'] == 'keep'
    assert decision['decided_by'] == 'policy'


@pytest.mark.parametrize(
    'prior,tier,reason',
    [
        ({'verdict': 'keep', 'decided_by': 'rule', 'reason': 'explicit_reminder'}, 'rule', 'explicit_reminder'),
        ({'verdict': 'keep', 'decided_by': 'rule'}, 'rule', 'prior_rule_keep'),
        ({'verdict': 'keep', 'decided_by': 'rule', 'reason': []}, 'rule', 'prior_rule_keep'),
        ({'verdict': 'keep', 'reason': 'calendar_overlap'}, 'override', 'calendar_overlap'),
        ({'verdict': 'keep'}, 'policy', 'prior_keep'),
    ],
)
def test_incomplete_prior_keeps_are_repaired_without_reversal(prior, tier, reason):
    row = {'source': 'omi', 'discarded': False, 'relevance_decision': prior}
    decision = terminal_decision(
        row, path='dead_letter', texts=['Huh?'], decoded=True, assess=True, calendar_retains=lambda: False
    )
    assert valid_decision(decision)
    assert (decision['verdict'], decision['decided_by'], decision['reason']) == ('keep', tier, reason)
    # Explicit user discard still outranks even prior positive evidence.
    row['discarded'] = True
    assert terminal_decision(row, path='dead_letter')['verdict'] == 'discard'


@pytest.mark.parametrize('reason', ['prior_keep', 'prior_rule_keep'])
def test_repaired_prior_keep_reasons_have_distinct_metric_labels(reason):
    from utils.metrics import CONVERSATION_RELEVANCE_DECISION_TOTAL, record_conversation_relevance

    labels = dict(trigger='dead_letter', verdict='keep', decided_by='policy', reason=reason)
    counter = CONVERSATION_RELEVANCE_DECISION_TOTAL.labels(**labels)
    before = counter._value.get()
    record_conversation_relevance(**labels)
    assert counter._value.get() == before + 1


@pytest.mark.parametrize('restored', [False, True])
def test_incomplete_recovery_keep_retains_capture_preservation_provenance(restored):
    row = {
        'relevance_decision': {'trigger': 'server_recovery', 'verdict': 'keep'},
        'sync_relevance_user_kept': restored,
    }
    decision = terminal_decision(row, path='lifecycle_terminal')
    assert valid_decision(decision)
    assert decision['trigger'] == 'server_recovery'
    assert decision['verdict'] == 'keep'


@pytest.mark.parametrize('verdict', ['keep', 'discard'])
@pytest.mark.parametrize('discarded', [False, True])
def test_valid_prior_verdict_survives_flag_mismatch(verdict, discarded):
    prior = dict(verdict=verdict, decided_by='rule', reason='filler_only', trigger='capture_end')
    assert terminal_decision({'relevance_decision': prior, 'discarded': discarded}, path='lifecycle_terminal') == prior


@pytest.mark.parametrize('signal', ['sync_relevance_user_kept', 'user_restore'])
def test_only_explicit_restore_replaces_valid_discard(signal):
    prior = dict(verdict='discard', decided_by='rule', reason='filler_only', trigger='capture_end')
    row = {
        'relevance_decision': prior,
        'discarded': False,
        'sync_relevance_user_kept': signal == 'sync_relevance_user_kept',
    }
    decision = terminal_decision(row, path='user_restore' if signal == 'user_restore' else 'lifecycle_terminal')
    assert decision['verdict'] == 'keep'
    assert decision['decided_by'] == 'user'


def test_stamp_never_enables_assessment(monkeypatch):
    from utils.conversations import terminal_relevance

    calls = []
    original = terminal_relevance.terminal_decision

    def spy(row, **kwargs):
        calls.append(kwargs.get('assess', False))
        return original(row, **kwargs)

    monkeypatch.setattr(terminal_relevance, 'terminal_decision', spy)
    for path in TERMINAL_PATHS:
        terminal_relevance.stamp_terminal_decision({'source': 'omi', 'transcript_segments': []}, path=path)
    assert calls == [False] * len(TERMINAL_PATHS)


def test_production_terminal_assessment_call_sites_are_pinned():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    expected = {
        'database/conversations.py': 2,
        'database/conversation_merge_jobs.py': 1,
        'database/conversation_terminal_title.py': 1,
        'utils/task_intelligence/chat_first_fixture_capture.py': 1,
        'utils/conversations/lifecycle.py': 3,
        'utils/sync/assignment.py': 1,
    }
    observed = {}
    for folder in ('database', 'utils'):
        for file in (root / folder).rglob('*.py'):
            if file.name == 'terminal_relevance.py':
                continue
            for call in ast.walk(ast.parse(file.read_text())):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                    continue
                if call.func.id == 'stamp_terminal_decision':
                    relative = str(file.relative_to(root))
                    observed[relative] = observed.get(relative, 0) + 1
                    assert 'assess' not in {kw.arg for kw in call.keywords}
                elif call.func.id == 'terminal_decision':
                    assert str(file.relative_to(root)) == 'database/conversation_terminal_title.py'
                    assert any(
                        kw.arg == 'assess' and isinstance(kw.value, ast.Constant) and kw.value.value is True
                        for kw in call.keywords
                    )
    assert observed == expected
