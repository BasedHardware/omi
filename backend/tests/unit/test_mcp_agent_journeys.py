"""Task-shaped agent journeys over the hosted MCP tools (synthetic store, no IO).

Each journey chains real tool calls the way ChatGPT, Claude or a syncing agent
would, and checks every response against its advertised output schema and the
serialized response budget. They are an eval set for the read surface as a
whole: if a tool stops leading to the next one (an id, a section, a segment
index, a cursor), a journey breaks even when each tool's own tests still pass.
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import jsonschema
import pytest

from database.transcript_search import TranscriptScanPage, TranscriptScanRow
from utils.mcp_server.constants import MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
from utils.mcp_server.handlers import conversations, transcripts
from utils.mcp_server.payloads import tool_response_serialized_chars, tool_result_payload
from utils.mcp_server.registry import TOOLS_BY_NAME, execute_tool

OWNER = 'synthetic-owner'
DAY = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)
LINES = [
    'we should look at the budget before friday',
    'the hiring plan needs two more engineers',
    'my sister is visiting next week',
    'can you send me the deck',
]


def _segments(cid, count, mentions):
    rows = []
    for i in range(count):
        rows.append(
            {
                'id': f'{cid}-s{i}',
                'text': mentions.get(i, f'{LINES[i % len(LINES)]} ({i})'),
                'speaker_id': i % 2,
                'is_user': i % 2 == 0,
                'start': i * 5.0,
                'end': i * 5.0 + 4.5,
            }
        )
    return rows


def _conversation(cid, hour, title, count, mentions=None, sections=None, **extra):
    segments = _segments(cid, count, mentions or {})
    return {
        'id': cid,
        'status': 'completed',
        'created_at': DAY + timedelta(hours=hour),
        'started_at': DAY + timedelta(hours=hour),
        'finished_at': DAY + timedelta(hours=hour, seconds=count * 5),
        'language': 'en',
        'kind': 'conversation',
        'structured': {'title': title, 'overview': f'{title} overview', 'sections': sections or []},
        'transcript_segments': segments,
        **extra,
    }


@pytest.fixture
def store(monkeypatch):
    planning = _conversation(
        'planning',
        1,
        'Quarterly planning',
        1_400,
        mentions={1_111: 'Priya said the Series A closes in March'},
        sections=[
            {'heading': 'Budget', 'source_segment_ids': [f'planning-s{i}' for i in range(10, 60)]},
            {'heading': 'Hiring', 'source_segment_ids': [f'planning-s{i}' for i in range(600, 700)]},
        ],
    )
    lunch = _conversation('lunch', 4, 'Lunch with family', 40)
    tv = _conversation('tv', 6, 'TV in the background', 30, kind='media')
    rows = {row['id']: row for row in (planning, lunch, tv)}

    def copy(row):
        return {**row, 'transcript_segments': [dict(s) for s in row['transcript_segments']]}

    def by_ids(uid, ids, **kwargs):
        return [copy(rows[cid]) for cid in ids if cid in rows]

    def cards_page(uid, limit, *args, **kwargs):
        ordered = sorted(rows.values(), key=lambda r: r['created_at'], reverse=True)
        return [{k: v for k, v in copy(r).items() if k != 'transcript_segments'} for r in ordered][:limit], None

    def scan(uid, query, **kwargs):
        ordered = sorted(rows.values(), key=lambda r: r['created_at'], reverse=True)
        return TranscriptScanPage([TranscriptScanRow(copy(r), f'cursor-{r["id"]}') for r in ordered], exhausted=True)

    utc = lambda *a, **k: (None, None, ZoneInfo('UTC'))  # noqa: E731
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', by_ids)
    monkeypatch.setattr(conversations.mcp_conversation_pages, 'get_mcp_conversation_cards_page', cards_page)
    monkeypatch.setattr(conversations, 'resolve_mcp_conversation_search_ids', lambda *a, **k: ['planning'])
    monkeypatch.setattr(conversations, 'keyword_search_conversation_ids', lambda *a, **k: ['lunch'])
    monkeypatch.setattr(conversations, 'local_date_window', utc)
    monkeypatch.setattr(transcripts, 'read_transcript_search_page', scan)
    monkeypatch.setattr(transcripts, 'local_date_window', utc)
    return rows


def call(name, **arguments):
    result = execute_tool(OWNER, name, arguments)
    wire = tool_result_payload(result)['structuredContent']
    jsonschema.validate(wire, TOOLS_BY_NAME[name].output_schema)
    assert tool_response_serialized_chars(result) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
    return wire


def test_what_did_we_decide_about_the_budget(store):
    """Search a topic, outline the long hit, then read only the cited section, compactly."""
    hits = call('search_conversations', query='budget')['conversations']
    assert hits[0]['id'] == 'planning' and 'summary' in hits[0]['match_basis']
    outline = call('get_conversation_by_id', conversation_id=hits[0]['id'], view='outline')
    budget = next(s for s in outline['sections'] if s['heading'] == 'Budget')
    section = call(
        'get_conversation_by_id',
        conversation_id='planning',
        offset=budget['first_segment'],
        max_segments=budget['segment_count'],
        format='lines',
    )
    assert section['conversation']['transcript_range'] == [10, 59]
    assert 'budget' in section['conversation']['transcript']


def test_when_was_the_series_a_mentioned(store):
    """A detail said once in a two-hour window: find it literally, then read around it."""
    (match,) = call('search_transcripts', query='Series A')['matches']
    (hit,) = match['hits']
    assert match['conversation']['id'] == 'planning' and hit['segment_index'] == 1_111
    around = call(
        'get_conversation_by_id',
        conversation_id='planning',
        offset=hit['segment_index'] - 2,
        max_segments=5,
        format='lines',
    )
    assert 'Series A closes in March' in around['conversation']['transcript']
    assert around['conversation']['transcript_range'] == [1_109, 1_113]


def test_read_a_whole_long_conversation_page_by_page(store):
    """Every segment reachable exactly once by following next_cursor, in lines."""
    page = call('get_conversation_by_id', conversation_id='planning', format='lines')
    covered = []
    for _ in range(20):
        first, last = page['conversation']['transcript_range']
        covered.extend(range(first, last + 1))
        if not page['next_cursor']:
            break
        page = call('get_conversation_by_id', conversation_id='planning', format='lines', cursor=page['next_cursor'])
    assert covered == list(range(1_400)) and page['truncated'] is False


def test_what_happened_today_tells_media_from_conversation(store):
    """A day listing gives kinds and durations, so an agent can skip background media before reading."""
    cards = call('get_conversations', start_date='2026-11-16', end_date='2026-11-16')['conversations']
    kinds = {card['id']: card.get('kind') for card in cards}
    assert kinds == {'planning': 'conversation', 'lunch': 'conversation', 'tv': 'media'}
    wanted = [cid for cid, kind in kinds.items() if kind != 'media']
    # JSON segments of a two-hour conversation do not fit beside another item; the
    # batch never silently shrinks one, it lists it in next_ids. lines fits both.
    segments = call('get_conversations_by_ids', conversation_ids=wanted)
    assert [i['id'] for i in segments['conversations']] + segments['next_ids'] == wanted
    read = call('get_conversations_by_ids', conversation_ids=wanted, format='lines')
    assert {item['id'] for item in read['conversations']} == {'planning', 'lunch'} and read['next_ids'] == []
