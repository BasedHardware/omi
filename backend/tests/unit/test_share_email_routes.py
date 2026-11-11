"""Route-level contract tests for the meeting-summary share endpoints.

Drives the real mounted router with only the auth edge overridden, so the
owner-typed recipient bounds and the publish→send→rollback ordering are
exercised through the same code paths the desktop client calls.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from utils.conversations import share_email
from fastapi.testclient import TestClient

from routers import conversations as conversations_router

UID = 'uid-share-email-routes'
CONV_ID = 'conv-share-routes-1'


def _conversation() -> dict:
    return {
        'id': CONV_ID,
        'visibility': 'private',
        'structured': {'title': 'Weekly sync', 'overview': 'Notes'},
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'Weekly sync',
                'calendar_source': 'google_calendar',
                'participants': [
                    {'name': 'Owner', 'email': 'owner@acme.com'},
                    {'name': 'Sarah Chen', 'email': 'sarah@acme.com'},
                ],
            }
        },
    }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[conversations_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_data_layer(monkeypatch):
    state = {'visibility': 'private', 'redis': set(), 'sent': []}

    monkeypatch.setattr(
        conversations_router,
        '_get_valid_conversation_by_id',
        lambda uid, cid, **kw: _conversation() | {'visibility': state['visibility']},
    )
    monkeypatch.setattr(
        conversations_router.share_email,
        'get_user_from_uid',
        lambda uid: {'uid': uid, 'email': 'owner@acme.com', 'display_name': 'Owner'},
    )
    monkeypatch.setattr(
        conversations_router.conversations_db,
        'set_conversation_visibility',
        lambda uid, cid, value: state.__setitem__('visibility', getattr(value, 'value', value)),
    )
    # CAS seams: update_time token 't1'; the guarded write succeeds only while
    # the doc token matches, mirroring Firestore's last_update_time precondition.
    state['doc_token'] = 't1'

    def conditional_publish(uid, cid):
        # Mirrors the precondition semantics: publish only while still private.
        if state['visibility'] in ('shared', 'public'):
            return (False, None)
        state['visibility'] = 'shared'
        state['doc_token'] = 't1'
        return (True, 't1')

    monkeypatch.setattr(
        conversations_router.conversations_db, 'publish_conversation_visibility_if_private', conditional_publish
    )

    def guarded_set(uid, cid, value, last_update_time):
        if last_update_time != state['doc_token']:
            return False
        state['visibility'] = getattr(value, 'value', value)
        return True

    monkeypatch.setattr(conversations_router.conversations_db, 'set_conversation_visibility_if_unchanged', guarded_set)
    monkeypatch.setattr(conversations_router.share_email, 'consume_daily_send_quota', lambda uid, n: True)

    # Two ledgers, same split the Firestore layer keeps: 'in_flight' is a
    # dispatch claim, 'sent' is a delivery that happened.
    state['in_flight'] = []

    def reserve(uid, cid, emails):
        to_dispatch, already_sent, in_flight_elsewhere = [], [], []
        for email in emails:
            if email in state['sent']:
                already_sent.append(email)
            elif email in state['in_flight']:
                in_flight_elsewhere.append(email)
            else:
                to_dispatch.append(email)
                state['in_flight'].append(email)
        return to_dispatch, already_sent, in_flight_elsewhere

    monkeypatch.setattr(conversations_router.conversations_db, 'reserve_share_email_recipients', reserve)

    def confirm(uid, cid, emails):
        for email in emails:
            if email in state['in_flight']:
                state['in_flight'].remove(email)
            if email not in state['sent']:
                state['sent'].append(email)

    monkeypatch.setattr(conversations_router.conversations_db, 'confirm_share_email_recipients', confirm)
    monkeypatch.setattr(
        conversations_router.conversations_db,
        'release_share_email_recipients',
        lambda uid, cid, emails: [state['in_flight'].remove(e) for e in emails if e in state['in_flight']],
    )
    monkeypatch.setattr(
        conversations_router.redis_db, 'store_conversation_to_uid', lambda cid, uid: state['redis'].add(cid)
    )
    monkeypatch.setattr(
        conversations_router.redis_db, 'add_public_conversation', lambda cid: state['redis'].add(f'pub:{cid}')
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        'remove_conversation_to_uid',
        lambda cid: state['redis'].discard(cid),
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        'remove_public_conversation',
        lambda cid: state['redis'].discard(f'pub:{cid}'),
    )
    yield state


def test_share_recipients_excludes_owner():
    response = _client().get(f'/v1/conversations/{CONV_ID}/share-recipients')
    assert response.status_code == 200
    assert response.json() == {'recipients': [{'name': 'Sarah Chen', 'email': 'sarah@acme.com'}]}


def test_share_email_sends_to_an_address_the_owner_typed(monkeypatch, _stub_data_layer):
    """The Share control lets the owner type the recipient, so detection only prefills."""
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: {'sent_to': recipient_emails},
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['someone-not-on-the-invite@acme.com']},
    )
    assert response.status_code == 200
    assert response.json() == {'sent_to': ['someone-not-on-the-invite@acme.com']}
    assert _stub_data_layer['visibility'] == 'shared'


def test_share_email_rejects_an_unusable_address(_stub_data_layer):
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['not-an-email']},
    )
    assert response.status_code == 400
    assert _stub_data_layer['visibility'] == 'private'
    assert _stub_data_layer['redis'] == set()


def test_share_email_rejects_more_than_the_per_send_cap(_stub_data_layer):
    """The request schema owns the cap, so an oversized send never reaches the handler."""
    too_many = [f'p{index}@acme.com' for index in range(share_email.MAX_RECIPIENTS + 1)]
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': too_many},
    )
    assert response.status_code == 422
    assert _stub_data_layer['visibility'] == 'private'
    assert _stub_data_layer['redis'] == set()


def test_share_email_success_publishes_and_sends(monkeypatch, _stub_data_layer):
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: {'sent_to': recipient_emails},
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com', 'SARAH@acme.com']},
    )
    assert response.status_code == 200
    assert response.json() == {'sent_to': ['sarah@acme.com']}
    assert _stub_data_layer['visibility'] == 'shared'
    assert CONV_ID in _stub_data_layer['redis']


def test_share_email_success_emits_summary_shared_telemetry(monkeypatch, _stub_data_layer):
    """Delivered shares feed the admin K-factor; a successful send must emit
    exactly one 'Conversation Summary Shared' event with the delivered count."""
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: {'sent_to': recipient_emails},
    )
    events = []
    monkeypatch.setattr(
        conversations_router,
        'emit_posthog_event',
        lambda distinct_id, event, properties: events.append((distinct_id, event, properties)),
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 200
    assert events == [
        (UID, 'Conversation Summary Shared', {'conversation_id': CONV_ID, 'recipient_count': 1, 'channel': 'email'})
    ]


def test_share_email_failed_send_emits_no_telemetry(monkeypatch, _stub_data_layer):
    def failing_send(*, uid, conversation, recipient_emails):
        raise RuntimeError('email provider rejected the send')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', failing_send)
    events = []
    monkeypatch.setattr(
        conversations_router,
        'emit_posthog_event',
        lambda distinct_id, event, properties: events.append(event),
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 502
    assert events == []


def test_share_email_provider_failure_rolls_back_visibility(monkeypatch, _stub_data_layer):
    def failing_send(*, uid, conversation, recipient_emails):
        raise RuntimeError('email provider rejected the send')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', failing_send)
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 502
    assert _stub_data_layer['visibility'] == 'private'
    assert _stub_data_layer['redis'] == set()


def test_share_email_preserves_public_visibility(monkeypatch, _stub_data_layer):
    public_conversation = _conversation() | {'visibility': 'public'}
    monkeypatch.setattr(
        conversations_router, '_get_valid_conversation_by_id', lambda uid, cid, **kw: public_conversation
    )
    _stub_data_layer['visibility'] = 'public'
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: {'sent_to': recipient_emails},
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 200
    assert _stub_data_layer['visibility'] == 'public'
    assert CONV_ID in _stub_data_layer['redis']


def test_rollback_skipped_when_visibility_changed_concurrently(monkeypatch, _stub_data_layer):
    reads = {'n': 0}

    def evolving_conversation(uid, cid, **kw):
        reads['n'] += 1
        conv = _conversation()
        # First read serves the request; by rollback time the user has made it public.
        conv['visibility'] = 'private' if reads['n'] == 1 else 'public'
        return conv

    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', evolving_conversation)

    def failing_send(*, uid, conversation, recipient_emails):
        # Any real concurrent write moves the doc's update_time as well.
        _stub_data_layer['visibility'] = 'public'
        _stub_data_layer['doc_token'] = 't2-user-made-public'
        raise RuntimeError('email provider rejected the send')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', failing_send)
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 502
    assert _stub_data_layer['visibility'] == 'public'


def test_ambiguous_delivery_returns_504_and_keeps_link_live(monkeypatch, _stub_data_layer):
    from utils.conversations.share_email import AmbiguousDeliveryError

    def ambiguous_send(*, uid, conversation, recipient_emails):
        raise AmbiguousDeliveryError('email delivery status unknown')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', ambiguous_send)
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 504
    assert _stub_data_layer['visibility'] == 'shared'
    assert CONV_ID in _stub_data_layer['redis']


def test_rollback_skipped_when_concurrent_share_wrote_same_value(monkeypatch, _stub_data_layer):
    """A concurrent Copy/Send stores the same 'shared' value; the CAS token is
    voided by that write, so the failed email attempt must not revert it."""

    def failing_send(*, uid, conversation, recipient_emails):
        # Concurrent actor re-shares while the provider call is in flight:
        # value unchanged, but the doc's update_time moves on.
        _stub_data_layer['doc_token'] = 't2-concurrent-writer'
        raise RuntimeError('email provider rejected the send')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', failing_send)
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 502
    assert _stub_data_layer['visibility'] == 'shared'
    assert CONV_ID in _stub_data_layer['redis']


def test_repeat_send_is_idempotent_per_recipient(monkeypatch, _stub_data_layer):
    dispatches = []

    def counting_send(*, uid, conversation, recipient_emails):
        dispatches.append(list(recipient_emails))
        return {'sent_to': recipient_emails}

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', counting_send)
    conv = _conversation()

    def get_conv(uid, cid, **kw):
        conv['visibility'] = _stub_data_layer['visibility']
        conv['share_email_sent_to'] = list(_stub_data_layer['sent'])
        return conv

    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', get_conv)

    first = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    second = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert first.status_code == 200 and second.status_code == 200
    assert second.json() == {'sent_to': ['sarah@acme.com']}
    assert dispatches == [['sarah@acme.com']]


def test_quota_exhaustion_returns_429_without_dispatch(monkeypatch, _stub_data_layer):
    monkeypatch.setattr(conversations_router.share_email, 'consume_daily_send_quota', lambda uid, n: False)
    called = []
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda **kw: called.append(1) or {'sent_to': []},
    )
    response = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert response.status_code == 429
    assert called == []
    assert _stub_data_layer['visibility'] == 'private'


def test_definitive_failure_releases_reservation_for_retry(monkeypatch, _stub_data_layer):
    attempts = []

    def flaky_send(*, uid, conversation, recipient_emails):
        attempts.append(list(recipient_emails))
        if len(attempts) == 1:
            raise RuntimeError('email provider rejected the send')
        return {'sent_to': recipient_emails}

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', flaky_send)
    first = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    second = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert first.status_code == 502
    assert second.status_code == 200
    assert attempts == [['sarah@acme.com'], ['sarah@acme.com']]


def test_ambiguous_failure_keeps_reservation_and_publish(monkeypatch, _stub_data_layer):
    from utils.conversations.share_email import AmbiguousDeliveryError

    def ambiguous_send(*, uid, conversation, recipient_emails):
        raise AmbiguousDeliveryError('email delivery status unknown')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', ambiguous_send)
    response = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert response.status_code == 504
    # Reservation stands: a later duplicate request dispatches nothing.
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda **kw: (_ for _ in ()).throw(AssertionError('must not dispatch')),
    )
    repeat = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert repeat.status_code == 200
    assert _stub_data_layer['visibility'] == 'shared'


def test_publish_infrastructure_failure_releases_reservation_and_quota(monkeypatch, _stub_data_layer):
    refunds = []
    monkeypatch.setattr(conversations_router.share_email, 'refund_daily_send_quota', lambda uid, n: refunds.append(n))

    def broken_redis(cid, uid):
        raise ConnectionError('redis down')

    monkeypatch.setattr(conversations_router.redis_db, 'store_conversation_to_uid', broken_redis)
    dispatched = []
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda **kw: dispatched.append(1) or {'sent_to': kw['recipient_emails']},
    )
    first = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert first.status_code == 502
    assert dispatched == []
    assert refunds == [1]
    assert _stub_data_layer['sent'] == []  # reservation released for retry


def test_concurrent_public_change_before_publish_is_preserved(monkeypatch, _stub_data_layer):
    """User makes the conversation public between our read and the publish:
    the conditional publish yields to it and a failed send must not touch it."""
    # The conversation was private at request time...
    calls = {'n': 0}

    def racing_publish(uid, cid):
        # ...but by publish time another actor already made it public.
        state = _stub_data_layer
        state['visibility'] = 'public'
        return (False, None)

    monkeypatch.setattr(
        conversations_router.conversations_db, 'publish_conversation_visibility_if_private', racing_publish
    )

    def failing_send(*, uid, conversation, recipient_emails):
        raise RuntimeError('email provider rejected the send')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', failing_send)
    response = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert response.status_code == 502
    assert _stub_data_layer['visibility'] == 'public'


def test_publish_contention_with_private_visibility_fails_without_sending(monkeypatch, _stub_data_layer):
    """Unrelated concurrent writes exhaust the CAS retries while visibility
    stays private: the route must fail definitively — no email, reservation
    and quota released — never dispatch a link to a still-private conversation."""
    refunds = []
    monkeypatch.setattr(conversations_router.share_email, 'refund_daily_send_quota', lambda uid, n: refunds.append(n))

    def contended_publish(uid, cid):
        raise RuntimeError('could not publish conversation visibility under contention')

    monkeypatch.setattr(
        conversations_router.conversations_db, 'publish_conversation_visibility_if_private', contended_publish
    )
    dispatched = []
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda **kw: dispatched.append(1) or {'sent_to': kw['recipient_emails']},
    )
    response = _client().post(f'/v1/conversations/{CONV_ID}/share-email', json={'recipient_emails': ['sarah@acme.com']})
    assert response.status_code == 502
    assert dispatched == []
    assert refunds == [1]
    assert _stub_data_layer['sent'] == []


def test_overlapping_request_is_not_told_a_dispatch_in_flight_was_sent(monkeypatch, _stub_data_layer):
    """Request B overlaps A, then A fails definitively.

    B must not be told the mail went out — A's claim was only a dispatch in
    progress, and it released. Nothing was sent, and nothing claimed otherwise.
    """
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda **kw: (_ for _ in ()).throw(RuntimeError('provider rejected')),
    )
    client = _client()

    # A claims the recipient and is mid-dispatch; B arrives while that claim is live.
    _stub_data_layer['in_flight'].append('sarah@acme.com')
    overlapping = client.post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert overlapping.status_code == 409
    assert 'sent_to' not in overlapping.json()

    # A now fails definitively and releases its claim.
    _stub_data_layer['in_flight'].remove('sarah@acme.com')
    assert _stub_data_layer['sent'] == []

    # The retry is the first real dispatch, and it is the only one.
    sends = []
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: sends.append(list(recipient_emails))
        or {'sent_to': recipient_emails},
    )
    retry = client.post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert retry.status_code == 200
    assert retry.json() == {'sent_to': ['sarah@acme.com']}
    assert sends == [['sarah@acme.com']]
    assert _stub_data_layer['sent'] == ['sarah@acme.com']
    assert _stub_data_layer['in_flight'] == []

    # A later repeat is a no-op: the recipient is in the sent ledger now.
    again = client.post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert again.status_code == 200
    assert sends == [['sarah@acme.com']]


def test_failed_dispatch_leaves_nothing_in_the_sent_ledger(monkeypatch, _stub_data_layer):
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda **kw: (_ for _ in ()).throw(RuntimeError('provider rejected')),
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 502
    assert _stub_data_layer['sent'] == []
    assert _stub_data_layer['in_flight'] == []
