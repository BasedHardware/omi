"""Owner-feedback regressions for complete, bounded external reads (synthetic data)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import FailedPrecondition

import database.daily_summaries as summary_db
import database.mcp_memory_queries as memory_queries
import utils.mcp_memory_reads as memory_reads
from utils.daily_summary_read_contract import union_interval_minutes, screen_observation_minutes, summary_read_payload
from utils.mcp_data import clean_action_item
import utils.mcp_dates as dates
from utils.mcp_dates import local_date_window, offset_timestamp, resolve_timezone
from utils.mcp_server.handlers import conversations, memories, other
from utils.mcp_server.helpers import bounded_transcript_segments, conversation_card, public_transcript_timing
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.payloads import tool_response_serialized_chars
from utils.mcp_server.constants import MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
from utils.other.list_budget import ListReadBudgetExhausted

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
OWNER = 'synthetic-owner'


def card(cid, text='x'):
    return {
        'id': cid,
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW + timedelta(minutes=10),
        'structured': {'title': 'Synthetic', 'overview': text},
        'transcript_segments': [{'text': text, 'start': 0, 'end': 60}],
    }


@pytest.mark.parametrize(
    'start,end,expected',
    [
        (-285.0, -42.0, (0.0, 0.0)),
        ('-285', '-42', (0, 0)),
        (-0.25, 1.5, (0.0, 1.5)),
        ('-0.25', 1.5, (0, 1.5)),
        (0, 2, (0, 2)),
        (1.25, 3.5, (1.25, 3.5)),
    ],
)
def test_mcp_read_clamps_pre_origin_offsets_without_changing_storage(start, end, expected):
    source = [{'id': 'synthetic-segment', 'text': 'synthetic', 'speaker_id': 0, 'start': start, 'end': end}]
    projected, truncated = bounded_transcript_segments(source, max_segments=10, max_chars=100)
    assert (projected[0]['start'], projected[0]['end']) == expected
    assert projected[0]['text'] == 'synthetic'
    assert source[0]['start'] == start and source[0]['end'] == end
    assert not truncated


def test_mcp_pre_origin_projection_preserves_fetch_bounds_and_conversation_origin(monkeypatch):
    stored = card('synthetic-conversation')
    stored['transcript_segments'] = [
        {'text': 'before', 'start': -10, 'end': -2},
        {'text': 'crossing', 'start': -1, 'end': 2},
        {'text': 'after', 'start': 2, 'end': 3},
    ]
    monkeypatch.setattr(conversations, 'fetch_conversation_for_detail', lambda *a, **k: stored)
    result = conversations.get_conversation_by_id(
        OWNER, {'conversation_id': stored['id'], 'max_segments': 2, 'max_chars': 100}
    )
    projected = result['conversation']
    assert result['truncated']
    assert projected['started_at'] == stored['started_at']
    assert [(s['start'], s['end']) for s in projected['transcript_segments']] == [(0, 0), (0, 2)]
    assert stored['transcript_segments'][0]['start'] == -10


def test_mcp_pre_origin_projection_keeps_text_budget():
    source = [{'text': 'synthetic', 'start': -10, 'end': -2}, {'text': 'later', 'start': 1, 'end': 2}]
    projected, truncated = bounded_transcript_segments(source, max_segments=10, max_chars=5)
    assert truncated and len(projected) == 1
    assert len(projected[0]['text']) <= 5
    assert projected[0]['start'] == projected[0]['end'] == 0


def test_mcp_snippet_seconds_and_milliseconds_use_the_same_nonnegative_projection():
    source = {'text': 'synthetic', 'start': -2.5, 'end': 1.25, 'start_ms': -2500, 'end_ms': 1250}
    projected = public_transcript_timing(source)
    assert projected == {'text': 'synthetic', 'start': 0, 'end': 1.25, 'start_ms': 0, 'end_ms': 1250}
    assert source['start'] == -2.5 and source['start_ms'] == -2500


@pytest.mark.parametrize('unknown', [None, False, 'unplaced'])
def test_mcp_timing_projection_does_not_invent_unknown_clock_metadata(unknown):
    source = {'text': 'synthetic', 'start': unknown, 'end': 1.25}
    assert public_transcript_timing(source) == source


def test_updated_filter_runs_before_the_old_200_row_scan(monkeypatch):
    rows = [{'id': 'new', 'content': 'Synthetic fact', 'updated_at': NOW, 'created_at': NOW}]
    read = MagicMock(return_value=(rows, 237))
    monkeypatch.setattr(memories, 'read_filtered_mcp_memories', read)
    result = memories.memories_page_core(OWNER, limit=20, updated_after=NOW, cursor_kind='test')
    assert result['memories'] == rows
    assert not result['has_more'] and not result['scan_truncated']
    assert result['scanned_count'] == 237 and result['matched_count'] == 1
    assert read.call_args.kwargs['filters']['updated_after'] == NOW


def test_filtered_page_lookahead_and_cursor_are_truthful(monkeypatch):
    monkeypatch.setattr(
        memories, 'read_filtered_mcp_memories', lambda *a, **k: ([{'id': str(i)} for i in range(3)], 300)
    )
    args = dict(limit=2, updated_after=NOW, cursor_kind='test')
    first = memories.memories_page_core(OWNER, **args)
    second = memories.memories_page_core(OWNER, cursor_token=first['next_cursor'], **args)
    assert first['more_in_window'] is True
    assert [r['id'] for r in second['memories']] == ['2']
    assert second['more_in_window'] is False


def test_memory_candidate_date_bound_is_in_firestore(monkeypatch):
    query = MagicMock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = []
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = query
    assert (
        memory_queries.read_mcp_memory_candidates(
            OWNER, origin='memory_items', filters={'updated_after': NOW}, firestore_client=client
        )
        == []
    )
    predicate = query.where.call_args.kwargs['filter']
    assert predicate.field_path == 'updated_at' and predicate.value == NOW and predicate.op_string == '>='


def test_memory_index_fallback_preserves_date_bound(monkeypatch):
    query = MagicMock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.side_effect = [FailedPrecondition('index not ready'), []]
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = query
    monkeypatch.setattr(memory_queries, 'record_fallback', MagicMock())
    assert (
        memory_queries.read_mcp_memory_candidates(
            OWNER, origin='memory_items', filters={'updated_after': NOW}, firestore_client=client
        )
        == []
    )
    assert all(call.kwargs['filter'].value == NOW for call in query.where.call_args_list)
    memory_queries.record_fallback.assert_called_once()


def test_exhausted_filter_window_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(memory_reads, 'read_mcp_memory_candidates', lambda *a, **k: [object()] * 5001)
    with pytest.raises(ToolExecutionError, match='memory_filter_window_exceeded'):
        memory_reads.collect_filtered_mcp_memories(SimpleNamespace(db_client=object()), OWNER, filters={})


def test_batch_honors_twenty_ids_under_large_unicode_payload(monkeypatch):
    ids = [f'conversation-{i}' for i in range(20)]
    monkeypatch.setattr(
        conversations.conversations_db,
        'get_mcp_conversations_by_id',
        lambda *a, **k: [card(cid, '漢' * 24000) for cid in ids],
    )
    result = conversations.get_conversations_by_ids(OWNER, {'conversation_ids': ids})
    assert [item['id'] for item in result['conversations']] == ids
    assert result['omitted_ids'] == []
    assert result['truncated'] is True
    assert tool_response_serialized_chars(result) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
    for item in result['conversations']:
        assert item['structured'] == item['conversation']['structured']


def test_batch_pathological_metadata_accounts_for_omissions_and_resumes(monkeypatch):
    ids = ['first', 'second', 'third']
    rows = [card(cid) for cid in ids]
    for row in rows:
        row['transcript_segments'] = [
            {'text': 'x', 'speaker_id': i, 'person_id': str(i), 'start': 0, 'end': 1} for i in range(100)
        ]
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', lambda *a, **k: rows)
    monkeypatch.setattr(conversations, 'MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS', 70000)
    first = conversations.get_conversations_by_ids(OWNER, {'conversation_ids': ids})
    returned = [item['id'] for item in first['conversations']]
    assert set(returned) | set(first['omitted_ids']) == set(ids)
    assert first['omitted_ids'] and first['next_cursor']
    second = conversations.get_conversations_by_ids(OWNER, {'conversation_ids': ids, 'cursor': first['next_cursor']})
    assert second['conversations'][0]['id'] == first['omitted_ids'][0]


def test_prefix_not_found_has_full_id_hint(monkeypatch):
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', lambda *a, **k: [])
    result = conversations.get_conversations_by_ids(OWNER, {'conversation_ids': ['12345678']})
    assert result['not_found'] == ['12345678']
    assert 'full id' in result['not_found_hint']
    with pytest.raises(ToolExecutionError, match='full id'):
        conversations.get_conversation_by_id(OWNER, {'conversation_id': '12345678'})


def test_summary_only_and_fields_work_in_batch(monkeypatch):
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', lambda *a, **k: [card('a')])
    result = conversations.get_conversations_by_ids(
        OWNER, {'conversation_ids': ['a'], 'summary_only': True, 'fields': ['structured']}
    )
    assert set(result['conversations'][0]['conversation']) == {'id', 'structured'}
    assert 'transcript_segments' not in result['conversations'][0]


@pytest.mark.parametrize(
    'context',
    [
        {
            'external_data': {
                'calendar_meeting_context': {
                    'meeting_link': 'https://meet.google.com/synthetic',
                    'calendar_event_id': 'synthetic-event',
                }
            }
        },
        {
            'calendar_meeting_context': {
                'meeting_url': 'https://meet.google.com/synthetic',
                'event_id': 'synthetic-event',
            }
        },
        {'calendar_event': {'url': 'https://meet.google.com/synthetic', 'id': 'synthetic-event'}},
    ],
)
def test_call_metadata_accepts_both_existing_context_shapes(context):
    result = conversation_card({**card('a'), **context})
    assert result['is_call'] is True
    assert result['call_platform'] == 'google_meet'
    assert result['calendar_event_id'] == 'synthetic-event'


def test_call_unknown_is_not_inferred_as_in_person():
    assert conversation_card(card('a'))['is_call'] is None


@pytest.mark.parametrize(
    'raw, source',
    [
        ({'conversation_id': 'a'}, 'conversation'),
        ({'source': 'manual'}, 'manual'),
        ({'chat_session_id': 'b'}, 'chat'),
        ({}, 'unknown'),
    ],
)
def test_action_item_provenance(raw, source):
    assert clean_action_item(raw)['source'] == source


def test_timezone_covers_local_midnight_and_returns_offset():
    start, end, zone = local_date_window(OWNER, '2026-10-22', '2026-10-22', 'Asia/Ho_Chi_Minh')
    assert start == datetime(2026, 10, 21, 17, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 22, 16, 59, 59, 999999, tzinfo=timezone.utc)
    assert offset_timestamp(start, zone) == '2026-10-22T00:00:00+07:00'


def test_timezone_dst_and_released_utc_default():
    start, end, zone = local_date_window(OWNER, '2026-11-01', '2026-11-01', 'America/New_York')
    assert (end - start + timedelta(microseconds=1)).total_seconds() == 25 * 3600
    assert str(resolve_timezone(OWNER)) == 'UTC'
    with pytest.raises(ToolExecutionError, match='Invalid timezone'):
        resolve_timezone(OWNER, 'Invalid/Timezone')


def test_group_by_reads_whole_window_not_two_hundred_row_page(monkeypatch):
    rows = [{'timestamp': f'2026-10-22 {i // 60:02d}:{i % 60:02d}:00.000', 'appName': 'Synthetic'} for i in range(500)]
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *a, **k: rows)
    result = other.get_screen_activity(
        OWNER, {'start_date': '2026-10-22', 'end_date': '2026-10-22', 'group_by': 'day', 'limit': 200}
    )
    assert result['buckets'][0]['count'] == 500
    assert result['coverage']['complete_window'] is True
    assert 'next_cursor' not in result


def test_group_by_local_hour_has_offset_and_reports_truncation(monkeypatch):
    rows = [{'timestamp': '2026-10-21 18:00:00.000', 'appName': 'Synthetic'}] * 5001
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *a, **k: rows)
    result = other.get_screen_activity(OWNER, {'group_by': 'hour', 'timezone': 'Asia/Ho_Chi_Minh'})
    assert result['buckets'][0]['hour'] == '2026-10-22T01:00:00+07:00'
    assert result['coverage']['truncated'] is True
    assert result['buckets'][0]['count'] == 5000


def test_daily_payload_counters_and_coverage_explain_legacy_subsets():
    result = summary_read_payload(
        {
            'date': '2026-10-22',
            'created_at': NOW,
            'stats': {'memories_created': 9, 'action_items_created': 3, 'watching_minutes': 2473},
            'memories_learned': [],
            'action_items': [],
        }
    )
    assert result['stats']['action_items_created'] == result['stats']['action_items_count'] == 0
    assert result['stats']['stored_action_items_created'] == 3
    assert result['stats']['watching_minutes'] == 1440
    assert 'review_selection' in result['memories_learned_coverage']
    assert result['stats']['memories_learned_count'] == 0
    assert result['generated_at'] == NOW


def test_union_clips_at_local_day_and_deduplicates_devices():
    start, end, _ = local_date_window(OWNER, '2026-10-22', '2026-10-22', 'Asia/Ho_Chi_Minh')
    assert (
        union_interval_minutes(
            [(start - timedelta(hours=1), start + timedelta(hours=2)), (start, start + timedelta(hours=3))], start, end
        )
        == 180
    )
    assert union_interval_minutes([(start - timedelta(days=1), end + timedelta(days=1))], start, end) == 1440


def test_screen_observation_union_deduplicates_device_intervals():
    rows = [
        {'timestamp': f'2026-10-22 00:0{i}:00.000', 'clientDeviceId': device} for i in range(3) for device in ('a', 'b')
    ]
    assert screen_observation_minutes(rows, NOW, NOW + timedelta(days=1)) == 2


def test_true_daily_count_is_an_aggregation_without_list_limit(monkeypatch):
    query = MagicMock()
    query.where.return_value = query
    query.count.return_value.get.return_value = [[SimpleNamespace(value=137)]]
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = query
    assert summary_db.get_day_recording_count(OWNER, NOW, NOW + timedelta(days=1), firestore_client=client) == 137
    query.limit.assert_not_called()
    query.count.assert_called_once()


def test_missing_days_have_stubs_and_day_based_continuation(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 25, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(other, 'datetime', FixedDatetime)
    monkeypatch.setattr(other.daily_summaries_db, 'get_daily_summary_by_date', lambda *a: None)
    monkeypatch.setattr(
        other.daily_summaries_db,
        'get_daily_summary_generation_status',
        lambda *a: {'status': 'failed'} if a[-1] == '2026-10-21' else None,
    )
    monkeypatch.setattr(other.daily_summaries_db, 'get_day_recording_count', lambda *a: 0 if a[1].day == 20 else 120)
    args = {'start_date': '2026-10-20', 'end_date': '2026-10-22', 'limit': 2}
    first = other.get_daily_summaries(OWNER, args)
    assert [row['status'] for row in first['daily_summaries']] == ['not_generated', 'failed']
    second = other.get_daily_summaries(OWNER, {**args, 'cursor': first['next_cursor']})
    assert second['daily_summaries'] == [
        {'date': '2026-10-20', 'status': 'no_recordings', 'generated_at': None, 'timezone': 'UTC'}
    ]
    assert 'next_cursor' not in second


def test_daily_existing_count_is_corrected_above_old_hundred_cap(monkeypatch):
    monkeypatch.setattr(
        other.daily_summaries_db,
        'get_daily_summary_by_date',
        lambda *a: {'date': '2026-10-22', 'stats': {'total_conversations': 100}},
    )
    monkeypatch.setattr(other.daily_summaries_db, 'get_day_recording_count', lambda *a: 137)
    result = other.get_daily_summaries(OWNER, {'start_date': '2026-10-22', 'end_date': '2026-10-22'})
    assert result['daily_summaries'][0]['stats']['total_conversations'] == 137


def test_profile_timezone_is_resolved_only_when_requested(monkeypatch):
    read = MagicMock(return_value={'time_zone': 'Asia/Ho_Chi_Minh'})
    monkeypatch.setattr(dates.users_db, 'get_user_profile', read)
    start, _end, zone = local_date_window(OWNER, '2026-10-22', '2026-10-22', 'profile')
    assert str(zone) == 'Asia/Ho_Chi_Minh' and start.hour == 17
    read.assert_called_once_with(OWNER)


def test_filtered_memory_path_never_falls_back_to_historical_after_canonical_failure(monkeypatch):
    monkeypatch.setattr(
        memory_reads, 'read_mcp_memory_candidates', MagicMock(side_effect=RuntimeError('synthetic canonical failure'))
    )
    with pytest.raises(RuntimeError, match='synthetic canonical failure'):
        memory_reads.collect_filtered_mcp_memories(SimpleNamespace(db_client=object()), OWNER, filters={})
    assert memory_reads.read_mcp_memory_candidates.call_count == 1


def test_created_only_legacy_candidates_are_included_without_updated_filter():
    updated = SimpleNamespace(id='updated', to_dict=lambda: {'updated_at': NOW})
    created_only = SimpleNamespace(id='created-only', to_dict=lambda: {'created_at': NOW})
    query = MagicMock()
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.side_effect = [[updated], [created_only]]
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = query
    assert [
        row.id
        for row in memory_queries.read_mcp_memory_candidates(
            OWNER, origin='memories', filters={}, firestore_client=client
        )
    ] == ['updated', 'created-only']


def test_summary_timestamps_have_offsets(monkeypatch):
    monkeypatch.setattr(
        other.screen_activity_db,
        'get_screen_activity_summary',
        lambda *a, **k: {
            'apps': {'Synthetic': {'first_seen': '2026-10-22 18:00:00.000'}},
            'coverage': {'first_observed_at': '2026-10-22 18:00:00.000'},
        },
    )
    result = other.get_screen_activity(OWNER, {'summary': True, 'timezone': 'Asia/Ho_Chi_Minh'})
    assert result['apps']['Synthetic']['first_seen'] == '2026-10-23T01:00:00+07:00'
    assert result['coverage']['first_observed_at'].endswith('+07:00')


def test_summary_honors_app_filter_over_whole_window(monkeypatch):
    read = MagicMock(return_value=[{'timestamp': '2026-10-22 18:00:00.000', 'appName': 'Synthetic'}] * 501)
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', read)
    result = other.get_screen_activity(OWNER, {'summary': True, 'app': 'Synthetic', 'limit': 200})
    assert result['total_screenshots'] == result['apps']['Synthetic']['count'] == 501
    assert read.call_args.kwargs['app_filter'] == 'Synthetic'


def test_daily_offset_past_window_is_empty_without_date_underflow():
    assert other.get_daily_summaries(
        OWNER, {'start_date': '0001-01-01', 'end_date': '0001-01-02', 'offset': 100000}
    ) == {'daily_summaries': []}


def test_filtered_memory_budget_exhaustion_cannot_be_empty_success(monkeypatch):
    read = MagicMock(side_effect=ListReadBudgetExhausted('documents'))
    monkeypatch.setattr(memory_reads, 'read_mcp_memory_candidates', read)
    budget = object()
    with pytest.raises(ToolExecutionError, match='request read budget exhausted'):
        memory_reads.collect_filtered_mcp_memories(
            SimpleNamespace(db_client=object()), OWNER, filters={}, budget=budget
        )
    assert read.call_args.kwargs['budget'] is budget


def test_filtered_candidate_policy_checks_share_the_request_budget(monkeypatch):
    snapshot = SimpleNamespace(id='synthetic-memory')
    monkeypatch.setattr(memory_reads, 'read_mcp_memory_candidates', MagicMock(side_effect=[[snapshot], []]))
    policy = MagicMock(return_value=([], True))
    monkeypatch.setattr(memory_reads, 'read_canonical_scan_page', policy)
    budget = SimpleNamespace(truncated=False)
    assert memory_reads.collect_filtered_mcp_memories(
        SimpleNamespace(db_client=object()), OWNER, filters={}, budget=budget
    ) == ([], 1)
    assert policy.call_args.kwargs['budget'] is budget


def test_legacy_summary_does_not_claim_unrecorded_review_coverage():
    result = summary_read_payload({'date': '2026-08-01', 'stats': {'memories_created': 9, 'action_items_created': 0}})
    assert result['memories_learned_coverage'].startswith('not_recorded_by_legacy_producer')
    assert result['action_items_coverage'].startswith('legacy_conversation_subset')


def test_malformed_optional_call_metadata_does_not_drop_the_card():
    result = conversation_card(
        {
            **card('a'),
            'source': {},
            'call_platform': [],
            'calendar_event_id': 7,
            'is_call': 'unknown',
            'calendar_meeting_context': {'platform': {}, 'event_id': 42},
        }
    )
    assert result['id'] == 'a'
    assert all(result[key] is None for key in ('source', 'is_call', 'call_platform', 'calendar_event_id'))


def test_filtered_global_sort_uses_complete_candidates_not_service_prefix(monkeypatch):
    read = MagicMock(return_value=([{'id': 'old-created'}, {'id': 'new-created'}], 620))
    monkeypatch.setattr(memories, 'read_filtered_mcp_memories', read)
    prefix = MagicMock(side_effect=AssertionError('incomplete service prefix must not be used'))
    monkeypatch.setattr(memories, 'MemoryService', prefix)
    result = memories.memories_page_core(OWNER, limit=20, sort='created_desc', updated_after=NOW, cursor_kind='test')
    assert len(result['memories']) == 2 and result['scanned_count'] == 620
    assert result['matched_count'] == 2 and not result['scan_truncated']
    prefix.assert_not_called()


def test_candidate_merge_preserves_universal_scoring_order(monkeypatch):
    old = {'id': 'canonical-old', 'created_at': NOW - timedelta(days=1), 'updated_at': NOW - timedelta(days=1)}
    new = {'id': 'historical-new', 'created_at': NOW}

    def model(row):
        return SimpleNamespace(model_dump=lambda **k: dict(row))

    canonical = SimpleNamespace(id=old['id'])
    historical = SimpleNamespace(id=new['id'], to_dict=lambda: dict(new))
    monkeypatch.setattr(memory_reads, 'read_mcp_memory_candidates', MagicMock(side_effect=[[canonical], [historical]]))
    monkeypatch.setattr(memory_reads, 'read_canonical_scan_page', lambda *a, **k: ([(model(old), None)], True))
    service = SimpleNamespace(
        db_client=object(),
        canonical_statuses=lambda *a: {},
        historical_suppression_reason=lambda *a, **k: None,
        history=SimpleNamespace(adapt_scan_payloads=lambda *a, **k: [(SimpleNamespace(memory=model(new)), None)]),
    )
    rows, scanned = memory_reads.collect_filtered_mcp_memories(service, OWNER, filters={'sort': 'scoring_desc'})
    assert [row['id'] for row in rows] == ['historical-new', 'canonical-old']
    assert scanned == 2


def test_native_offset_resumes_after_emitted_rows_without_materializing(monkeypatch):
    def mem(cid):
        return SimpleNamespace(model_dump=lambda **k: {'id': cid})

    service = MagicMock()
    service.read_page.side_effect = [
        SimpleNamespace(memories=[mem('a'), mem('b'), mem('c')], next_cursor='native-after-c', truncated=False),
        SimpleNamespace(memories=[mem('d')], next_cursor=None, truncated=False),
    ]
    monkeypatch.setattr(memories, 'MemoryService', lambda **k: service)
    first = memories.memories_page_core(OWNER, limit=2, offset=1, sort='updated_desc', cursor_kind='test')
    second = memories.memories_page_core(
        OWNER, limit=2, cursor_token=first['next_cursor'], sort='updated_desc', cursor_kind='test'
    )
    assert [row['id'] for row in first['memories']] == ['b', 'c']
    assert [row['id'] for row in second['memories']] == ['d']
    service.read_mcp_filtered.assert_not_called()


@pytest.mark.parametrize('sort', ['created_desc', 'manual_first'])
@pytest.mark.parametrize('origin', ['memory_items', 'memories'])
def test_large_account_default_is_bounded_and_never_materializes_all(monkeypatch, sort, origin):
    stored = [
        {'id': f'{origin}-{i}', 'content': 'Synthetic fact', 'created_at': NOW - timedelta(seconds=i)}
        for i in range(6854)
    ]
    service = MagicMock()
    service.read.side_effect = lambda uid, *, limit, offset, **kw: [
        SimpleNamespace(model_dump=lambda row=row, **k: row) for row in stored[offset : offset + limit]
    ]
    service.read_mcp_filtered.side_effect = AssertionError('default must not scan entire stores')
    monkeypatch.setattr(memories, 'MemoryService', lambda **kw: service)
    first = memories.memories_page_core(OWNER, limit=20, sort=sort, cursor_kind='test')
    second = memories.memories_page_core(
        OWNER, limit=20, sort=sort, cursor_kind='test', cursor_token=first['next_cursor']
    )
    assert len(first['memories']) == len(second['memories']) == 20
    assert first['memories'][0]['id'] == f'{origin}-0' and second['memories'][0]['id'] == f'{origin}-20'
    assert first['scan_truncated'] and first['more_in_window'] and 'bounded' in first['coverage']
    assert first['source_window_limit'] == first['scanned_count'] == 100
    assert all(call.kwargs['limit'] == 100 for call in service.read.call_args_list)
    service.read_mcp_filtered.assert_not_called()


@pytest.mark.parametrize(
    'options,expected',
    [
        ({}, '2026-10-22 02:15:00.000'),
        ({'timestamp_format': 'iso_offset'}, '2026-10-22T02:15:00+00:00'),
        ({'timezone': 'UTC'}, '2026-10-22T02:15:00+00:00'),
        ({'timezone': 'Asia/Ho_Chi_Minh'}, '2026-10-22T09:15:00+07:00'),
    ],
)
def test_screen_timestamp_formats_are_opt_in(monkeypatch, options, expected):
    rows = [{'id': 'synthetic', 'timestamp': '2026-10-22 02:15:00.000', 'appName': 'Synthetic'}]
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity_page', lambda *a, **k: (rows, False))
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *a, **k: rows)
    raw = other.get_screen_activity(OWNER, options)
    assert raw['screen_activity'][0]['timestamp'] == expected
    grouped = other.get_screen_activity(OWNER, {**options, 'group_by': 'hour'})
    expected_hour = '2026-10-22 02:00' if not options else expected[:13] + ':00:00' + expected[-6:]
    assert grouped['buckets'][0]['hour'] == expected_hour
    assert grouped['buckets'][0]['first_seen'] == expected


@pytest.mark.parametrize('group_by', ['app', 'hour', 'day'])
def test_screen_grouping_ignores_even_stale_cursors_with_note(monkeypatch, group_by):
    rows = [{'timestamp': '2026-10-22 02:15:00.000', 'appName': 'Synthetic'}] * 501
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *a, **k: rows)
    first = other.get_screen_activity(OWNER, {'group_by': group_by})
    resumed = other.get_screen_activity(OWNER, {'group_by': group_by, 'cursor': 'old-or-invalid-cursor'})
    assert resumed['buckets'] == first['buckets']
    assert sum(row['count'] for row in resumed['buckets']) == 501
    assert 'cursor ignored' in resumed['note'] and resumed['coverage']['complete_window']
    assert 'next_cursor' not in resumed


def test_duplicate_ids_and_omissions_always_advance_cursor(monkeypatch):
    ids = ['a', 'b', 'a', 'c', 'b', 'd']
    monkeypatch.setattr(
        conversations.conversations_db, 'get_mcp_conversations_by_id', lambda *a, **k: [card(cid) for cid in set(ids)]
    )
    # Force metadata budget omission, regardless of transcript shrink rounds.
    monkeypatch.setattr(
        conversations, 'tool_response_serialized_chars', lambda result: 100 * len(result['conversations'])
    )
    monkeypatch.setattr(conversations, 'MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS', 100)
    cursor = None
    seen = []
    tokens = set()
    for _ in range(6):
        args = {'conversation_ids': ids}
        if cursor:
            args['cursor'] = cursor
        result = conversations.get_conversations_by_ids(OWNER, args)
        seen.extend(row['id'] for row in result['conversations'])
        cursor = result.get('next_cursor')
        if cursor is None:
            break
        assert cursor not in tokens
        tokens.add(cursor)
    assert seen == ['a', 'b', 'c', 'd'] and cursor is None
