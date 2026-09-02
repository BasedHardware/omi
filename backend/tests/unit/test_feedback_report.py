"""Daily thumbs-down report contract.

The properties worth pinning are the ones that would otherwise fail silently:

* the report never contains message text (the whole privacy argument for
  materializing it at all),
* the follow-up window crosses chat sessions but stops at five minutes,
* a thumbs-down with no reason is counted as "not captured", not dropped,
* one rated message produces one report entry even when the client sends the
  rating twice (once bare, once carrying a reason).
"""

from datetime import datetime, timedelta, timezone

import pytest

from models.feedback import (
    FeedbackEvent,
    FeedbackSurface,
    FeedbackTargetKind,
)

RATED_AT = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
UID = 'uid-feedback-1'


# --------------------------------------------------------------------------
# Firestore fake — only the surface the feedback code actually touches.
# --------------------------------------------------------------------------


class _Snapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _Query:
    """Applies where/order_by/limit in Python over a list of snapshots."""

    def __init__(self, snapshots, filters=None, order=None, desc=False, limit=None):
        self._snapshots = snapshots
        self._filters = filters or []
        self._order = order
        self._desc = desc
        self._limit = limit

    def _clone(self, **kwargs):
        base = {
            'snapshots': self._snapshots,
            'filters': self._filters,
            'order': self._order,
            'desc': self._desc,
            'limit': self._limit,
        }
        base.update(kwargs)
        return _Query(**base)

    def where(self, filter=None, **_):
        return self._clone(filters=self._filters + [filter])

    def order_by(self, field, direction='ASCENDING'):
        return self._clone(order=field, desc=str(direction).upper().startswith('DESC'))

    def limit(self, count):
        return self._clone(limit=count)

    def stream(self):
        rows = list(self._snapshots)
        for f in self._filters:
            rows = [r for r in rows if _matches(r.to_dict(), f)]
        if self._order:
            rows.sort(key=lambda r: r.to_dict().get(self._order), reverse=self._desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(rows)


class _FieldFilter:
    def __init__(self, path, op, value):
        self.field_path = path
        self.op_string = op
        self.value = value


def _matches(data, f):
    actual = data.get(f.field_path)
    op = f.op_string
    if op == '==':
        return actual == f.value
    if actual is None:
        return False
    if op == '<':
        return actual < f.value
    if op == '<=':
        return actual <= f.value
    if op == '>':
        return actual > f.value
    if op == '>=':
        return actual >= f.value
    raise AssertionError(f'unsupported operator {op}')


class _DocRef:
    def __init__(self, docs, doc_id, subcollections):
        self._docs = docs
        self._doc_id = doc_id
        self._subcollections = subcollections

    def get(self):
        return _Snapshot(self._doc_id, self._docs.get(self._doc_id))

    def set(self, data):
        self._docs[self._doc_id] = dict(data)

    def collection(self, name):
        store = self._subcollections.setdefault(self._doc_id, {}).setdefault(name, {})
        return _Collection(store, {})


class _Collection:
    def __init__(self, docs, subcollections):
        self._docs = docs
        self._subcollections = subcollections

    def document(self, doc_id):
        return _DocRef(self._docs, doc_id, self._subcollections)

    def _snapshots(self):
        return [_Snapshot(k, v) for k, v in self._docs.items()]

    def where(self, filter=None, **_):
        return _Query(self._snapshots()).where(filter=filter)

    def order_by(self, field, direction='ASCENDING'):
        return _Query(self._snapshots()).order_by(field, direction)

    def limit(self, count):
        return _Query(self._snapshots()).limit(count)


class _FakeFirestore:
    def __init__(self):
        self._collections = {}
        self._subcollections = {}

    def collection(self, name):
        return _Collection(
            self._collections.setdefault(name, {}),
            self._subcollections.setdefault(name, {}),
        )


def _message(msg_id, sender, offset_seconds, session='s1', text='hello'):
    return {
        'id': msg_id,
        'sender': sender,
        'text': text,
        'created_at': RATED_AT + timedelta(seconds=offset_seconds),
        'chat_session_id': session,
    }


@pytest.fixture
def fake_db(monkeypatch):
    import database._client as client_module
    import database.feedback as feedback_db
    import utils.feedback_context as ctx

    fake = _FakeFirestore()
    monkeypatch.setattr(client_module, 'db', fake, raising=False)
    monkeypatch.setattr(feedback_db, 'db', fake)
    monkeypatch.setattr(ctx, 'db', fake)
    monkeypatch.setattr(ctx, 'FieldFilter', _FieldFilter)
    # database.feedback imports FieldFilter lazily inside the query function,
    # so patch it at the source module rather than on database.feedback.
    import google.cloud.firestore_v1 as firestore_v1

    monkeypatch.setattr(firestore_v1, 'FieldFilter', _FieldFilter)
    # Messages are stored plaintext in the fake; the real decrypt path is
    # exercised by database/chat.py's own tests.
    monkeypatch.setattr(ctx, 'decrypt_message_payload', lambda raw, uid: raw)
    return fake


def _seed_messages(fake, messages):
    ref = fake.collection('users').document(UID).collection('messages')
    for index, msg in enumerate(messages):
        ref.document(f'doc{index}').set(msg)


# --------------------------------------------------------------------------
# Context window
# --------------------------------------------------------------------------


def test_follow_up_window_crosses_sessions_but_stops_at_five_minutes(fake_db):
    from utils.feedback_context import resolve_chat_context

    _seed_messages(
        fake_db,
        [
            _message('m0', 'human', -120, session='s1'),
            _message('m1', 'ai', -60, session='s1'),
            _message('rated', 'ai', 0, session='s1'),
            # A retry in a brand new session is exactly the follow-up we want.
            _message('m3', 'human', 30, session='s2'),
            # Eight minutes later is a different conversation, not fallout.
            _message('m4', 'human', 480, session='s2'),
        ],
    )

    pointer = resolve_chat_context(UID, 'rated', chat_session_id='s1')
    ids = [t.message_id for t in pointer.turns]

    assert ids == ['m0', 'm1', 'rated', 'm3']
    assert pointer.follow_up_count == 1
    assert 'm4' not in ids


def test_preceding_turns_are_scoped_to_the_rated_session(fake_db):
    from utils.feedback_context import resolve_chat_context

    _seed_messages(
        fake_db,
        [
            _message('other', 'human', -300, session='other-session'),
            _message('m1', 'human', -60, session='s1'),
            _message('rated', 'ai', 0, session='s1'),
        ],
    )

    pointer = resolve_chat_context(UID, 'rated', chat_session_id='s1')
    assert [t.message_id for t in pointer.turns] == ['m1', 'rated']


def test_missing_rated_message_reports_an_error_rather_than_an_empty_window(fake_db):
    from utils.feedback_context import resolve_chat_context

    _seed_messages(fake_db, [_message('m1', 'human', -60)])
    pointer = resolve_chat_context(UID, 'gone')

    assert pointer.turns == []
    assert pointer.resolution_error == 'rated_message_not_found'


def test_pointer_carries_no_message_text(fake_db):
    from utils.feedback_context import resolve_chat_context

    _seed_messages(
        fake_db,
        [
            _message('m1', 'human', -60, text='my private question'),
            _message('rated', 'ai', 0, text='a bad answer'),
        ],
    )

    pointer = resolve_chat_context(UID, 'rated', chat_session_id='s1')
    serialized = pointer.model_dump_json()

    assert 'my private question' not in serialized
    assert 'a bad answer' not in serialized


def test_hydrate_returns_text_for_the_pointer_window(fake_db):
    from utils.feedback_context import hydrate_context, resolve_chat_context

    _seed_messages(
        fake_db,
        [
            _message('m1', 'human', -60, text='why is this broken'),
            _message('rated', 'ai', 0, text='I do not know'),
        ],
    )

    pointer = resolve_chat_context(UID, 'rated', chat_session_id='s1')
    hydrated = hydrate_context(pointer)

    assert [t.text for t in hydrated.turns] == ['why is this broken', 'I do not know']
    assert hydrated.unavailable == []


# --------------------------------------------------------------------------
# Report generation
# --------------------------------------------------------------------------


def _record(fake_db, **overrides):
    import database.feedback as feedback_db

    payload = {
        'uid': UID,
        'surface': FeedbackSurface.chat_text,
        'target_kind': FeedbackTargetKind.chat_message,
        'target_id': 'rated',
        'value': -1,
    }
    payload.update(overrides)
    return feedback_db.record_feedback_event(
        payload.pop('uid'),
        payload.pop('surface'),
        payload.pop('target_kind'),
        payload.pop('target_id'),
        payload.pop('value'),
        **payload,
    )


def test_report_counts_a_reasonless_thumbs_down_as_not_captured(fake_db):
    from datetime import date

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, platform='desktop')

    report = generate_report(date.today())

    assert report.total_negative == 1
    assert report.counts_by_reason == {'not_captured': 1}
    assert report.counts_by_platform == {'desktop': 1}


def test_report_body_contains_no_message_text(fake_db):
    from datetime import date

    from jobs.feedback_daily_report import generate_report

    _seed_messages(
        fake_db,
        [
            _message('m1', 'human', -60, text='sensitive question'),
            _message('rated', 'ai', 0, text='sensitive answer'),
        ],
    )
    _record(fake_db, chat_session_id='s1')

    serialized = generate_report(date.today()).model_dump_json()

    assert 'sensitive question' not in serialized
    assert 'sensitive answer' not in serialized
    assert 'rated' in serialized  # the pointer itself is there


def test_thumbs_up_events_are_not_in_the_negative_report(fake_db):
    from datetime import date

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, value=1)

    assert generate_report(date.today()).total_negative == 0


def test_a_thumbs_down_then_a_reason_is_one_entry_carrying_the_reason(fake_db):
    """The macOS client sends the rating on tap and again when a reason is
    picked. That must read as one thumbs-down with a reason, not two."""
    from datetime import date

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, platform='desktop')
    _record(fake_db, platform='desktop', reason='incorrect_or_hallucination')

    report = generate_report(date.today())

    assert report.total_negative == 1
    assert report.counts_by_reason == {'incorrect_or_hallucination': 1}


def test_distinct_messages_stay_distinct_entries(fake_db):
    from datetime import date

    from jobs.feedback_daily_report import generate_report

    _seed_messages(
        fake_db,
        [_message('rated', 'ai', 0), _message('rated2', 'ai', 60)],
    )
    _record(fake_db, target_id='rated')
    _record(fake_db, target_id='rated2')

    assert generate_report(date.today()).total_negative == 2


def test_notification_ratings_are_a_separate_surface(fake_db):
    """The macOS client resolves surface='notification' for proactive cards
    (#12626). The rating endpoint must accept that value — rejecting it would
    422 the PATCH and revert the user's thumbs-down — and the report must count
    it apart from answers Omi actually gave."""
    from datetime import date

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, surface=FeedbackSurface.chat_notification, platform='desktop')

    report = generate_report(date.today())

    assert report.counts_by_surface == {'chat_notification': 1}
