import zlib
from datetime import datetime, timezone
import database.conversations as conversations_db


def test_prepare_conversation_for_read_standard_corrupt_compressed_falls_back_to_empty_list():
    corrupt_zlib = {
        'id': 'c1',
        'data_protection_level': 'standard',
        'transcript_segments_compressed': True,
        'transcript_segments': b'not-valid-zlib-bytes',
    }
    res1 = conversations_db.prepare_conversation_for_read(corrupt_zlib, 'user-1')
    assert res1['transcript_segments'] == []

    invalid_utf8_zlib = {
        'id': 'c2',
        'data_protection_level': 'standard',
        'transcript_segments_compressed': True,
        'transcript_segments': zlib.compress(b'\xff\xfe\xfd'),
    }
    res2 = conversations_db.prepare_conversation_for_read(invalid_utf8_zlib, 'user-1')
    assert res2['transcript_segments'] == []


def test_conversation_matches_list_predicates_handles_naive_tombstone_timestamps():
    naive_created = datetime(2026, 9, 25, 10, 0, 0)
    aware_start = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)
    aware_end = datetime(2026, 9, 25, 11, 0, 0, tzinfo=timezone.utc)
    assert (
        conversations_db._conversation_matches_list_predicates(
            {'created_at': naive_created, 'discarded': False},
            include_discarded=True,
            statuses=None,
            sources=None,
            categories=None,
            folder_id=None,
            starred=None,
            start_date=aware_start,
            end_date=aware_end,
            date_field='created_at',
        )
        is True
    )


def test_page_eligible_action_item_count_handles_none_structured_and_action_items():
    assert conversations_db._page_eligible_action_item_count({'structured': None}, include_completed=True) == 0
    assert (
        conversations_db._page_eligible_action_item_count(
            {'structured': {'action_items': None}}, include_completed=True
        )
        == 0
    )
