from utils.chat_rating_triage import (
    extract_rating_triage_fields,
    normalize_rating_reason,
    parse_notification_kind,
)


def test_parse_notification_kind_from_typed_key():
    metadata = '{"continuityKey":"notification:memory:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}'
    assert parse_notification_kind(metadata) == 'memory'


def test_parse_notification_kind_general_without_kind_segment():
    metadata = {'continuityKey': 'notification:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}
    assert parse_notification_kind(metadata) == 'general'


def test_parse_notification_kind_from_client_message_id():
    assert parse_notification_kind(None, 'notification:suggestion:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee') == 'suggestion'


def test_parse_notification_kind_ignores_non_notification_keys():
    assert parse_notification_kind({'continuityKey': 'voice:abc'}) is None
    assert parse_notification_kind(None, 'desktop-turn-1') is None


def test_extract_rating_triage_fields_copies_kind_and_app_id():
    message = {
        'app_id': 'mentor',
        'metadata': '{"continuityKey":"notification:insight:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}',
        'text': 'never copy this',
    }
    assert extract_rating_triage_fields(message) == {
        'notification_kind': 'insight',
        'app_id': 'mentor',
    }


def test_extract_rating_triage_fields_omits_missing_optional_keys():
    assert extract_rating_triage_fields({'id': 'm1'}) == {}


def test_normalize_rating_reason_accepts_desktop_and_mobile_codes():
    assert normalize_rating_reason('not_about_me') == 'not_about_me'
    assert normalize_rating_reason('too_verbose') == 'too_verbose'
    assert normalize_rating_reason('not_about_me: user typed this') == 'not_about_me'
    assert normalize_rating_reason('free text') is None
    assert normalize_rating_reason(None) is None
