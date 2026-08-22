"""Unit tests for meeting-summary share recipient detection and email compose."""

from utils.conversations.share_email import (
    MAX_MEETING_PARTICIPANTS,
    build_summary_email,
    extract_share_recipients,
)


def _conversation_with_calendar_context(participants, calendar_source='google_calendar'):
    context = {
        'calendar_event_id': 'evt-1',
        'title': 'Weekly sync',
        'participants': participants,
    }
    if calendar_source is not None:
        context['calendar_source'] = calendar_source
    return {'id': 'conv-1', 'external_data': {'calendar_meeting_context': context}}


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


def test_unnamed_participant_is_not_proposed():
    """A bare address is an unknown person: one click must not mail it."""
    conversation = _conversation_with_calendar_context(
        [
            {'name': 'Nik', 'email': 'nik@basedhardware.com'},
            {'name': '  ', 'email': 'unknown@acme.com'},
            {'email': 'noname@acme.com'},
        ]
    )
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == []


def test_unresolved_owner_suppresses_the_whole_proposal(monkeypatch):
    """#12017: without a known owner address the owner looks like a recipient."""
    import utils.conversations.share_email as se
    import utils.observability.fallback as fallback

    events = []
    monkeypatch.setattr(fallback, 'record_fallback', lambda **kw: events.append(kw))
    monkeypatch.setattr(se, 'get_user_from_uid', lambda uid: {'uid': uid, 'email': None})

    conversation = _conversation_with_calendar_context(
        [
            {'name': 'David Zhang', 'email': 'david@scalingforever.com'},
            {'name': 'Sarah Chen', 'email': 'sarah@acme.com'},
        ]
    )
    assert se.get_share_recipients('uid-1', conversation) == []
    assert events and events[0]['to_mode'] == 'share_recipients_suppressed'


def test_resolved_owner_still_proposes_the_other_participant(monkeypatch):
    import utils.conversations.share_email as se

    monkeypatch.setattr(se, 'get_user_from_uid', lambda uid: {'uid': uid, 'email': 'David@ScalingForever.com'})
    conversation = _conversation_with_calendar_context(
        [
            {'name': 'David Zhang', 'email': 'david@scalingforever.com'},
            {'name': 'Sarah Chen', 'email': 'sarah@acme.com'},
        ]
    )
    assert se.get_share_recipients('uid-1', conversation) == [{'name': 'Sarah Chen', 'email': 'sarah@acme.com'}]


def test_sender_name_falls_back_to_the_address_local_part():
    import utils.conversations.share_email as se

    assert se._sender_display_name({'display_name': 'David Zhang'}) == 'David Zhang'
    assert se._sender_display_name({'display_name': None, 'email': 'david@scalingforever.com'}) == 'david'
    assert se._sender_display_name({}) == 'Someone'


def test_google_attendee_without_display_name_is_not_proposed():
    """extract_attendees stores a nameless attendee as name==email; that is not a captured name."""
    conversation = {
        'id': 'conv-1',
        'calendar_event': {
            'event_id': 'evt-3',
            'title': 'Intro call',
            # Shape produced by utils.conversations.calendar_utils.extract_attendees
            # when the attendee has no displayName.
            'attendees': ['jordan@acme.com', 'Sam Rivera'],
            'attendee_emails': ['jordan@acme.com', 'sam@acme.com'],
        },
    }
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
        {'name': 'Sam Rivera', 'email': 'sam@acme.com'}
    ]


def test_local_part_stand_in_name_is_not_proposed():
    conversation = _conversation_with_calendar_context(
        [
            {'name': 'Nik', 'email': 'nik@basedhardware.com'},
            {'name': 'JORDAN', 'email': 'jordan@acme.com'},
        ]
    )
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == []


def test_screen_derived_identity_is_never_a_share_recipient():
    """#12036: OCR of the conferencing window saw a calendar tile for a later meeting."""
    conversation = {
        'id': 'conv-1',
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'screen-activity',
                'title': 'Video meeting',
                'calendar_source': 'screen_activity',
                'participants': [
                    {'name': 'Aryan Gupta and Nik', 'email': 'nik@basedhardware.com'},
                    {'name': 'Aryan Gupta', 'email': 'aryan@example.com'},
                ],
            }
        },
    }
    assert extract_share_recipients(conversation, ['kodjima33@gmail.com']) == []


def test_calendar_backed_sources_still_propose():
    for source in ('system_calendar', 'macos_calendar', 'google', 'google_calendar', 'outlook_calendar'):
        conversation = {
            'id': 'conv-1',
            'external_data': {
                'calendar_meeting_context': {
                    'calendar_event_id': 'evt-1',
                    'title': 'Weekly sync',
                    'calendar_source': source,
                    'participants': [
                        {'name': 'Nik', 'email': 'nik@basedhardware.com'},
                        {'name': 'Sarah Chen', 'email': 'sarah@acme.com'},
                    ],
                }
            },
        }
        assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
            {'name': 'Sarah Chen', 'email': 'sarah@acme.com'}
        ], source


def test_unlabelled_context_source_is_not_trusted():
    conversation = _conversation_with_calendar_context(
        [{'name': 'Sarah Chen', 'email': 'sarah@acme.com'}], calendar_source=None
    )
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == []


def _calendar_link_conversation(people, *, also_as_calendar_event):
    """The real production shape: a Google calendar link plus, optionally, the
    same meeting repeated as `calendar_event`.

    `context_from_calendar_link` emits each attendee twice — once name-only,
    once email-only — so this is the boundary where naive counting doubles.
    """
    from datetime import datetime, timezone

    from models.conversation import CalendarEventLink
    from utils.conversations.meeting_context import context_from_calendar_link

    link = CalendarEventLink(
        event_id='evt-1',
        title='Weekly sync',
        attendees=[name for name, _ in people],
        attendee_emails=[email for _, email in people],
        start_time=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 22, 15, 30, tzinfo=timezone.utc),
    )
    context = context_from_calendar_link(link).model_dump()
    conversation = {'id': 'conv-1', 'external_data': {'calendar_meeting_context': context}}
    if also_as_calendar_event:
        conversation['calendar_event'] = {
            'event_id': 'evt-1',
            'title': 'Weekly sync',
            'attendees': [name for name, _ in people],
            'attendee_emails': [email for _, email in people],
        }
    return conversation


def test_calendar_link_shape_counts_each_attendee_once():
    """context_from_calendar_link emits 6 name-only + 6 email-only entries for 6 people."""
    people = [('Nik', 'nik@basedhardware.com')] + [(f'Person {i}', f'p{i}@acme.com') for i in range(5)]
    conversation = _calendar_link_conversation(people, also_as_calendar_event=False)
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
        {'name': name, 'email': email} for name, email in people[1:]
    ]


def test_calendar_link_shape_combined_with_calendar_event_stays_eligible():
    people = [('Nik', 'nik@basedhardware.com')] + [(f'Person {i}', f'p{i}@acme.com') for i in range(5)]
    conversation = _calendar_link_conversation(people, also_as_calendar_event=True)
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
        {'name': name, 'email': email} for name, email in people[1:]
    ]


def test_genuinely_oversized_meeting_is_still_suppressed_in_that_shape():
    people = [(f'Person {i}', f'p{i}@acme.com') for i in range(MAX_MEETING_PARTICIPANTS + 1)]
    conversation = _calendar_link_conversation(people, also_as_calendar_event=True)
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == []


def test_meeting_present_in_both_calendar_representations_is_counted_once():
    """The same six people in both shapes must not read as twelve attendees."""
    people = [(f'Person {i}', f'p{i}@acme.com') for i in range(5)]
    conversation = {
        'id': 'conv-1',
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'Weekly sync',
                'calendar_source': 'google_calendar',
                'participants': [{'name': 'Nik', 'email': 'nik@basedhardware.com'}]
                + [{'name': name, 'email': email} for name, email in people],
            }
        },
        'calendar_event': {
            'event_id': 'evt-1',
            'title': 'Weekly sync',
            'attendees': ['Nik'] + [name for name, _ in people],
            'attendee_emails': ['nik@basedhardware.com'] + [email for _, email in people],
        },
    }
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
        {'name': name, 'email': email} for name, email in people
    ]


def test_duplicate_representations_still_respect_the_size_gate():
    people = [{'name': f'P{i}', 'email': f'p{i}@acme.com'} for i in range(MAX_MEETING_PARTICIPANTS + 1)]
    conversation = {
        'id': 'conv-1',
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'All hands',
                'calendar_source': 'google_calendar',
                'participants': people,
            }
        },
        'calendar_event': {
            'event_id': 'evt-1',
            'title': 'All hands',
            'attendees': [p['name'] for p in people],
            'attendee_emails': [p['email'] for p in people],
        },
    }
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == []


def test_same_address_spelled_differently_across_sources_is_one_person():
    """A 10-person meeting must survive each source spelling a name its own way."""
    people = [('Nik', 'nik@basedhardware.com')] + [(f'Person {i}', f'p{i}@acme.com') for i in range(9)]
    conversation = {
        'id': 'conv-1',
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'All hands',
                'calendar_source': 'google_calendar',
                'participants': [{'name': name, 'email': email} for name, email in people],
            }
        },
        'calendar_event': {
            'event_id': 'evt-1',
            'title': 'All hands',
            # Same ten addresses, every display name spelled differently.
            'attendees': [f'{name} Alt' for name, _ in people],
            'attendee_emails': [email for _, email in people],
        },
    }
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
        {'name': name, 'email': email} for name, email in people[1:6]
    ]


def test_legacy_unpaired_context_counts_each_person_once():
    """Conversations stored before attendees were paired hold name-only + email-only entries."""
    people = [(f'Person {i}', f'p{i}@acme.com') for i in range(6)]
    conversation = {
        'id': 'conv-1',
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'Weekly sync',
                'calendar_source': 'google',
                'participants': [{'name': name} for name, _ in people] + [{'email': email} for _, email in people],
            }
        },
        'calendar_event': {
            'event_id': 'evt-1',
            'title': 'Weekly sync',
            'attendees': [name for name, _ in people],
            'attendee_emails': [email for _, email in people],
        },
    }
    assert extract_share_recipients(conversation, ['nik@basedhardware.com']) == [
        {'name': name, 'email': email} for name, email in people[:5]
    ]
