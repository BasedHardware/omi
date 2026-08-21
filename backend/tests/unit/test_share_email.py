"""Unit tests for meeting-summary share recipient detection and email compose."""

from utils.conversations.share_email import (
    MAX_MEETING_PARTICIPANTS,
    build_summary_email,
    extract_share_recipients,
)


def _conversation_with_calendar_context(participants):
    return {
        'id': 'conv-1',
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'Weekly sync',
                'participants': participants,
            }
        },
    }


def test_recipients_exclude_owner_and_dedupe():
    conversation = _conversation_with_calendar_context(
        [
            {'name': 'Nik', 'email': 'nik@basedhardware.com'},
            {'name': 'Sarah Chen', 'email': 'sarah@acme.com'},
            {'name': 'Sarah C', 'email': 'SARAH@acme.com'},
            {'name': None, 'email': 'not-an-email'},
        ]
    )
    recipients = extract_share_recipients(conversation, ['nik@basedhardware.com'])
    assert recipients == [{'name': 'Sarah Chen', 'email': 'sarah@acme.com'}]


def test_no_calendar_identity_means_no_proposal():
    assert extract_share_recipients({'id': 'conv-1'}, ['nik@basedhardware.com']) == []


def test_large_meetings_are_not_proposed():
    participants = [{'name': f'P{i}', 'email': f'p{i}@acme.com'} for i in range(MAX_MEETING_PARTICIPANTS + 1)]
    conversation = _conversation_with_calendar_context(participants)
    assert extract_share_recipients(conversation, []) == []


def test_google_calendar_event_attendee_emails_are_recipients():
    conversation = {
        'id': 'conv-1',
        'calendar_event': {
            'event_id': 'evt-2',
            'title': 'Planning',
            'attendees': ['Nik', 'Jordan Lee'],
            'attendee_emails': ['nik@basedhardware.com', 'jordan@acme.com'],
        },
    }
    recipients = extract_share_recipients(conversation, ['nik@basedhardware.com'])
    assert recipients == [{'name': 'Jordan Lee', 'email': 'jordan@acme.com'}]


def test_build_summary_email_escapes_and_links():
    content = build_summary_email(
        sender_name='Nik <admin>',
        conversation_title='Roadmap & hiring',
        overview='Line one\nLine two',
        share_url='https://h.omi.me/conversations/conv-1',
    )
    assert content['subject'] == 'Meeting notes: Roadmap & hiring'
    assert 'Nik &lt;admin&gt;' in content['html']
    assert 'Roadmap &amp; hiring' in content['html']
    assert 'Line one<br>Line two' in content['html']
    assert 'https://h.omi.me/conversations/conv-1' in content['html']


def test_publish_then_send_rolls_back_on_failure():
    from utils.conversations.share_email import publish_then_send

    calls = []

    def failing_send():
        calls.append('send')
        raise RuntimeError('provider down')

    try:
        publish_then_send(
            publish=lambda: calls.append('publish'),
            unpublish=lambda: calls.append('unpublish'),
            send=failing_send,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError('expected RuntimeError to propagate')
    assert calls == ['publish', 'send', 'unpublish']


def test_publish_then_send_keeps_publish_on_success():
    from utils.conversations.share_email import publish_then_send

    calls = []
    result = publish_then_send(
        publish=lambda: calls.append('publish'),
        unpublish=lambda: calls.append('unpublish'),
        send=lambda: {'sent_to': ['a@b.co']},
    )
    assert calls == ['publish']
    assert result == {'sent_to': ['a@b.co']}


def test_publish_then_send_rolls_back_partial_publish_failure():
    from utils.conversations.share_email import publish_then_send

    calls = []

    def partially_failing_publish():
        calls.append('publish-db-write')
        raise ConnectionError('redis down')

    try:
        publish_then_send(
            publish=partially_failing_publish,
            unpublish=lambda: calls.append('unpublish'),
            send=lambda: calls.append('send'),
        )
    except ConnectionError:
        pass
    else:
        raise AssertionError('expected ConnectionError to propagate')
    assert calls == ['publish-db-write', 'unpublish']


def test_normalized_recipient_emails_dedupes_preserving_order():
    from utils.conversations.share_email import normalized_recipient_emails

    result = normalized_recipient_emails(['B@acme.com', 'a@acme.com', 'b@acme.com', 'not-an-email', 'A@ACME.COM'])
    assert result == ['b@acme.com', 'a@acme.com']


def test_ambiguous_delivery_keeps_publish():
    from utils.conversations.share_email import AmbiguousDeliveryError, publish_then_send

    calls = []

    def ambiguous_send():
        calls.append('send')
        raise AmbiguousDeliveryError('email delivery status unknown')

    try:
        publish_then_send(
            publish=lambda: calls.append('publish'),
            unpublish=lambda: calls.append('unpublish'),
            send=ambiguous_send,
        )
    except AmbiguousDeliveryError:
        pass
    else:
        raise AssertionError('expected AmbiguousDeliveryError to propagate')
    assert calls == ['publish', 'send']


def test_read_timeout_maps_to_ambiguous_and_connect_failure_to_definitive(monkeypatch):
    import httpx

    from utils.conversations import share_email as se

    monkeypatch.setenv('RESEND_API_KEY', 'test-key')
    monkeypatch.setattr(se, 'get_user_from_uid', lambda uid: {'email': 'owner@acme.com', 'display_name': 'Owner'})
    conversation = {'id': 'c1', 'structured': {'title': 'T', 'overview': 'O'}}

    def raise_read_timeout(*a, **kw):
        raise httpx.ReadTimeout('read timed out')

    monkeypatch.setattr(se.httpx, 'post', raise_read_timeout)
    try:
        se.send_summary_email(uid='u1', conversation=conversation, recipient_emails=['a@b.co'])
    except se.AmbiguousDeliveryError:
        pass
    else:
        raise AssertionError('read timeout must be ambiguous')

    def raise_connection_error(*a, **kw):
        raise httpx.ConnectError('refused')

    monkeypatch.setattr(se.httpx, 'post', raise_connection_error)
    try:
        se.send_summary_email(uid='u1', conversation=conversation, recipient_emails=['a@b.co'])
    except se.AmbiguousDeliveryError:
        raise AssertionError('connection failure is definitive, not ambiguous')
    except RuntimeError:
        pass


def test_quota_redis_outage_fails_open_and_records_fallback(monkeypatch):
    from utils.conversations import share_email as se

    class BrokenRedis:
        def incrby(self, *a, **kw):
            raise ConnectionError('redis down')

    import database.redis_db as redis_db

    monkeypatch.setattr(redis_db, 'r', BrokenRedis())
    events = []
    import utils.observability.fallback as fallback

    monkeypatch.setattr(fallback, 'record_fallback', lambda **kw: events.append(kw))
    assert se.consume_daily_send_quota('uid-1', 1) is True
    assert len(events) == 1
    assert events[0]['to_mode'] == 'quota_bypassed'
