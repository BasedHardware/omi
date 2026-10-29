"""One push when an account's first summary is ready.

The decision is made once per account and recorded atomically; the push goes out only for the
account's first summary, never for a summary the reader asked for in the app, and never when
server-side notifications are off.
"""

import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from firebase_admin import messaging
from google.api_core.exceptions import AlreadyExists, ServiceUnavailable

import database.notifications as notification_db
import utils.conversations.first_summary_push as first_summary_push
import utils.notifications as notifications
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.notification_dispatch import NotificationDispatchOutcome, NotificationDispatchStatus, NotificationKind

UID = 'first-summary-owner'
MARKER = ('users', UID, 'notification_markers', 'first_summary_push')


class _Store:
    """Just enough Firestore for the marker: document gets and Firestore's atomic ``create``."""

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
        return SimpleNamespace(exists=self.path in self.store.docs)

    def create(self, data):
        if self.store.write_error is not None:
            raise self.store.write_error
        with self.store.lock:
            if self.path in self.store.docs:
                raise AlreadyExists('document exists')
            self.store.docs[self.path] = dict(data)


def _conversation(
    conversation_id='conv-1', *, title='Weekly product sync with design', overview='We agreed on X.', discarded=False
):
    moment = datetime(2026, 10, 29, 16, 35, tzinfo=timezone.utc)
    return Conversation(
        id=conversation_id,
        created_at=moment,
        started_at=moment,
        finished_at=moment,
        source=ConversationSource.omi,
        structured=Structured(title=title, overview=overview),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=discarded,
    )


@pytest.fixture
def account(monkeypatch):
    store = _Store()
    state = SimpleNamespace(store=store, visible=1, count_calls=0, settings={'enabled': True}, sent=[])

    def count(uid, statuses=None, **kwargs):
        assert (uid, statuses, kwargs) == (UID, ['completed'], {})
        state.count_calls += 1
        return state.visible

    def dispatch(intent):
        state.sent.append(intent)
        return NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=2)

    monkeypatch.setattr(notification_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(first_summary_push.conversations_db, 'get_conversations_count', count)
    monkeypatch.setattr(first_summary_push.users_db, 'get_notification_settings', lambda uid: dict(state.settings))
    monkeypatch.setattr(first_summary_push, 'dispatch_notification', dispatch)
    return state


def _marker(state):
    return state.store.docs.get(MARKER)


def test_first_summary_sends_one_push_that_opens_it(account):
    outcome = first_summary_push.maybe_send_first_summary_push(UID, _conversation(), ProcessingTrigger.CAPTURE_END)

    assert outcome == 'sent'
    assert len(account.sent) == 1
    intent = account.sent[0]
    assert intent.user_id == UID
    assert intent.kind == NotificationKind.FIRST_SUMMARY
    assert intent.title == 'Your first summary is ready'
    assert intent.body == 'Weekly product sync with design'
    assert dict(intent.data) == {
        'type': 'first_summary',
        'conversation_id': 'conv-1',
        'navigate_to': '/conversation/conv-1',
    }
    marker = _marker(account)
    assert marker['outcome'] == 'sent' and marker['conversation_id'] == 'conv-1'


def test_retries_and_later_summaries_never_push_again(account):
    first = _conversation('conv-1')
    assert first_summary_push.maybe_send_first_summary_push(UID, first, ProcessingTrigger.CAPTURE_END) == 'sent'

    # The same conversation retried, then two later summaries on the same account.
    account.visible = 3
    for conversation in (first, _conversation('conv-2'), _conversation('conv-3')):
        outcome = first_summary_push.maybe_send_first_summary_push(UID, conversation, ProcessingTrigger.SYNC_UPDATE)
        assert outcome == 'already_decided'

    assert len(account.sent) == 1
    assert account.count_calls == 1  # decided accounts are never counted again
    assert _marker(account)['conversation_id'] == 'conv-1'


def test_concurrent_first_summaries_push_exactly_once(account, monkeypatch):
    # Both workers read "no marker" before either writes it; Firestore's create picks one winner.
    monkeypatch.setattr(notification_db, 'has_first_summary_push_marker', lambda uid: False)
    start = threading.Barrier(2)
    outcomes = []

    def worker(conversation_id):
        start.wait()
        outcomes.append(
            first_summary_push.maybe_send_first_summary_push(
                UID, _conversation(conversation_id), ProcessingTrigger.CAPTURE_END
            )
        )

    threads = [threading.Thread(target=worker, args=(cid,)) for cid in ('conv-a', 'conv-b')]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ['already_decided', 'sent']
    assert len(account.sent) == 1


def test_notifications_turned_off_get_no_push_and_the_moment_is_spent(account):
    account.settings = {'enabled': False}

    outcome = first_summary_push.maybe_send_first_summary_push(UID, _conversation(), ProcessingTrigger.CAPTURE_END)

    assert outcome == 'notifications_disabled'
    assert account.sent == []
    assert _marker(account)['outcome'] == 'notifications_disabled'

    # Turning notifications back on later does not resurrect a "first" summary push.
    account.settings = {'enabled': True}
    later = first_summary_push.maybe_send_first_summary_push(
        UID, _conversation('conv-2'), ProcessingTrigger.CAPTURE_END
    )
    assert later == 'already_decided'
    assert account.sent == []


def test_existing_account_is_never_told_its_summary_is_the_first(account):
    account.visible = 41

    outcome = first_summary_push.maybe_send_first_summary_push(UID, _conversation(), ProcessingTrigger.CAPTURE_END)

    assert outcome == 'not_first'
    assert account.sent == []
    assert _marker(account)['outcome'] == 'not_first'


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
    outcome = first_summary_push.maybe_send_first_summary_push(UID, _conversation(), trigger)

    assert outcome == 'in_app'
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
    assert first_summary_push.maybe_send_first_summary_push(UID, _conversation(), trigger) == 'sent'
    assert len(account.sent) == 1


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
    outcome = first_summary_push.maybe_send_first_summary_push(UID, conversation, ProcessingTrigger.CAPTURE_END)

    assert outcome == 'no_summary'
    assert account.sent == [] and account.count_calls == 0 and _marker(account) is None


def test_conversation_hidden_from_the_list_leaves_the_decision_open(account):
    account.visible = 0

    outcome = first_summary_push.maybe_send_first_summary_push(UID, _conversation(), ProcessingTrigger.CAPTURE_END)

    assert outcome == 'not_visible'
    assert account.sent == [] and _marker(account) is None


def test_storage_failure_never_pushes(account):
    account.store.write_error = ServiceUnavailable('firestore down')

    outcome = first_summary_push.maybe_send_first_summary_push(UID, _conversation(), ProcessingTrigger.CAPTURE_END)

    assert outcome == 'error'
    assert account.sent == []


def test_untitled_summary_still_says_what_to_do(account):
    first_summary_push.maybe_send_first_summary_push(UID, _conversation(title='  '), ProcessingTrigger.CAPTURE_END)

    assert account.sent[0].body == 'Tap to read it.'


def test_the_fcm_message_is_a_visible_push_that_deep_links_to_the_summary(monkeypatch):
    captured = []
    monkeypatch.setattr(notifications, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(notifications, '_send_messages', lambda messages: captured.extend(messages))
    monkeypatch.setattr(notifications, '_collect_send_results', lambda response, tokens: (len(tokens), []))
    intent = first_summary_push.first_summary_intent(UID, _conversation())

    delivered = notifications.send_notification_result(
        UID, intent.title, intent.body, dict(intent.data), tokens=['ios-token', 'android-token']
    )

    assert delivered == 2
    encoded = [messaging._MessagingService.encode_message(message) for message in captured]
    assert [message['token'] for message in encoded] == ['ios-token', 'android-token']
    for message in encoded:
        assert message['notification'] == {
            'title': 'Your first summary is ready',
            'body': 'Weekly product sync with design',
        }
        assert message['data'] == {
            'type': 'first_summary',
            'conversation_id': 'conv-1',
            'navigate_to': '/conversation/conv-1',
        }
        assert message['android']['notification']['tag'] == message['apns']['headers']['apns-collapse-id']
