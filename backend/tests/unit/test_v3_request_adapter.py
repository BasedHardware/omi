import pytest

from utils.memory.v3_request_adapter import (
    V3RequestAdapterError,
    adapt_v3_request_parameters,
)


def test_legacy_offset_request_preserves_limit_offset_as_legacy_primary_only():
    adapted = adapt_v3_request_parameters({'limit': '25', 'offset': '50'}, enrolled=False)

    assert adapted.valid is True
    assert adapted.read_mode == 'legacy_primary'
    assert adapted.source == 'legacy_users_uid_memories'
    assert adapted.limit == 25
    assert adapted.offset == 50
    assert adapted.cursor is None
    assert adapted.legacy_primary is True
    assert adapted.v3_cursor_mode is False
    assert adapted.applies_first_page_5000_override is False
    assert adapted.include_archive is False
    assert adapted.archive_authorized is False

    first_page = adapt_v3_request_parameters({'limit': '100', 'offset': '0'}, enrolled=False)
    assert first_page.limit == 5000
    assert first_page.applies_first_page_5000_override is True


def test_memory_cursor_mode_requires_cursor_or_first_page_without_offset_and_never_expands_to_5000():
    first_page = adapt_v3_request_parameters({'limit': '100'}, enrolled=True)

    assert first_page.valid is True
    assert first_page.read_mode == 'default_memory'
    assert first_page.source == 'memory_compatibility_projection'
    assert first_page.limit == 100
    assert first_page.offset is None
    assert first_page.cursor is None
    assert first_page.v3_cursor_mode is True
    assert first_page.legacy_primary is False
    assert first_page.applies_first_page_5000_override is False

    next_page = adapt_v3_request_parameters({'limit': '75', 'cursor': 'opaque.cursor'}, enrolled=True)
    assert next_page.cursor == 'opaque.cursor'
    assert next_page.limit == 75

    for params, reason in [
        ({'limit': '100', 'offset': '0'}, 'offset_not_allowed_in_v3_cursor_mode'),
        ({'limit': '5000'}, 'legacy_first_page_5000_not_allowed_in_v3_cursor_mode'),
        ({'limit': '0'}, 'limit_out_of_range'),
        ({'limit': '501'}, 'limit_out_of_range'),
    ]:
        adapted = adapt_v3_request_parameters(params, enrolled=True)
        assert adapted.valid is False
        assert adapted.fail_closed_reason == reason
        assert adapted.legacy_primary is False


def test_category_and_supported_filters_are_normalized_into_stable_filter_hash_and_cursor_binding():
    adapted = adapt_v3_request_parameters(
        {
            'limit': '50',
            'cursor': 'opaque',
            'category': ' Work ',
            'visibility': 'visible',
            'reviewed': 'false',
        },
        enrolled=True,
    )
    same = adapt_v3_request_parameters(
        {
            'reviewed': 'false',
            'visibility': 'visible',
            'category': 'work',
            'limit': '50',
            'cursor': 'opaque',
        },
        enrolled=True,
    )
    different = adapt_v3_request_parameters(
        {'limit': '50', 'cursor': 'opaque', 'category': 'personal', 'visibility': 'visible', 'reviewed': 'false'},
        enrolled=True,
    )

    assert adapted.valid is True
    assert adapted.category == 'work'
    assert adapted.filters == {'category': 'work', 'reviewed': False, 'visibility': 'visible'}
    assert adapted.filter_hash == same.filter_hash
    assert adapted.cursor_binding['filter_hash'] == adapted.filter_hash
    assert adapted.cursor_binding['source'] == 'memory_compatibility_projection'
    assert adapted.cursor_binding['read_mode'] == 'default_memory'
    assert adapted.filter_hash != different.filter_hash


def test_unsupported_filters_fail_closed_instead_of_silent_fallback():
    for params, reason in [
        ({'limit': '25', 'foo': 'bar'}, 'unsupported_filter'),
        ({'limit': '25', 'visibility': 'private'}, 'unsupported_filter_value'),
        ({'limit': '25', 'reviewed': 'maybe'}, 'unsupported_filter_value'),
        ({'limit': '25', 'source': 'legacy_primary'}, 'unsupported_filter'),
    ]:
        adapted = adapt_v3_request_parameters(params, enrolled=True)
        assert adapted.valid is False
        assert adapted.fail_closed_reason == reason
        assert adapted.should_fetch_legacy is False


def test_include_archive_defaults_false_unavailable_and_explicit_archive_is_blocked_for_v3_default():
    default = adapt_v3_request_parameters({'limit': '25'}, enrolled=True)
    assert default.include_archive is False
    assert default.archive_authorized is False
    assert default.archive_default_available is False

    explicit = adapt_v3_request_parameters({'limit': '25', 'include_archive': 'true'}, enrolled=True)
    assert explicit.valid is False
    assert explicit.fail_closed_reason == 'archive_not_launched_on_v3_default'
    assert explicit.include_archive is True
    assert explicit.archive_authorized is False


def test_invalid_parameter_shapes_fail_closed_without_fastapi_dependency():
    for params, reason in [
        ({'limit': 'abc'}, 'invalid_limit'),
        ({'offset': '-1'}, 'invalid_offset'),
        ({'cursor': ''}, 'malformed_cursor_parameter'),
        ({'include_archive': 'sometimes'}, 'invalid_include_archive'),
    ]:
        adapted = adapt_v3_request_parameters(params, enrolled=True)
        assert adapted.valid is False
        assert adapted.fail_closed_reason == reason

    with pytest.raises(V3RequestAdapterError) as exc:
        adapt_v3_request_parameters({'limit': object()}, enrolled=True, raise_on_invalid=True)
    assert exc.value.reason == 'invalid_limit'
