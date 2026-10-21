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
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None

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
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    statuses = {item['text']: (item['status'], item['action_item_id']) for item in episode['provisional_items']}
    assert statuses == {'Book lunch table for 12:30': ('kept', 'task-1'), 'Water the plants': ('dropped', None)}
    # The tail call saw only the unapplied tail.
    assert 'sandbox' in model.calls[1][1][1] and 'git thing' not in model.calls[1][1][1]
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='user_reprocess', collaborators=c) == 'skipped'


def test_wrap_up_waits_for_the_closing_conversation_then_closes():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    pending = service.wrap_up(UID, episode['id'], conversation_id='c1', collaborators=c)
    assert pending['status'] == 'live' and pending['closing_conversation_id'] == 'c1'
    row = {
        'id': 'c1',
        'source': 'omi',
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=2),
        'transcript_segments': [],
    }
    service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c)
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert service.live_episode(UID, collaborators=c) is None


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
