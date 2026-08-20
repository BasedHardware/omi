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
