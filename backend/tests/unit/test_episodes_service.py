"""Episode orchestration over the strict Firestore fake: moments, boundaries, reconciliation, wrap-up."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import episodes as config
from database import episodes as episodes_db
from models.episode import Episode
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes import service
from utils.episodes.service import Collaborators, MomentInput

UID = 'uid-episodes'
T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    # These tests exercise a user whose app shows episodes (test_episodes_client_gate covers the marker).
    monkeypatch.setattr(service.client_gate, 'client_seen', lambda uid: True)
    service.client_gate.reset_for_tests()


class FakeModel:
    """Returns scripted answers and records exactly what each call was shown."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, uid, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0) if self.answers else {'bullets': ['x']}
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(content=json.dumps(answer), usage_metadata={'input_tokens': 400, 'output_tokens': 120})


def _collaborators(model, *, now, ask=None, saved=None, store=None):
    return Collaborators(
        invoke=model,
        ask=ask or (lambda *a, **k: None),
        tz_name='UTC',
        firestore_client=store,
        saved_tasks=lambda uid, cid: list((saved or {}).get(cid, [])),
        people_names=lambda uid, ids: {pid: 'Huong' for pid in ids},
        now=lambda: now,
    )


def _segments(text, *, start=0.0, step=5.0, person=None):
    words = text.split('. ')
    return [
        {
            'text': w,
            'start': start + i * step,
            'end': start + (i + 1) * step,
            'is_user': i % 2 == 0,
            'person_id': person,
        }
        for i, w in enumerate(words)
    ]


LONG = 'okay so 12:30 works for lunch near the office. perfect now the git thing where each agent gets its own worktree. and the server owns the diff so agents can just apply it cleanly. remind me to book the lunch table for twelve thirty'


def _moment(conversation_id='c1', *, minutes=0.0, trigger='pause', text=LONG, start=0.0, source='omi', person=None):
    return MomentInput(
        conversation_id=conversation_id,
        source=source,
        segments=_segments(text, start=start, person=person),
        started_at=T0 + timedelta(minutes=minutes),
        ended_at=T0 + timedelta(minutes=minutes + 1),
        trigger=trigger,
    )


def test_first_moment_opens_an_episode_with_sealed_content():
    store = StrictFirestore()
    model = FakeModel(
        {
            'title': 'Coding at the café',
            'moment_heading': 'Lunch plans',
            'bullets': ['Lunch with Huong at 12:30', 'Git worktree per agent'],
            'people': ['Huong'],
            'items': [{'text': 'Book lunch table for 12:30', 'kind': 'reminder'}],
        }
    )
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    assert service.record_moment(UID, _moment(person='p1'), c) == 'applied'

    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['title'] == 'Coding at the café'
    assert episode['conversation_ids'] == ['c1'] and episode['sources'] == ['omi']
    assert episode['moments'][0]['heading'] == 'Lunch plans'
    assert episode['provisional_items'][0]['status'] == 'provisional'
    assert episode['applied']['c1'] == 20.0
    assert episode['usage'] == {'calls': 1, 'input_tokens': 400, 'output_tokens': 120}
    # Speech-derived text never sits in plaintext on the document.
    raw = store.rows[('users', UID, 'episodes', episode['id'])]
    assert 'Huong' not in json.dumps(raw, default=str) and isinstance(raw['content'], str)
    # The model saw only the empty state and this moment, with the named speaker.
    system, user = model.calls[0]
    assert system[0] == 'system' and '"bullets":[]' in user[1] and 'Huong:' in user[1]
    assert user[1].index('Episode state so far') < user[1].index('Newest moment')


def test_next_moment_sends_only_state_plus_new_text_and_dedupes_applied_segments():
    store = StrictFirestore()
    model = FakeModel({'title': 'T', 'moment_heading': 'Lunch', 'bullets': ['Lunch at 12:30']}, {'bullets': ['B2']})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    later = _moment(minutes=3, text=LONG.upper(), start=0.0)
    # Same conversation, same offsets: already applied, no call.
    assert (
        service.record_moment(UID, later, _collaborators(model, now=T0 + timedelta(minutes=4), store=store))
        == 'skipped_applied'
    )
    fresh = _moment(
        minutes=3,
        text='so pricing for the hosted tier. we said twenty dollars a month for teams. and a free tier for students. that sounds right to me',
        start=30.0,
    )
    assert (
        service.record_moment(UID, fresh, _collaborators(model, now=T0 + timedelta(minutes=4), store=store))
        == 'applied'
    )
    user_message = model.calls[1][1][1]
    assert '"Lunch at 12:30"' in user_message and 'git thing' not in user_message and 'pricing' in user_message
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert [m['heading'] for m in episode['moments']] == ['Lunch', '']
    assert episode['bullets'] == ['B2'] and episode['applied']['c1'] == 50.0


def test_short_and_rate_limited_moments_cost_nothing():
    store = StrictFirestore()
    model = FakeModel({'bullets': ['A']})
    assert (
        service.record_moment(UID, _moment(text='hi there'), _collaborators(model, now=T0, store=store))
        == 'skipped_short'
    )
    assert model.calls == []
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    soon = _moment(minutes=1, start=40.0, text=LONG.replace('lunch', 'dinner'))
    assert (
        service.record_moment(UID, soon, _collaborators(model, now=T0 + timedelta(minutes=1, seconds=20), store=store))
        == 'rate_limited'
    )
    assert len(model.calls) == 1


def test_model_failure_keeps_state_and_reports_outcome():
    store = StrictFirestore()
    model = FakeModel(RuntimeError('provider down'))
    assert service.record_moment(UID, _moment(), _collaborators(model, now=T0, store=store)) == 'llm_error'
    # The occasion still exists, without notes; the next moment fills them in.
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['title'] == '' and episode['bullets'] == [] and episode['usage']['calls'] == 0

    def garbage(uid, messages):
        return SimpleNamespace(content='no json at all', usage_metadata={})

    assert service.record_moment(UID, _moment(), _collaborators(garbage, now=T0, store=store)) == 'parse_error'


def test_disabled_does_nothing(monkeypatch):
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    store = StrictFirestore()
    model = FakeModel({'bullets': ['A']})
    assert service.record_moment(UID, _moment(), _collaborators(model, now=T0, store=store)) == 'disabled'
    assert model.calls == [] and store.rows == {}
    assert service.on_conversation_finalized(UID, 'c1', {}, trigger='capture_end') == 'skipped'


def test_jev_moved_on_closes_and_opens_a_new_episode():
    store = StrictFirestore()
    model = FakeModel(
        {'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]}, {'title': 'Standup'}
    )
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    asked = []

    def ask(state, questions, **kwargs):
        asked.append(state)
        return SimpleNamespace(noul=lambda name: 0.05)

    later = _moment('c2', minutes=12)
    assert (
        service.record_moment(UID, later, _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store))
        == 'applied'
    )
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'moved_on'
    assert closed['provisional_items'][0]['status'] == 'dropped'
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['id'] != first['id'] and current['conversation_ids'] == ['c2']
    assert 'minutes_since_last_speech' in asked[0] and 'Lunch' in asked[0]


def test_parallel_capture_attaches_a_source_without_a_model_call():
    store = StrictFirestore()
    model = FakeModel({'title': 'Meeting', 'bullets': ['A']})
    service.record_moment(UID, _moment(minutes=0), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    other = _moment('c-desktop', minutes=0.5, source='desktop')
    assert (
        service.record_moment(UID, other, _collaborators(model, now=T0 + timedelta(minutes=2), store=store))
        == 'parallel'
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c-desktop'] and episode['sources'] == ['omi', 'desktop']
    assert len(model.calls) == 1
    assert episodes_db.get_episode_for_conversation(UID, 'c-desktop', firestore_client=store)['id'] == episode['id']


def test_finalization_applies_the_tail_and_reconciles_provisional_items():
    store = StrictFirestore()
    model = FakeModel(
        {
            'title': 'Lunch',
            'bullets': ['A'],
            'items': [{'text': 'Book lunch table for 12:30'}, {'text': 'Water the plants'}],
        },
        {'bullets': ['A', 'B']},
    )
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    row = {
        'id': 'c1',
        'source': 'omi',
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=2),
        'transcript_segments': _segments(LONG)
        + _segments(
            'and one more thing about the agents. they also need a sandbox for builds. that is all for now', start=30.0
        ),
    }
    saved = {'c1': [{'id': 'task-1', 'description': 'Book a lunch table'}]}
    c = _collaborators(model, now=T0 + timedelta(minutes=3), saved=saved, store=store)
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='capture_end', collaborators=c) == 'reconciled'
    # The phone's occasion conversation ended on silence, so its episode ended with it.
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    episode = episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)
    assert episode['status'] == 'closed' and episode['close_reason'] == 'gap'
    statuses = {item['text']: (item['status'], item['action_item_id']) for item in episode['provisional_items']}
    assert statuses == {'Book lunch table for 12:30': ('kept', 'task-1'), 'Water the plants': ('dropped', None)}
    # The tail call saw only the unapplied tail.
    assert 'sandbox' in model.calls[1][1][1] and 'git thing' not in model.calls[1][1][1]
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='user_reprocess', collaborators=c) == 'skipped'


def _row(conversation_id='c1', *, text=None, start=30.0, source='omi', **extra):
    return {
        'id': conversation_id,
        'source': source,
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=2),
        'transcript_segments': _segments(LONG) + (_segments(text, start=start) if text else []),
        **extra,
    }


TAIL = 'and one more thing about the agents. they also need a sandbox for builds. that is all for now'


def test_wrap_up_with_a_conversation_closes_now_and_reconciles_when_it_lands():
    store = StrictFirestore()
    model = FakeModel(
        {'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table for 12:30'}]},
        {'bullets': ['A', 'B']},
    )
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    closed = service.wrap_up(UID, episode['id'], conversation_id='c1', collaborators=c)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert closed['closing_conversation_id'] == 'c1' and closed['wrap_up_requested_at'] == T0 + timedelta(minutes=2)
    # Nothing live for the app to pick back up; the conversation's item waits for its processing.
    assert service.live_episode(UID, collaborators=c) is None
    assert [i['status'] for i in closed['provisional_items']] == ['provisional']

    saved = {'c1': [{'id': 'task-1', 'description': 'Book a lunch table'}]}
    c = _collaborators(model, now=T0 + timedelta(minutes=3), saved=saved, store=store)
    row = _row(text=TAIL)
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c) == 'reconciled'
    after = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    # The tail completed the closed episode's notes instead of opening a new live one.
    assert after['status'] == 'closed' and after['bullets'] == ['A', 'B']
    assert {i['text']: i['status'] for i in after['provisional_items']} == {'Book lunch table for 12:30': 'kept'}
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert service.live_episode(UID, collaborators=c) is None


def test_a_client_finalize_closes_the_live_episode_at_once_and_is_idempotent():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    # A pendant double-tap: the finalize closes the episode before the conversation processes.
    assert service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c) == 'closed'
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert closed['closed_at'] == T0 + timedelta(minutes=2)
    assert service.live_episode(UID, collaborators=c) is None
    # A second double-tap, or Wrap up after it, changes nothing and never errors.
    assert service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c) == 'not_live'
    again = service.wrap_up(UID, episode['id'], conversation_id='c1', collaborators=c)
    assert again['status'] == 'closed' and again['state_version'] == closed['state_version']
    assert service.wrap_up(UID, episode['id'], conversation_id=None, collaborators=c)['status'] == 'closed'
    # Processing finishing afterwards reconciles onto the closed episode and opens nothing.
    row = _row()
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c) == 'reconciled'
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    final = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert [i['status'] for i in final['provisional_items']] == ['dropped']


def test_an_ended_conversation_never_reopens_its_episode_and_the_next_words_open_a_new_one():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'title': 'Standup', 'bullets': ['S']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c)
    # The old conversation's late live moment and a re-attach (a reconnect) are both dropped.
    late = _moment('c1', minutes=1, start=60.0, text=TAIL + '. and a little more to say here')
    assert service.record_moment(UID, late, c) == 'skipped_closed'
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'attached'
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert len(model.calls) == 1
    # The next live words open the new episode, which the old conversation never joins.
    assert _attach(store, 'c2', minutes=3) == 'opened'
    second = episodes_db.get_current_episode(UID, firestore_client=store)
    assert second['id'] != first['id'] and second['conversation_ids'] == ['c2']
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'attached'
    assert service.record_moment(UID, late, c) == 'skipped_closed'
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['conversation_ids'] == ['c2'] and current['state_version'] == second['state_version']
    assert episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)['id'] == first['id']


def test_a_finalize_tail_never_opens_an_episode_after_its_own_closed():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    # Closed by the idle rule, not by this conversation's end: its tail still stays with it.
    idle = _collaborators(model, now=T0 + timedelta(hours=2), store=store)
    assert service.live_episode(UID, collaborators=idle) is None
    service.on_conversation_finalized(UID, 'c1', _row(text=TAIL), trigger='client_finalize', collaborators=idle)
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['close_reason'] == 'idle' and closed['bullets'] == ['A', 'B']


def test_server_recovery_reconciles_and_closes_the_occasion():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table for 12:30'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    saved = {'c1': [{'id': 'task-1', 'description': 'Book a lunch table'}]}
    c = _collaborators(model, now=T0 + timedelta(minutes=30), saved=saved, store=store)
    assert service.close_on_finalize(UID, 'c1', trigger='server_recovery', source='omi', collaborators=c) == 'closed'
    assert (
        service.on_conversation_finalized(UID, 'c1', _row(), trigger='server_recovery', collaborators=c) == 'reconciled'
    )
    episode = episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)
    assert episode['status'] == 'closed' and episode['close_reason'] == 'gap'
    assert [(i['status'], i['action_item_id']) for i in episode['provisional_items']] == [('kept', 'task-1')]


def test_a_server_side_end_keeps_the_episode_when_the_occasion_goes_on():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0, source='desktop')
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=5), store=store)
    # Desktop capture still splits on short silences: its end is not the occasion's end.
    assert service.close_on_finalize(UID, 'c1', trigger='capture_end', source='desktop', collaborators=c) == 'kept_open'
    # A conversation that joined after this one (a rollover, another device) keeps it going.
    _attach(store, 'c2', minutes=1)
    assert service.close_on_finalize(UID, 'c1', trigger='capture_end', source='omi', collaborators=c) == 'continued'
    assert episodes_db.get_current_episode(UID, firestore_client=store)['status'] == 'live'
    # A client finalize is the user ending it, whatever else is attached.
    assert service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c) == 'closed'
    assert service.close_on_finalize(UID, 'c1', trigger='user_reprocess', collaborators=c) == 'skipped'


def test_a_wrap_up_left_live_by_an_older_server_is_never_served_as_live():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    episodes_db.update_episode(
        UID,
        episode['id'],
        expected_version=episode['state_version'],
        updates={'wrap_up_requested_at': T0 + timedelta(minutes=2), 'closing_conversation_id': 'c1'},
        firestore_client=store,
    )
    c = _collaborators(model, now=T0 + timedelta(minutes=2, seconds=5), store=store)
    assert service.live_episode(UID, collaborators=c) is None
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    # Its conversation's item still waits for that conversation's reconciliation.
    assert [i['status'] for i in closed['provisional_items']] == ['provisional']


def test_a_discarded_conversation_still_ends_its_episode_and_drops_its_items():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    row = _row(discarded=True)
    assert (
        service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c)
        == 'skipped_discarded'
    )
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert [i['status'] for i in closed['provisional_items']] == ['dropped']


def test_wrap_up_without_a_conversation_closes_now_and_dismiss_marks_an_item():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    item_id = episode['provisional_items'][0]['id']
    dismissed = service.dismiss_item(UID, episode['id'], item_id, collaborators=c)
    assert dismissed['provisional_items'][0]['status'] == 'dismissed'
    closed = service.wrap_up(UID, episode['id'], conversation_id=None, collaborators=c)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert closed['provisional_items'][0]['status'] == 'dismissed'
    assert service.wrap_up(UID, 'missing', conversation_id=None, collaborators=c) is None


def test_reads_close_idle_episodes_lazily_and_wire_projection_hides_internals():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    live = service.live_episode(UID, collaborators=_collaborators(model, now=T0 + timedelta(minutes=5), store=store))
    wire = service.to_wire(live)
    assert set(wire) == {
        'id',
        'status',
        'started_at',
        'last_activity_at',
        'closed_at',
        'close_reason',
        'title',
        'bullets',
        'people',
        'provisional_items',
        'moments',
        'conversation_ids',
        'sources',
        'state_updated_at',
    }
    assert Episode.model_validate(wire).provisional_items[0].text == 'Book lunch table'
    idle = _collaborators(model, now=T0 + timedelta(hours=2), store=store)
    assert service.live_episode(UID, collaborators=idle) is None
    closed = service.episode_for_conversation(UID, 'c1', collaborators=idle)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'idle'


def test_smart_merge_absorb_repoints_the_episode_to_the_survivor():
    store = StrictFirestore()
    model = FakeModel({'title': 'Dinner', 'bullets': ['A']}, {'title': 'Dinner', 'bullets': ['B']})
    service.record_moment(UID, _moment('survivor'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    service.record_moment(
        UID, _moment('donor', minutes=3), _collaborators(model, now=T0 + timedelta(minutes=4), store=store)
    )
    donor_row = {'id': 'donor', 'smart_merge': {'role': 'donor', 'survivor_id': 'survivor'}, 'finished_at': T0}
    c = _collaborators(model, now=T0 + timedelta(minutes=5), store=store)
    service.on_conversation_finalized(
        UID, 'survivor', donor_row, trigger='capture_end', absorbed_from='donor', collaborators=c
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['survivor']
    assert {m['conversation_id'] for m in episode['moments']} == {'survivor'}


def test_commit_conflict_is_reported_not_raised(monkeypatch):
    store = StrictFirestore()
    model = FakeModel({'bullets': ['A']}, {'bullets': ['B']})

    def always_conflict(*args, **kwargs):
        raise episodes_db.EpisodeConflict('state_version_changed')

    monkeypatch.setattr(episodes_db, 'commit_moment', always_conflict)
    assert service.record_moment(UID, _moment(), _collaborators(model, now=T0, store=store)) == 'conflict'
    assert len(model.calls) == 2


def test_mentor_state_is_the_compact_render_or_none(monkeypatch):
    monkeypatch.setattr(
        service, 'live_episode', lambda uid: {'title': 'Lunch', 'bullets': ['A'], 'provisional_items': []}
    )
    assert json.loads(service.mentor_episode_state(UID))['topic'] == 'Lunch'
    monkeypatch.setattr(service, 'live_episode', lambda uid: None)
    assert service.mentor_episode_state(UID) is None
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert service.mentor_episode_state(UID) is None


# --------------------------------------------------------------------------- structure before notes


def _attach(store, conversation_id, *, minutes, source='omi', now_minutes=None):
    c = _collaborators(
        FakeModel(), now=T0 + timedelta(minutes=now_minutes if now_minutes is not None else minutes), store=store
    )
    return service.attach_conversation(
        UID, conversation_id, source, started_at=T0 + timedelta(minutes=minutes), collaborators=c
    )


def test_first_words_open_the_episode_without_a_model_call():
    store = StrictFirestore()
    model = FakeModel()
    c = _collaborators(model, now=T0, store=store)
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'opened'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    # The app gets a live episode, its real start and its member conversation right away.
    assert episode['status'] == 'live' and episode['title'] == '' and model.calls == []
    assert episode['started_at'] == T0 and episode['conversation_ids'] == ['c1'] and episode['sources'] == ['omi']
    assert episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)['id'] == episode['id']
    # Attaching again (a reconnect, another replica) is a no-op.
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'attached'


def test_fragments_join_the_live_episode_so_home_can_hide_them():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0)
    # A live split a minute later, and an overlapping capture from another device.
    assert _attach(store, 'c2', minutes=1) == 'joined'
    assert _attach(store, 'c3', minutes=0.5, source='phone', now_minutes=1) == 'joined'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c2', 'c3'] and episode['sources'] == ['omi', 'phone']
    # Then the first moment's notes land on that same episode.
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(
        UID, _moment('c2', minutes=1), _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    )
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['title'] == 'Lunch'


def test_an_ambiguous_gap_joins_provisionally_and_jev_splits_it_off():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'title': 'Standup'})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    assert _attach(store, 'c2', minutes=12) == 'pending'
    joined = episodes_db.get_current_episode(UID, firestore_client=store)
    assert joined['conversation_ids'] == ['c1', 'c2'] and set(joined['pending_boundary']) == {'c2'}

    ask = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05)  # noqa: E731
    later = _moment('c2', minutes=12)
    c = _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store)
    assert service.record_moment(UID, later, c) == 'applied'
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['close_reason'] == 'moved_on' and closed['conversation_ids'] == ['c1']
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['id'] != first['id'] and current['conversation_ids'] == ['c2'] and current['title'] == 'Standup'
    assert episodes_db.get_episode_for_conversation(UID, 'c2', firestore_client=store)['id'] == current['id']


def test_jev_same_occasion_keeps_the_provisional_join():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['B']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    _attach(store, 'c2', minutes=12)
    ask = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    c = _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store)
    assert service.record_moment(UID, _moment('c2', minutes=12), c) == 'applied'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c2'] and episode['pending_boundary'] == {}
    assert episode['bullets'] == ['B']


def test_a_long_gap_attach_closes_the_old_episode_and_opens_a_new_one():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0)
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    # 29 minutes later sits between the continue and close gaps: a provisional join.
    assert _attach(store, 'c2', minutes=29, now_minutes=29) == 'pending'
    assert _attach(store, 'c9', minutes=120, now_minutes=120) == 'opened'
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed'


def test_an_idle_close_is_stamped_when_the_quiet_reached_the_gap():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0)
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    # Nobody looks for eight hours; the next read closes it, dated at the gap, not at the read.
    reader = _collaborators(FakeModel(), now=T0 + timedelta(hours=8), store=store)
    assert service.live_episode(UID, collaborators=reader) is None
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['close_reason'] == 'idle'
    assert closed['closed_at'] == T0 + timedelta(seconds=config.CLOSE_GAP_SECONDS)


def test_two_provisional_joins_are_each_settled_at_their_own_first_moment():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['B']}, {'bullets': ['C']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    _attach(store, 'c2', minutes=12)
    _attach(store, 'c3', minutes=12.5, source='phone', now_minutes=12.5)
    assert set(episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary']) == {'c2', 'c3'}
    keep = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    service.record_moment(
        UID, _moment('c2', minutes=12), _collaborators(model, now=T0 + timedelta(minutes=13), ask=keep, store=store)
    )
    assert set(episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary']) == {'c3'}


def test_a_failed_model_call_after_a_split_still_leaves_a_live_episode():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, RuntimeError('provider down'))
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    _attach(store, 'c2', minutes=12)
    moved_on = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05)  # noqa: E731
    c = _collaborators(model, now=T0 + timedelta(minutes=13), ask=moved_on, store=store)
    assert service.record_moment(UID, _moment('c2', minutes=12), c) == 'llm_error'
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current is not None and current['id'] != first['id'] and current['conversation_ids'] == ['c2']
    assert current['title'] == ''


def test_moment_render_receives_account_and_conversation_and_language_reaches_update(monkeypatch):
    from dataclasses import replace
    from unittest.mock import Mock

    render = Mock(wraps=service.incremental.render_moment)
    update = Mock(wraps=service.incremental.run_incremental_update)
    monkeypatch.setattr(service.incremental, 'render_moment', render)
    monkeypatch.setattr(service.incremental, 'run_incremental_update', update)
    moment = replace(_moment(), language='en')
    model = FakeModel({'title': 'Fixture', 'moment_heading': 'Fixture', 'bullets': ['Fixture']})
    result = service.record_moment(
        UID, moment, _collaborators(model, now=T0 + timedelta(minutes=1), store=StrictFirestore())
    )
    assert result == 'applied'
    assert render.call_args.kwargs == {'uid': UID, 'conversation_id': moment.conversation_id}
    assert update.call_args.kwargs['conversation_language'] == 'en'
    assert len(model.calls) == 1
