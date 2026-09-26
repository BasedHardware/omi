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


def utc_today():
    """The UTC day the events under test are stamped into.

    `date.today()` is the *local* date. `record_feedback_event` stamps
    `created_at` from `datetime.now(timezone.utc)` and `_day_bounds` reads a day
    as UTC midnight-to-midnight, so on any runner west of UTC these tests would
    ask for the wrong day for several hours each evening and see zero events.
    """
    return datetime.now(timezone.utc).date()


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
    # Both modules bind `get_firestore_client` by name at import, so patch the
    # name each one actually calls rather than only the definition site.
    monkeypatch.setattr(client_module, 'get_firestore_client', lambda: fake, raising=False)
    monkeypatch.setattr(feedback_db, 'get_firestore_client', lambda: fake)
    monkeypatch.setattr(ctx, 'get_firestore_client', lambda: fake)
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

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, platform='desktop')

    report = generate_report(utc_today())

    assert report.total_negative == 1
    assert report.counts_by_reason == {'not_captured': 1}
    assert report.counts_by_platform == {'desktop': 1}


def test_report_body_contains_no_message_text(fake_db):

    from jobs.feedback_daily_report import generate_report

    _seed_messages(
        fake_db,
        [
            _message('m1', 'human', -60, text='sensitive question'),
            _message('rated', 'ai', 0, text='sensitive answer'),
        ],
    )
    _record(fake_db, chat_session_id='s1')

    serialized = generate_report(utc_today()).model_dump_json()

    assert 'sensitive question' not in serialized
    assert 'sensitive answer' not in serialized
    assert 'rated' in serialized  # the pointer itself is there


def test_thumbs_up_events_are_not_in_the_negative_report(fake_db):

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, value=1)

    assert generate_report(utc_today()).total_negative == 0


def test_a_thumbs_down_then_a_reason_is_one_entry_carrying_the_reason(fake_db):
    """The macOS client sends the rating on tap and again when a reason is
    picked. That must read as one thumbs-down with a reason, not two."""

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, platform='desktop')
    _record(fake_db, platform='desktop', reason='incorrect_or_hallucination')

    report = generate_report(utc_today())

    assert report.total_negative == 1
    assert report.counts_by_reason == {'incorrect_or_hallucination': 1}


def test_distinct_messages_stay_distinct_entries(fake_db):

    from jobs.feedback_daily_report import generate_report

    _seed_messages(
        fake_db,
        [_message('rated', 'ai', 0), _message('rated2', 'ai', 60)],
    )
    _record(fake_db, target_id='rated')
    _record(fake_db, target_id='rated2')

    assert generate_report(utc_today()).total_negative == 2


def test_notification_ratings_are_a_separate_surface(fake_db):
    """The macOS client resolves surface='notification' for proactive cards
    (#12626). The rating endpoint must accept that value — rejecting it would
    422 the PATCH and revert the user's thumbs-down — and the report must count
    it apart from answers Omi actually gave."""

    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, surface=FeedbackSurface.chat_notification, platform='desktop')

    report = generate_report(utc_today())

    assert report.counts_by_surface == {'chat_notification': 1}


def test_truncation_is_judged_on_raw_rows_not_collapsed_entries(fake_db, monkeypatch):
    """A reasoned thumbs-down writes two ledger rows that collapse to one entry.
    If the fetch limit were measured after collapsing, a day that overran the
    fetch could still report `truncated: False` while silently dropping half
    its thumbs-down — the one failure the flag exists to rule out."""

    import database.feedback as feedback_db
    from jobs.feedback_daily_report import generate_report

    # Cap of 4 entries, raw fetch of 8 rows.
    monkeypatch.setattr(feedback_db, 'MAX_REPORT_ENTRIES', 4)
    monkeypatch.setattr(feedback_db, 'RAW_FETCH_LIMIT', 8)

    # 6 distinct rated messages, each rated twice (tap, then reason) = 12 raw
    # rows. That overruns the 8-row fetch, but collapses to at most 4 entries —
    # under the entry cap, so only the raw-row check can notice.
    messages = [_message(f'rated{i}', 'ai', i) for i in range(6)]
    _seed_messages(fake_db, messages)
    for i in range(6):
        _record(fake_db, target_id=f'rated{i}')
        _record(fake_db, target_id=f'rated{i}', reason='too_verbose')

    report = generate_report(utc_today())

    assert report.truncated, 'a report that could not read the whole day must say so'
    assert report.total_negative <= 4


# --------------------------------------------------------------------------
# Review fixes: the ways a window or a row can be quietly wrong
# --------------------------------------------------------------------------


def test_preceding_window_is_skipped_when_the_session_is_unknown(fake_db):
    """A rated message with no session id has no knowable "before".

    Keeping the time filter and dropping the session filter would return the
    previous ten messages from *any* conversation and print them as the setup
    for this answer — a reviewer would read an unrelated exchange as the
    question that produced the bad reply. Showing nothing is the honest answer.
    """
    from utils.feedback_context import resolve_chat_context

    _seed_messages(
        fake_db,
        [
            _message('elsewhere1', 'human', -300, session='unrelated'),
            _message('elsewhere2', 'ai', -200, session='unrelated'),
            _message('rated', 'ai', 0, session=None),
        ],
    )

    pointer = resolve_chat_context(UID, 'rated')

    assert [t.message_id for t in pointer.turns] == ['rated']
    assert pointer.resolution_error == 'preceding_turns_session_unknown'


def test_a_burst_of_follow_ups_is_reported_as_truncated(fake_db):
    """The window promises *every* turn within five minutes, so a cut has to
    be visible. A silently clipped burst reads as a calm retry."""
    from utils.feedback_context import MAX_FOLLOW_UP_TURNS, resolve_chat_context

    _seed_messages(
        fake_db,
        [_message('rated', 'ai', 0)] + [_message(f'f{i}', 'human', i + 1) for i in range(MAX_FOLLOW_UP_TURNS + 3)],
    )

    pointer = resolve_chat_context(UID, 'rated', chat_session_id='s1')

    assert pointer.follow_up_count == MAX_FOLLOW_UP_TURNS
    assert pointer.truncated_after is True


def test_hydrate_marks_a_turn_unavailable_when_it_comes_back_encrypted(fake_db, monkeypatch):
    """`utils.encryption.decrypt` returns its *input* when decryption fails, so
    a failed decrypt raises nothing and hands back base64 ciphertext typed as
    `str`. Rendering that as the user's words is worse than saying nothing."""
    import utils.feedback_context as ctx
    from utils.feedback_context import hydrate_context, resolve_chat_context

    _seed_messages(
        fake_db,
        [
            _message('m1', 'human', -60),
            _message('rated', 'ai', 0),
        ],
    )
    for doc in fake_db.collection('users').document(UID).collection('messages')._docs.values():
        doc['data_protection_level'] = 'enhanced'

    # The real failure mode: decrypt hands the ciphertext straight back.
    monkeypatch.setattr(ctx, 'decrypt_message_payload', lambda raw, uid: dict(raw))

    pointer = resolve_chat_context(UID, 'rated', chat_session_id='s1')
    hydrated = hydrate_context(pointer)

    assert hydrated.turns == []
    assert sorted(hydrated.unavailable) == ['m1', 'rated']


def test_an_unrecognized_reason_keeps_the_rating_and_drops_the_reason(fake_db):
    """The legacy mobile endpoint takes `reason` as a free-form query string.
    Writing an unknown value through would make the whole row unparseable, and
    the read boundary would drop it — losing a thumbs-down entirely."""
    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    assert _record(fake_db, reason='not_a_real_reason') is not None

    report = generate_report(utc_today())

    assert report.total_negative == 1
    assert report.counts_by_reason == {'not_captured': 1}


def test_an_uninterpretable_rating_value_is_refused_rather_than_stored(fake_db):
    """A value the report query can never match looks like recorded feedback
    and behaves like a hole. Better to refuse the row and log it."""
    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    assert _record(fake_db, value=-2) is None

    assert generate_report(utc_today()).total_negative == 0


def test_the_reason_survives_when_the_two_rating_writes_land_out_of_order(fake_db):
    """The client sends the bare rating on tap and the reasoned one when the
    user picks a chip — two independent requests that can be written in either
    order. Ranking by information content instead of arrival keeps the reason
    the user actually gave, however the two race."""
    from jobs.feedback_daily_report import generate_report

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db, reason='too_verbose')
    _record(fake_db)  # the bare tap, written second

    report = generate_report(utc_today())

    assert report.total_negative == 1
    assert report.counts_by_reason == {'too_verbose': 1}
    assert report.entries[0].event.reason.value == 'too_verbose'


def test_report_stops_at_the_document_size_budget_and_says_so(fake_db, monkeypatch):
    """Firestore rejects a document over 1 MiB outright, so the entry cap alone
    is not a safe bound — a heavy day would produce no report at all, which is
    exactly the day you want one."""
    import database.feedback as feedback_db
    from jobs.feedback_daily_report import generate_report

    monkeypatch.setattr(feedback_db, 'MAX_REPORT_DOCUMENT_BYTES', 3000)

    messages = [_message(f'rated{i}', 'ai', i) for i in range(20)]
    _seed_messages(fake_db, messages)
    for i in range(20):
        _record(fake_db, target_id=f'rated{i}')

    report = generate_report(utc_today())

    assert report.truncated is True
    # Counts still describe the whole day; only the context windows were cut.
    assert report.total_negative == 20
    assert 0 < len(report.entries) < 20
    assert sum(report.counts_by_surface.values()) == 20


def test_one_oversized_window_still_yields_an_entry(fake_db, monkeypatch):
    """A budget smaller than a single window must not produce an empty report:
    that is indistinguishable from a quiet day and tells a reviewer nothing."""
    import database.feedback as feedback_db
    from jobs.feedback_daily_report import generate_report

    monkeypatch.setattr(feedback_db, 'MAX_REPORT_DOCUMENT_BYTES', 1)

    _seed_messages(fake_db, [_message('rated', 'ai', 0)])
    _record(fake_db)

    report = generate_report(utc_today())

    assert len(report.entries) == 1
    assert report.truncated is False
