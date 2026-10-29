"""One push when an account's first summary is ready.

The account decides once, atomically. The push goes to its first ready summary only: unprocessed
rows do not count, an older summary means the account is not new, and a summary that finished at
the same moment as an earlier one steps aside for it. The decision records what the dispatch did.
"""

import copy
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from firebase_admin import messaging
from google.api_core.exceptions import AlreadyExists, NotFound, ServiceUnavailable

import database.first_summary_push as push_db
import utils.conversations.first_summary_push as first_summary_push
import utils.notifications as notifications
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from utils.conversations.first_summary_copy import FIRST_SUMMARY_COPY
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.notification_dispatch import NotificationDispatchOutcome, NotificationDispatchStatus, NotificationKind

UID = 'first-summary-owner'
MARKER = ('users', UID, 'notification_markers', 'first_summary_push')
CAPTURED = datetime(2026, 10, 29, 16, 35, tzinfo=timezone.utc)
TITLE = 'Weekly product sync with design'


class _Store:
    """Just enough Firestore for the marker: document get, atomic ``create`` and ``update``."""

    def __init__(self):
        self.docs = {}
        self.lock = threading.Lock()
        self.write_error = None

    def collection(self, name):
        return _Ref(self, (name,))


class _Ref:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def document(self, name):
        return _Ref(self.store, self.path + (name,))

    collection = document

    def get(self):
        data = self.store.docs.get(self.path)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: dict(data or {}))

    def create(self, data):
        if self.store.write_error is not None:
            raise self.store.write_error
        with self.store.lock:
            if self.path in self.store.docs:
                raise AlreadyExists('document exists')
            self.store.docs[self.path] = dict(data)

    def update(self, data):
        with self.store.lock:
            if self.path not in self.store.docs:
                raise NotFound('no document')
            self.store.docs[self.path].update(data)


def _conversation(conversation_id='conv-1', *, title=TITLE, overview='We agreed on X.', discarded=False):
    """The in-memory conversation ``process_conversation`` hands off."""
    return Conversation(
        id=conversation_id,
        created_at=CAPTURED,
        started_at=CAPTURED,
        finished_at=CAPTURED,
        source=ConversationSource.omi,
        structured=Structured(title=title, overview=overview),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=discarded,
    )


def _row(
    conversation_id, *, created=CAPTURED, written_ago=timedelta(0), title=TITLE, overview='We agreed on X.', **fields
):
    """A stored conversation document, as Firestore holds it."""
    return {
        'id': conversation_id,
        'created_at': created,
        'status': 'completed',
        'discarded': False,
        'language': 'en',
        'structured': {'title': title, 'overview': overview, 'sections': []},
        'written_ago': written_ago,
        **fields,
    }


@pytest.fixture
def account(monkeypatch):
    store = _Store()
    state = SimpleNamespace(
        store=store,
        rows={},
        settings={'enabled': True},
        language='',
        dispatch=NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=2),
        sent=[],
        history_reads=0,
    )

    def get_conversation(uid, conversation_id):
        assert uid == UID
        row = state.rows.get(conversation_id)
        return None if row is None else {k: v for k, v in copy.deepcopy(row).items() if k != 'written_ago'}

    def oldest_conversation_summaries(uid, limit):
        # The real query: discarded == False, status == 'completed', oldest created first.
        assert (uid, limit) == (UID, first_summary_push.HISTORY_WINDOW)
        state.history_reads += 1
        now = datetime.now(timezone.utc)
        kept = [row for row in state.rows.values() if row['status'] == 'completed' and not row['discarded']]
        kept.sort(key=lambda row: row['created_at'])
        return [
            {
                'id': row['id'],
                'created_at': row['created_at'],
                'structured': {key: row['structured'].get(key) for key in ('overview', 'sections')},
                'updated_at': now - row['written_ago'],
            }
            for row in kept[:limit]
        ]

    def dispatch(intent):
        state.sent.append(intent)
        if isinstance(state.dispatch, Exception):
            raise state.dispatch
        return state.dispatch

    monkeypatch.setattr(push_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(push_db, 'oldest_conversation_summaries', oldest_conversation_summaries)
    monkeypatch.setattr(first_summary_push.conversations_db, 'get_conversation', get_conversation)
    monkeypatch.setattr(first_summary_push.users_db, 'get_notification_settings', lambda uid: dict(state.settings))
    monkeypatch.setattr(first_summary_push.users_db, 'get_user_language_preference', lambda uid: state.language)
    monkeypatch.setattr(first_summary_push, 'dispatch_notification', dispatch)
    return state


def _decide(conversation_id='conv-1', trigger=ProcessingTrigger.CAPTURE_END, **conversation):
    return first_summary_push.maybe_send_first_summary_push(
        UID, _conversation(conversation_id, **conversation), trigger
    )


def _marker(state):
    return state.store.docs.get(MARKER)


def test_first_summary_sends_one_push_that_opens_it(account):
    account.rows['conv-1'] = _row('conv-1')

    assert _decide() == 'sent'

    assert len(account.sent) == 1
    intent = account.sent[0]
    assert intent.user_id == UID
    assert intent.kind == NotificationKind.FIRST_SUMMARY
    assert intent.title == 'Your first summary is ready'
    assert intent.body == TITLE
    assert dict(intent.data) == {
        'type': 'first_summary',
        'conversation_id': 'conv-1',
        'navigate_to': '/conversation/conv-1',
    }
    marker = _marker(account)
    assert {key: marker[key] for key in ('outcome', 'conversation_id', 'language', 'delivered')} == {
        'outcome': 'sent',
        'conversation_id': 'conv-1',
        'language': 'en',
        'delivered': 2,
    }
    assert 'created_at' in marker and 'settled_at' in marker


def test_retries_and_later_summaries_never_push_again(account):
    account.rows['conv-1'] = _row('conv-1')
    assert _decide('conv-1') == 'sent'

    # The same conversation retried, then two later summaries on the same account.
    for later in ('conv-2', 'conv-3'):
        account.rows[later] = _row(later, created=CAPTURED + timedelta(hours=1))
    for conversation_id in ('conv-1', 'conv-2', 'conv-3'):
        assert _decide(conversation_id, ProcessingTrigger.SYNC_UPDATE) == 'already_decided'

    assert len(account.sent) == 1
    assert account.history_reads == 1  # a decided account is never scanned again
    assert _marker(account)['conversation_id'] == 'conv-1'


def test_duplicate_decisions_for_one_summary_push_once(account, monkeypatch):
    # Both workers read "undecided" before either writes; Firestore's create picks one winner.
    account.rows['conv-1'] = _row('conv-1')
    monkeypatch.setattr(push_db, 'get_decision', lambda uid: None)
    start = threading.Barrier(2)
    outcomes = []

    def worker():
        start.wait()
        outcomes.append(_decide('conv-1'))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ['already_decided', 'sent']
    assert len(account.sent) == 1


def test_unprocessed_recordings_do_not_take_the_first_push(account):
    # A sync batch stores both recordings as completed rows before either has a summary.
    account.rows['older'] = _row('older', overview='', title='Processing')
    account.rows['newer'] = _row('newer', created=CAPTURED + timedelta(minutes=30))

    assert _decide('newer', ProcessingTrigger.SYNC_UPDATE) == 'sent'
    assert account.sent[0].data['conversation_id'] == 'newer'

    # The older recording finishes later; the account already had its push.
    account.rows['older'] = _row('older')
    assert _decide('older', ProcessingTrigger.SYNC_UPDATE) == 'already_decided'
    assert len(account.sent) == 1


@pytest.mark.parametrize(
    'order, expected',
    [
        (('earlier', 'later'), {'earlier': 'sent', 'later': 'already_decided'}),
        (('later', 'earlier'), {'later': 'deferred', 'earlier': 'sent'}),
    ],
    ids=['earlier-decides-first', 'later-decides-first'],
)
def test_two_summaries_finishing_together_push_once_for_the_earlier_one(account, order, expected):
    # Both recordings got their summaries moments apart; either decision may run first.
    account.rows['earlier'] = _row('earlier')
    account.rows['later'] = _row('later', created=CAPTURED + timedelta(minutes=5))

    outcomes = {conversation_id: _decide(conversation_id, ProcessingTrigger.SYNC_UPDATE) for conversation_id in order}

    assert outcomes == expected
    assert [intent.data['conversation_id'] for intent in account.sent] == ['earlier']
    assert _marker(account)['conversation_id'] == 'earlier'


def test_two_summaries_deciding_at_the_same_time_push_once(account, monkeypatch):
    # Both decisions read "undecided" before either claims, with both summaries already stored.
    account.rows['earlier'] = _row('earlier')
    account.rows['later'] = _row('later', created=CAPTURED + timedelta(minutes=5))
    both_read = threading.Barrier(2)
    read_decision = push_db.get_decision

    def get_decision(uid):
        decision = read_decision(uid)
        both_read.wait()
        return decision

    monkeypatch.setattr(push_db, 'get_decision', get_decision)
    outcomes = {}

    def worker(conversation_id):
        outcomes[conversation_id] = _decide(conversation_id, ProcessingTrigger.SYNC_UPDATE)

    threads = [threading.Thread(target=worker, args=(cid,)) for cid in ('earlier', 'later')]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes == {'earlier': 'sent', 'later': 'deferred'}
    assert len(account.sent) == 1 and account.sent[0].data['conversation_id'] == 'earlier'


def test_existing_account_is_never_told_its_summary_is_the_first(account):
    account.rows['last-year'] = _row(
        'last-year', created=CAPTURED - timedelta(days=300), written_ago=timedelta(days=300)
    )
    account.rows['conv-1'] = _row('conv-1')

    assert _decide() == 'not_first'

    assert account.sent == []
    assert _marker(account)['outcome'] == 'not_first'
    account.rows['conv-2'] = _row('conv-2', created=CAPTURED + timedelta(hours=1))
    assert _decide('conv-2') == 'already_decided'


def test_existing_account_syncing_a_big_batch_is_still_not_first(account):
    # History sits at the start of the account; the batch fills the newest rows.
    account.rows['last-year'] = _row(
        'last-year', created=CAPTURED - timedelta(days=300), written_ago=timedelta(days=300)
    )
    for index in range(30):
        account.rows[f'batch-{index}'] = _row(
            f'batch-{index}', created=CAPTURED + timedelta(minutes=index), overview='', title='Processing'
        )
    account.rows['batch-29'] = _row('batch-29', created=CAPTURED + timedelta(minutes=29))

    assert _decide('batch-29', ProcessingTrigger.SYNC_UPDATE) == 'not_first'
    assert account.sent == []


def test_recently_rewritten_history_waits_instead_of_pushing(account):
    # An old summary rewritten moments ago looks like one still deciding: step aside, decide nothing.
    account.rows['last-year'] = _row('last-year', created=CAPTURED - timedelta(days=300))
    account.rows['conv-1'] = _row('conv-1')

    assert _decide() == 'deferred'
    assert account.sent == [] and _marker(account) is None


@pytest.mark.parametrize(
    'trigger',
    [
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.MERGE,
        ProcessingTrigger.BACKLOG_CHOICE,
    ],
)
def test_summary_asked_for_in_the_app_is_not_pushed(account, trigger):
    account.rows['conv-1'] = _row('conv-1')

    assert _decide(trigger=trigger) == 'in_app'
    assert account.sent == []
    assert _marker(account)['outcome'] == 'in_app'


@pytest.mark.parametrize(
    'trigger',
    [
        ProcessingTrigger.CAPTURE_END,
        ProcessingTrigger.CLIENT_FINALIZE,
        ProcessingTrigger.SYNC_UPDATE,
        ProcessingTrigger.SERVER_RECOVERY,
    ],
)
def test_background_processing_pushes(account, trigger):
    account.rows['conv-1'] = _row('conv-1')

    assert _decide(trigger=trigger) == 'sent'
    assert len(account.sent) == 1


def test_notifications_turned_off_get_no_push_and_the_moment_is_spent(account):
    account.rows['conv-1'] = _row('conv-1')
    account.settings = {'enabled': False}

    assert _decide() == 'suppressed'
    assert account.sent == []
    marker = _marker(account)
    assert (marker['outcome'], marker['reason']) == ('suppressed', 'notifications_disabled')

    # Turning notifications back on later does not resurrect a "first" summary push.
    account.settings = {'enabled': True}
    account.rows['conv-2'] = _row('conv-2', created=CAPTURED + timedelta(hours=1))
    assert _decide('conv-2') == 'already_decided'
    assert account.sent == []


@pytest.mark.parametrize(
    'dispatch, outcome, recorded',
    [
        (
            NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=0),
            'undelivered',
            {'delivered': 0, 'reason': 'no_device_accepted'},
        ),
        (
            NotificationDispatchOutcome(NotificationDispatchStatus.SUPPRESSED, reason='account_pending_deletion'),
            'suppressed',
            {'reason': 'account_pending_deletion'},
        ),
        (
            NotificationDispatchOutcome(NotificationDispatchStatus.FAILED, reason='delivery_failed'),
            'failed',
            {'reason': 'delivery_failed', 'retryable': True},
        ),
    ],
    ids=['no-tokens', 'suppressed', 'failed'],
)
def test_only_an_accepted_push_is_recorded_as_sent(account, dispatch, outcome, recorded):
    account.rows['conv-1'] = _row('conv-1')
    account.dispatch = dispatch

    assert _decide() == outcome

    marker = _marker(account)
    assert marker['outcome'] == outcome
    assert {key: marker.get(key) for key in recorded} == recorded
    # The claim stays the barrier: no automatic second attempt.
    assert _decide() == 'already_decided'
    assert len(account.sent) == 1


def test_an_interrupted_dispatch_stays_an_unconfirmed_claim(account):
    account.rows['conv-1'] = _row('conv-1')
    account.dispatch = RuntimeError('worker stopped mid-send')

    assert _decide() == 'error'

    marker = _marker(account)
    assert marker['outcome'] == 'claimed' and 'settled_at' not in marker
    assert _decide() == 'already_decided'
    assert len(account.sent) == 1


@pytest.mark.parametrize(
    'stored',
    [
        None,
        _row('conv-1', deleted=True),
        _row('conv-1', discarded=True),
        _row('conv-1', dream_duplicate_of='conv-0'),
        _row('conv-1', overview=''),
        _row('conv-1', status='processing'),
    ],
    ids=['gone', 'deleted', 'discarded', 'duplicate-capture', 'summary-gone', 'reprocessing'],
)
def test_a_conversation_no_longer_visible_leaves_the_decision_open(account, stored):
    if stored is not None:
        account.rows['conv-1'] = stored

    assert _decide() == 'not_visible'
    assert account.sent == [] and _marker(account) is None


@pytest.mark.parametrize(
    'conversation',
    [
        _conversation(overview=''),
        _conversation(discarded=True),
        SimpleNamespace(id='conv-1', discarded=False, structured=None),
    ],
    ids=['no-summary', 'discarded', 'no-structure'],
)
def test_no_readable_summary_decides_nothing(account, conversation):
    account.rows['conv-1'] = _row('conv-1')

    outcome = first_summary_push.maybe_send_first_summary_push(UID, conversation, ProcessingTrigger.CAPTURE_END)

    assert outcome == 'no_summary'
    assert account.sent == [] and account.history_reads == 0 and _marker(account) is None


def test_storage_failure_never_pushes(account):
    account.rows['conv-1'] = _row('conv-1')
    account.store.write_error = ServiceUnavailable('firestore down')

    assert _decide() == 'error'
    assert account.sent == []


@pytest.mark.parametrize(
    'language, title, untitled',
    [
        ('de', 'Ihre erste Zusammenfassung ist fertig', 'Tippen zum Anzeigen'),
        ('ja', '最初の要約ができました', 'タップして表示'),
        ('ar', 'ملخصك الأول جاهز', 'اضغط للعرض'),
    ],
)
def test_copy_is_in_the_readers_language(account, language, title, untitled):
    account.language = language
    account.rows['titled'] = _row('titled', title='Wochenplanung')
    assert _decide('titled', title='Wochenplanung') == 'sent'
    assert (account.sent[-1].title, account.sent[-1].body) == (title, 'Wochenplanung')
    assert _marker(account)['language'] == language

    # A second account whose first conversation has no title gets the localized fallback.
    account.store.docs.clear()
    account.rows = {'untitled': _row('untitled', title='  ')}
    assert _decide('untitled', title='  ') == 'sent'
    assert (account.sent[-1].title, account.sent[-1].body) == (title, untitled)


@pytest.mark.parametrize(
    'preference, captured_in, expected',
    [
        ('', 'ja', 'ja'),  # no preference: the conversation's language, like its summary
        ('pt-BR', 'en', 'pt'),  # a regional preference uses its base language
        ('multi', 'de', 'de'),  # "multi" names no language
        ('xx', 'xx', 'en'),  # unsupported: English
    ],
)
def test_copy_language_follows_the_summary_language(account, preference, captured_in, expected):
    account.language = preference
    account.rows['conv-1'] = _row('conv-1', language=captured_in)

    _decide()

    assert account.sent[0].title == FIRST_SUMMARY_COPY[expected][0]


def test_copy_is_short_and_plain():
    for language, strings in FIRST_SUMMARY_COPY.items():
        for text in strings:
            assert text.strip() == text and text, language
            assert '—' not in text and '–' not in text, language


def test_the_fcm_message_is_a_visible_push_that_deep_links_to_the_summary(monkeypatch):
    captured = []
    monkeypatch.setattr(notifications, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(notifications, '_send_messages', lambda messages: captured.extend(messages))
    monkeypatch.setattr(notifications, '_collect_send_results', lambda response, tokens: (len(tokens), []))
    intent = first_summary_push.first_summary_intent(UID, 'conv-1', 'اجتماع الفريق', 'ar')

    delivered = notifications.send_notification_result(
        UID, intent.title, intent.body, dict(intent.data), tokens=['ios-token', 'android-token']
    )

    assert delivered == 2
    encoded = [messaging._MessagingService.encode_message(message) for message in captured]
    assert [message['token'] for message in encoded] == ['ios-token', 'android-token']
    for message in encoded:
        assert message['notification'] == {'title': 'ملخصك الأول جاهز', 'body': 'اجتماع الفريق'}
        assert message['data'] == {
            'type': 'first_summary',
            'conversation_id': 'conv-1',
            'navigate_to': '/conversation/conv-1',
        }
        assert message['android']['notification']['tag'] == message['apns']['headers']['apns-collapse-id']


def test_history_reads_the_oldest_kept_conversations_and_their_last_write():
    written = datetime(2026, 1, 2, tzinfo=timezone.utc)
    calls = []

    class _Query:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                calls.append((name, args, kwargs))
                return self

            return record

        def stream(self):
            snapshot = SimpleNamespace(
                id='conv-0', update_time=written, to_dict=lambda: {'created_at': CAPTURED, 'structured': {}}
            )
            return iter([snapshot])

    rows = push_db.oldest_conversation_summaries(UID, 10, firestore_client=_Query())

    assert rows == [{'created_at': CAPTURED, 'structured': {}, 'id': 'conv-0', 'updated_at': written}]
    names = [name for name, _, _ in calls]
    assert names == ['collection', 'document', 'collection', 'where', 'where', 'order_by', 'select', 'limit']
    filters = [kwargs['filter'] for name, _, kwargs in calls if name == 'where']
    assert [(f.field_path, f.op_string, f.value) for f in filters] == [
        ('discarded', '==', False),
        ('status', '==', 'completed'),
    ]
    order = next(call for call in calls if call[0] == 'order_by')
    assert order[1] == ('created_at',) and order[2]['direction'] == 'ASCENDING'
    assert next(call for call in calls if call[0] == 'limit')[1] == (10,)


def test_hand_off_queues_a_summary_this_pass_made_appear(monkeypatch):
    submitted = []
    monkeypatch.setattr(first_summary_push, 'submit_with_context', lambda *args: submitted.append(args))
    conversation = _conversation()

    first_summary_push.hand_off(UID, conversation, ProcessingTrigger.CAPTURE_END, first_observation=True)

    assert submitted == [
        (
            first_summary_push.postprocess_executor,
            first_summary_push.maybe_send_first_summary_push,
            UID,
            conversation,
            ProcessingTrigger.CAPTURE_END,
        )
    ]


@pytest.mark.parametrize(
    'conversation, first_observation',
    [(_conversation(), False), (_conversation(overview=''), True), (_conversation(discarded=True), True)],
    ids=['regenerated', 'no-summary', 'discarded'],
)
def test_hand_off_queues_nothing_without_a_new_summary(monkeypatch, conversation, first_observation):
    submitted = []
    monkeypatch.setattr(first_summary_push, 'submit_with_context', lambda *args: submitted.append(args))

    first_summary_push.hand_off(UID, conversation, ProcessingTrigger.CAPTURE_END, first_observation=first_observation)

    assert submitted == []
