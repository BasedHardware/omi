"""Experiment ``end_open_conversation``: what End answers once its cut is stored.

Baseline (no stored cut): the answer is whatever the request produced, including the empty listening
recording still in progress that the app reads as "audio not received". With the cut stored, that one
answer becomes the conversation the cut ended, or "accepted, result to come" when none has landed yet.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.conversation import CreateConversationResponse
from models.conversation_enums import ConversationStatus
from utils.conversations.v3 import end_answer

AT = datetime(2026, 11, 24, 21, 52, 36, tzinfo=timezone.utc)


def recording(status):
    """The baseline answer: the listening session's own recording."""
    return SimpleNamespace(conversation=SimpleNamespace(id='socket-recording', status=status), messages=[])


def window(cid='open-conversation'):
    return {
        'id': cid,
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'status': 'in_progress',
        'tile_state': 'live',
        'v3_derived': True,
        'structured': {'title': '', 'overview': ''},
        'transcript_segments': [],
    }


@pytest.fixture
def lookups(monkeypatch):
    asked = []
    state = {'by_id': None, 'active': None}

    def by_id(uid, cid, *, now):
        asked.append(('by_id', uid, cid))
        return state['by_id']

    def active(uid, *, now, max_idle, pick):
        asked.append(('active', uid))
        return state['active']

    monkeypatch.setattr(end_answer.conversations_v3_live, 'live_window_by_id', by_id)
    monkeypatch.setattr(end_answer.conversations_v3_live, 'live_window', active)
    return SimpleNamespace(asked=asked, state=state)


def response():
    return SimpleNamespace(headers={})


def test_without_a_stored_cut_the_answer_is_the_baseline_and_nothing_is_read(lookups):
    baseline, out = recording(ConversationStatus.in_progress), response()
    assert end_answer.answer('u', None, baseline, 'named', response=out) is baseline
    assert lookups.asked == [] and out.headers == {}


@pytest.mark.parametrize('status', [ConversationStatus.processing, ConversationStatus.completed, 'processing'])
def test_an_answer_the_baseline_path_processed_is_left_alone(lookups, status):
    baseline, out = recording(status), response()
    assert end_answer.answer('u', 'cut-1', baseline, None, response=out) is baseline
    assert lookups.asked == [] and out.headers == {}


def test_an_empty_listening_recording_is_answered_with_the_conversation_the_cut_ended(lookups):
    lookups.state['active'] = window()
    out = response()
    answer = end_answer.answer('u', 'cut-1', recording(ConversationStatus.in_progress), None, response=out, now=AT)
    assert isinstance(answer, CreateConversationResponse)
    assert answer.conversation.id == 'open-conversation'
    # Shown as the app shows a conversation whose summary is being written.
    assert answer.conversation.status == ConversationStatus.processing
    assert answer.conversation.tile_state == 'writing'
    assert out.headers == {end_answer.ACCEPTED_HEADER: 'conversation'}
    assert lookups.asked == [('active', 'u')]


def test_the_conversation_the_app_named_is_preferred_and_the_open_one_is_the_fallback(lookups):
    lookups.state.update(by_id=window('named'), active=window('other'))
    answer = end_answer.answer('u', 'cut-1', recording('in_progress'), 'named', now=AT)
    assert answer.conversation.id == 'named'
    assert lookups.asked == [('by_id', 'u', 'named')]

    lookups.asked.clear()
    lookups.state['by_id'] = None  # the named one is no longer open
    answer = end_answer.answer('u', 'cut-1', recording('in_progress'), 'named', now=AT)
    assert answer.conversation.id == 'other'
    assert lookups.asked == [('by_id', 'u', 'named'), ('active', 'u')]


def test_with_no_conversation_landed_yet_the_end_is_marked_accepted_and_the_body_stays(lookups):
    baseline, out = recording(ConversationStatus.in_progress), response()
    assert end_answer.answer('u', 'cut-1', baseline, None, response=out, now=AT) is baseline
    assert out.headers == {end_answer.ACCEPTED_HEADER: 'pending'}


def test_a_failed_lookup_falls_back_to_the_baseline_answer(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('store down')

    monkeypatch.setattr(end_answer.conversations_v3_live, 'live_window', broken)
    baseline, out = recording(ConversationStatus.in_progress), response()
    assert end_answer.answer('u', 'cut-1', baseline, None, response=out) is baseline
    assert out.headers == {}


# --- The End route: the answer is replaced only for a stored cut and an unprocessed listening recording ---


@pytest.fixture
def route(monkeypatch, lookups):
    from routers import conversations

    calls = []
    state = {'cut': 'cut-1', 'finalized': recording(ConversationStatus.in_progress)}
    monkeypatch.setattr(conversations.v3_manual_cuts, 'record_end', lambda uid, ended_at=None: state['cut'])
    monkeypatch.setattr(conversations.v3_manual_cuts, 'wake', lambda uid, cut_id: calls.append(('wake', cut_id)))
    monkeypatch.setattr(conversations, 'retrieve_in_progress_conversation', lambda uid: {'id': 'socket-recording'})
    monkeypatch.setattr(conversations, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(conversations.byok, 'has_byok_keys', lambda: False)
    monkeypatch.setattr(conversations, 'finalize_conversation', lambda cid, request=None, uid=None: state['finalized'])
    return SimpleNamespace(conversations=conversations, state=state, calls=calls, lookups=lookups)


def test_route_answers_with_the_ended_conversation_when_the_cut_is_stored(route):
    route.lookups.state['active'] = window()
    out = response()
    request = SimpleNamespace(live_conversation_id=None, calendar_meeting_context=None, client_processing=None)
    answer = route.conversations.process_in_progress_conversation(request=request, uid='u', response=out)
    assert answer.conversation.id == 'open-conversation' and answer.conversation.tile_state == 'writing'
    assert out.headers == {end_answer.ACCEPTED_HEADER: 'conversation'}
    assert route.calls == [('wake', 'cut-1')], 'the builder is still woken once for the cut'


def test_route_marks_the_end_pending_when_nothing_has_landed(route):
    out = response()
    answer = route.conversations.process_in_progress_conversation(request=None, uid='u', response=out)
    assert answer is route.state['finalized']
    assert out.headers == {end_answer.ACCEPTED_HEADER: 'pending'}


def test_route_keeps_the_baseline_answer_when_no_cut_was_stored(route):
    # The experiment is off, the account is not on grouping, or storing the cut failed.
    route.state['cut'] = None
    route.lookups.state['active'] = window()
    out = response()
    answer = route.conversations.process_in_progress_conversation(request=None, uid='u', response=out)
    assert answer is route.state['finalized'] and out.headers == {}
    assert route.lookups.asked == []


def test_route_keeps_an_answer_the_listening_recording_did_produce(route):
    route.state['finalized'] = recording(ConversationStatus.processing)
    route.lookups.state['active'] = window()
    out = response()
    answer = route.conversations.process_in_progress_conversation(request=None, uid='u', response=out)
    assert answer is route.state['finalized'] and out.headers == {}
