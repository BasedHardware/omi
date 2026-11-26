"""Outline-first, offset and lines reads of one long conversation over hosted MCP (synthetic data).

Paging and its cursors are covered by ``test_mcp_conversation_detail_paging.py``.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from utils.mcp_dates import localize_timestamps
from utils.mcp_server import detail_views
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import conversations
from utils.mcp_server.helpers import conversation_card, select_card_fields
from utils.mcp_server.payloads import tool_response_serialized_chars

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
OWNER = 'synthetic-owner'


@pytest.fixture(autouse=True)
def cursor_key(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-detail-views-secret-0123456789')


def long_conversation(count=1300, text='word ' * 11, **extra):
    """About 1,300 segments is a two-hour v3 window at half speech."""
    segments = [
        {
            'id': f'seg-{i}',
            'text': f'{i} {text}'.strip(),
            'speaker_id': i % 3,
            'is_user': i % 3 == 0,
            'start': i * 4.3,
            'end': i * 4.3 + 4,
        }
        for i in range(count)
    ]
    return {
        'id': 'synthetic-long',
        'status': 'completed',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW + timedelta(hours=2),
        'structured': {'title': 'Planning', 'overview': 'Synthetic overview'},
        'transcript_segments': segments,
        **extra,
    }


@pytest.fixture
def stored(monkeypatch):
    row = long_conversation()
    reads = []

    def fetch(uid, conversation_id, extra_field_paths=None):
        reads.append(extra_field_paths)
        return {**row, 'transcript_segments': [dict(s) for s in row['transcript_segments']]}

    monkeypatch.setattr(conversations, 'fetch_conversation_for_detail', fetch)
    row['_reads'] = reads
    return row


def read(arguments):
    return conversations.get_conversation_by_id(OWNER, {'conversation_id': 'synthetic-long', **arguments})


def test_outline_anchors_sections_to_the_segments_they_cite(stored):
    stored['structured']['sections'] = [
        {'heading': 'Budget', 'body_markdown': 'b', 'source_segment_ids': ['seg-40', 'seg-12', 'seg-30']},
        {'heading': 'Hiring', 'body_markdown': 'h', 'source_segment_ids': ['seg-900'], 'kind': 'main'},
        {'heading': 'Loose ends', 'body_markdown': 'l', 'source_segment_ids': ['unknown-id']},
    ]
    result = read({'view': 'outline'})
    assert stored['_reads'][-1] == ['structured.sections']
    assert 'transcript_segments' not in result['conversation']
    assert result['truncated'] is False and result['next_cursor'] is None and result['total_segments'] == 1300
    budget, hiring, loose = result['sections']
    assert (budget['heading'], budget['first_segment'], budget['segment_count']) == ('Budget', 12, 29)
    assert budget['start'] == round(12 * 4.3, 1) and budget['end'] == round(40 * 4.3 + 4, 1)
    assert (hiring['first_segment'], hiring['segment_count'], hiring['kind']) == (900, 1, 'main')
    assert loose['first_segment'] is None and loose['segment_count'] is None
    assert tool_response_serialized_chars(result) < 5_000

    section = read({'offset': budget['first_segment'], 'max_segments': budget['segment_count']})
    ids = [s['id'] for s in section['conversation']['transcript_segments']]
    assert ids[0] == 'seg-12' and ids[-1] == 'seg-40' and section['truncated'] is True


def test_outline_is_bounded_and_says_when_sections_were_left_out(stored):
    stored['structured']['sections'] = [
        {'heading': 'h' * 5_000, 'source_segment_ids': [f'seg-{i}']}
        for i in range(detail_views.OUTLINE_MAX_SECTIONS + 50)
    ]
    result = read({'view': 'outline'})
    assert len(result['sections']) == detail_views.OUTLINE_MAX_SECTIONS and result['sections_truncated'] is True
    assert len(result['sections'][0]['heading']) == detail_views.SECTION_HEADING_MAX_CHARS
    stored['structured']['sections'] = stored['structured']['sections'][:3]
    assert read({'view': 'outline'})['sections_truncated'] is False


def test_transcript_reads_do_not_fetch_sections(stored):
    read({})
    assert stored['_reads'][-1] is None


def test_offset_starts_a_read_that_the_cursor_then_continues(stored):
    first = read({'offset': 1000, 'max_segments': 200})
    assert first['conversation']['transcript_segments'][0]['segment_index'] == 1000
    last = read({'max_segments': 200, 'cursor': first['next_cursor']})
    assert last['conversation']['transcript_segments'][0]['segment_index'] == 1200
    assert last['conversation']['transcript_segments'][-1]['id'] == 'seg-1299'
    assert last['next_cursor'] is None and last['truncated'] is False


def test_offset_at_the_end_is_empty_and_past_it_is_an_argument_error(stored):
    end = read({'offset': 1300})
    assert end['conversation']['transcript_segments'] == [] and end['truncated'] is False
    with pytest.raises(ToolExecutionError, match='past the end') as error:
        read({'offset': 1301})
    assert error.value.code == -32602


def test_a_cursor_wins_over_a_resent_offset(stored):
    first = read({'offset': 5, 'max_segments': 10})
    second = read({'offset': 5, 'max_segments': 10, 'cursor': first['next_cursor']})
    assert second['conversation']['transcript_segments'][0]['segment_index'] == 15
    assert read({'offset': 'junk', 'max_segments': 10, 'cursor': first['next_cursor']})['total_segments'] == 1300


@pytest.mark.parametrize('offset', [-1, 2_000_000_000, 'ten', True, 1.5])
def test_out_of_range_or_malformed_offsets_are_rejected_not_clamped(stored, offset):
    with pytest.raises(ToolExecutionError) as error:
        read({'offset': offset})
    assert error.value.code == -32602


def test_default_format_keeps_the_cursor_fingerprint_of_plain_paging():
    filters = conversations._detail_filters({}, 'synthetic-long', 500, 24_000)
    assert 'format' not in filters
    assert conversations._detail_filters({'format': 'lines'}, 'synthetic-long', 500, 24_000)['format'] == 'lines'


def test_lines_format_is_a_fraction_of_the_segment_json(stored):
    segments = read({'max_segments': 100})
    lines = read({'max_segments': 100, 'format': 'lines'})
    assert len(segments['conversation']['transcript_segments']) == 100
    assert 'transcript_segments' not in lines['conversation']
    text = lines['conversation']['transcript']
    assert text.splitlines()[0].startswith('[0:00:00] ') and '99 word' in text
    assert lines['conversation']['transcript_range'] == [0, 99]
    assert tool_response_serialized_chars(lines) * 2 < tool_response_serialized_chars(segments)


def test_lines_pages_continue_in_lines_and_the_cursor_is_bound_to_the_format(stored):
    first = read({'format': 'lines', 'max_segments': 100})
    second = read({'format': 'lines', 'max_segments': 100, 'cursor': first['next_cursor']})
    assert second['conversation']['transcript'].startswith('[0:07:10] ')
    with pytest.raises(ToolExecutionError, match='Invalid transcript cursor'):
        read({'max_segments': 100, 'cursor': first['next_cursor']})


def test_lines_keep_two_speakers_who_share_a_label_apart():
    items = [
        {'speaker_key': 'person:a', 'speaker_label': 'Alex', 'start': 0, 'text': 'one'},
        {'speaker_key': 'person:b', 'speaker_label': 'Alex', 'start': 5, 'text': 'two'},
    ]
    assert detail_views.render_lines(items) == '[0:00:00] Alex: one\n[0:00:05] Alex: two'
    corrected = [
        {'speaker_key': 'speaker:0', 'speaker_label': 'You', 'start': 0, 'text': 'mine'},
        {'speaker_key': 'speaker:0', 'speaker_label': 'Speaker A', 'start': 4, 'text': 'not mine'},
    ]
    assert detail_views.render_lines(corrected) == '[0:00:00] You: mine\n[0:00:04] Speaker A: not mine'


def test_lines_page_only_the_text_they_render(monkeypatch):
    row = long_conversation(count=1, text='short')
    row['transcript_segments'][0]['original_text'] = 'x' * 500
    monkeypatch.setattr(conversations, 'fetch_conversation_for_detail', lambda *a, **k: dict(row))
    page = read({'format': 'lines', 'max_chars': 5})
    assert page['conversation']['transcript'] == '[0:00:00] You: 0 sho'
    pages = 1
    while page['next_cursor']:
        page = read({'format': 'lines', 'max_chars': 5, 'cursor': page['next_cursor']})
        assert page['conversation']['transcript'].split(': ', 1)[1]
        pages += 1
    assert pages == 2


def test_empty_lines_page_reports_a_null_range_and_can_be_projected(stored):
    page = read({'format': 'lines', 'offset': 1300, 'fields': ['transcript', 'transcript_range']})
    assert page['conversation']['transcript'] == '' and page['conversation']['transcript_range'] is None


def test_outline_window_spans_every_cited_segment(stored):
    stored['transcript_segments'][3].update(start=8, end=27)
    stored['transcript_segments'][4].update(start=0, end=8)
    stored['structured']['sections'] = [{'heading': 'h', 'source_segment_ids': ['seg-3', 'seg-4']}]
    (section,) = read({'view': 'outline'})['sections']
    assert (section['start'], section['end']) == (0.0, 27.0)


def test_lines_join_consecutive_turns_of_one_speaker():
    items = [
        {'speaker_label': 'You', 'start': 0, 'text': 'hello'},
        {'speaker_label': 'You', 'start': 3, 'text': 'again'},
        {'speaker_label': 'Speaker 1', 'start': 3725, 'text': 'hi'},
    ]
    assert detail_views.render_lines(items) == '[0:00:00] You: hello again\n[1:02:05] Speaker 1: hi'


def test_locked_conversation_refuses_every_view(monkeypatch):
    locked = long_conversation(count=3, is_locked=True)
    monkeypatch.setattr(conversations, 'fetch_conversation_for_detail', lambda *a, **k: locked)
    for view in ('outline', 'transcript'):
        with pytest.raises(ToolExecutionError, match='paid plan'):
            read({'view': view})


def test_invalid_view_or_format_is_a_model_visible_argument_error(stored):
    for arguments in ({'view': 'everything'}, {'format': 'xml'}):
        with pytest.raises(ToolExecutionError) as error:
            read(arguments)
        assert error.value.code == -32602


def test_batch_items_accept_lines_and_keep_their_page_counts(monkeypatch):
    rows = [long_conversation(count=600), {**long_conversation(count=5), 'id': 'short'}]
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', lambda *a, **k: rows)
    result = conversations.get_conversations_by_ids(
        OWNER, {'conversation_ids': ['synthetic-long', 'short'], 'format': 'lines'}
    )
    long_item, short_item = result['conversations']
    assert isinstance(long_item['conversation']['transcript'], str)
    assert long_item['truncated'] and long_item['total_segments'] == 600 and long_item['next_cursor']
    assert not short_item['truncated'] and short_item['total_segments'] == 5
    monkeypatch.setattr(conversations, 'fetch_conversation_for_detail', lambda *a, **k: dict(rows[0]))
    resumed_at = long_item['conversation']['transcript_range'][1] + 1
    continued = conversations.get_conversation_by_id(
        OWNER, {'conversation_id': 'synthetic-long', 'format': 'lines', 'cursor': long_item['next_cursor']}
    )
    assert continued['conversation']['transcript'].startswith(f'[{detail_views._clock(resumed_at * 4.3)}] ')
    assert continued['conversation']['transcript_range'][0] == resumed_at


def test_page_counter_records_view_format_position_and_more(stored):
    counter = detail_views.MCP_TRANSCRIPT_PAGES_TOTAL

    def value(*labels):
        return counter.labels(*labels)._value.get()

    before = value('get_conversation_by_id', 'transcript', 'lines', 'first', 'true')
    first = read({'format': 'lines'})
    assert value('get_conversation_by_id', 'transcript', 'lines', 'first', 'true') == before + 1
    before = value('get_conversation_by_id', 'transcript', 'lines', 'continuation', 'true')
    read({'format': 'lines', 'cursor': first['next_cursor']})
    assert value('get_conversation_by_id', 'transcript', 'lines', 'continuation', 'true') == before + 1
    before = value('get_conversation_by_id', 'outline', 'segments', 'first', 'false')
    read({'view': 'outline'})
    assert value('get_conversation_by_id', 'outline', 'segments', 'first', 'false') == before + 1
    # A section read that starts at an offset is still the first page the agent asked for.
    before = value('get_conversation_by_id', 'transcript', 'segments', 'first', 'true')
    read({'offset': 600, 'max_segments': 10})
    assert value('get_conversation_by_id', 'transcript', 'segments', 'first', 'true') == before + 1


def test_card_reports_state_and_kind_only_where_stored():
    legacy = conversation_card(long_conversation(count=2))
    assert legacy['status'] == 'completed' and legacy['duration_seconds'] == 8
    assert not {'kind', 'shown_on_home', 'summary_covers_through'} & set(legacy)
    v3 = conversation_card(
        long_conversation(
            count=2, status='in_progress', kind='background', home_hidden=True, summary_covers_through=NOW
        )
    )
    assert (v3['status'], v3['kind'], v3['shown_on_home'], v3['summary_covers_through']) == (
        'in_progress',
        'background',
        False,
        NOW,
    )
    assert 'kind' not in conversation_card(long_conversation(count=2, kind='something-new'))
    assert select_card_fields(legacy, ['kind', 'status']) == {'id': legacy['id'], 'status': 'completed'}


def test_list_cards_without_a_transcript_do_not_guess_duration_from_the_wall_window():
    row = long_conversation(count=2)
    del row['transcript_segments']
    assert conversation_card(row)['duration_seconds'] is None


def test_a_loaded_transcript_free_record_keeps_its_wall_window_duration():
    photo_only = long_conversation(count=0)
    photo_only['finished_at'] = NOW + timedelta(seconds=45)
    assert conversation_card(photo_only)['duration_seconds'] == 45


def test_summary_coverage_is_localized_like_the_other_card_timestamps():
    card = {'started_at': NOW, 'summary_covers_through': NOW}
    local = localize_timestamps(card, ZoneInfo('America/Los_Angeles'))
    assert local['summary_covers_through'] == local['started_at'] != NOW.isoformat()
