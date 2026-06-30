import pytest

from utils.memory.v3_cursor import (
    V3CursorContext,
    V3CursorError,
    V3Keyset,
    create_v3_cursor,
    parse_v3_cursor,
    validate_v3_cursor_request,
)

SECRET = b'unit-test-memory-v3-cursor-secret'


def _context(**overrides):
    values = {
        'uid': 'uid-a',
        'account_generation': 7,
        'projection_generation': 11,
        'filter_hash': 'filter-default-v1',
        'source': 'memory_compatibility_projection',
        'read_mode': 'default_memory',
        'now_epoch_seconds': 1_800_000_000,
    }
    values.update(overrides)
    return V3CursorContext(**values)


def test_cursor_round_trips_as_opaque_hmac_signed_keyset_bound_to_generation_filter_source_and_mode():
    keyset = V3Keyset(created_at_ms=1_799_999_123_456, memory_id='memory-9')

    cursor = create_v3_cursor(keyset, _context(), SECRET, ttl_seconds=300)
    parsed = parse_v3_cursor(cursor, _context(), SECRET)

    assert parsed.keyset == keyset
    assert parsed.uid == 'uid-a'
    assert parsed.account_generation == 7
    assert parsed.projection_generation == 11
    assert parsed.filter_hash == 'filter-default-v1'
    assert parsed.source == 'memory_compatibility_projection'
    assert parsed.read_mode == 'default_memory'
    assert parsed.expires_at_epoch_seconds == 1_800_000_300
    assert parsed.keyset_order == ('created_at_desc', 'memory_id_desc')
    assert cursor.startswith('v3.')
    assert 'uid-a' not in cursor
    assert 'memory-9' not in cursor
    assert 'created_at_ms' not in cursor


def test_cursor_rejects_tampering_expiry_wrong_user_generation_filter_source_or_read_mode():
    cursor = create_v3_cursor(
        V3Keyset(created_at_ms=1_799_999_123_456, memory_id='memory-9'),
        _context(),
        SECRET,
        ttl_seconds=300,
    )

    tampered = cursor[:-1] + ('A' if cursor[-1] != 'A' else 'B')
    invalid_cases = [
        (tampered, _context(), 'invalid_signature'),
        (cursor, _context(now_epoch_seconds=1_800_000_301), 'cursor_expired'),
        (cursor, _context(uid='uid-b'), 'uid_mismatch'),
        (cursor, _context(account_generation=8), 'account_generation_mismatch'),
        (cursor, _context(projection_generation=12), 'projection_generation_mismatch'),
        (cursor, _context(filter_hash='filter-category-work'), 'filter_hash_mismatch'),
        (cursor, _context(source='legacy_primary'), 'source_mismatch'),
        (cursor, _context(read_mode='archive'), 'read_mode_mismatch'),
    ]

    for token, context, reason in invalid_cases:
        with pytest.raises(V3CursorError) as exc:
            parse_v3_cursor(token, context, SECRET)
        assert exc.value.reason == reason


def test_cursor_request_validation_disallows_offset_and_legacy_first_page_5000_override_in_memory_mode():
    request = validate_v3_cursor_request(limit=100, cursor=None, offset=None)

    assert request.cursor is None
    assert request.limit == 100
    assert request.allows_offset is False
    assert request.applies_first_page_5000_override is False

    for kwargs, reason in [
        ({'limit': 100, 'cursor': None, 'offset': 0}, 'offset_not_allowed_in_v3_cursor_mode'),
        ({'limit': 100, 'cursor': 'opaque', 'offset': 25}, 'offset_not_allowed_in_v3_cursor_mode'),
        ({'limit': 5000, 'cursor': None, 'offset': None}, 'legacy_first_page_5000_not_allowed_in_v3_cursor_mode'),
    ]:
        with pytest.raises(V3CursorError) as exc:
            validate_v3_cursor_request(**kwargs)
        assert exc.value.reason == reason


def test_cursor_parser_is_pure_local_and_fails_closed_for_malformed_or_unsupported_tokens():
    for token in ['', 'legacy-offset-25', 'v3.not-json.not-sig', 'v3.payload.signature.extra']:
        with pytest.raises(V3CursorError) as exc:
            parse_v3_cursor(token, _context(), SECRET)
        assert exc.value.reason in {'malformed_cursor', 'invalid_signature'}
