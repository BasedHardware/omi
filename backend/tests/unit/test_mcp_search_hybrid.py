"""Hybrid conversation search and literal transcript search over hosted MCP (synthetic data)."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import jsonschema
import pytest
from google.api_core.exceptions import FailedPrecondition

from database.transcript_search import InvalidTranscriptCursor, TranscriptScanPage, TranscriptScanRow
from utils.mcp_server import search_views
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.constants import MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
from utils.mcp_server.handlers import conversations, transcripts
from utils.mcp_server.payloads import tool_response_serialized_chars
from utils.mcp_server.registry import TOOLS_BY_NAME

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
OWNER = 'synthetic-owner'


def conversation(cid, *, words=None, count=3, **extra):
    segments = [
        {'id': f'{cid}-s{i}', 'text': f'line {i}', 'speaker_id': i % 2, 'is_user': i % 2 == 0, 'start': i, 'end': i + 1}
        for i in range(count)
    ]
    for index, text in (words or {}).items():
        segments[index]['text'] = text
    return {
        'id': cid,
        'status': 'completed',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW,
        'structured': {'title': f'Title {cid}', 'overview': 'overview'},
        'transcript_segments': segments,
        **extra,
    }


@pytest.fixture
def indexes(monkeypatch):
    state = {'vector': [], 'keyword': [], 'vector_error': None, 'keyword_error': None, 'rows': {}}

    def vector_ids(*args, **kwargs):
        if state['vector_error']:
            raise state['vector_error']
        return list(state['vector'])

    def keyword_ids(*args, **kwargs):
        if state['keyword_error']:
            raise state['keyword_error']
        return list(state['keyword'])

    def hydrate(uid, ids, **kwargs):
        return [dict(state['rows'][cid]) for cid in ids if cid in state['rows']]

    monkeypatch.setattr(conversations, 'resolve_mcp_conversation_search_ids', vector_ids)
    monkeypatch.setattr(conversations, 'keyword_search_conversation_ids', keyword_ids)
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', hydrate)
    monkeypatch.setattr(conversations, 'local_date_window', lambda *a, **k: (None, None, ZoneInfo('UTC')))
    return state


def search(query='budget', **arguments):
    return conversations.search_conversations(OWNER, {'query': query, **arguments})


def test_merge_ranks_shared_hits_first_then_alternates_the_two_indexes():
    merged = search_views.merge_search_ids(['v1', 'both', 'v2', 'v3'], ['k1', 'both', 'k2'], 10)
    assert merged == ['both', 'v1', 'k1', 'v2', 'k2', 'v3']
    assert search_views.merge_search_ids(['a', 'a', ''], ['a'], 10) == ['a']
    assert search_views.merge_search_ids(['v1', 'v2'], ['k1'], 2) == ['v1', 'k1']


def test_a_semantic_hit_no_longer_hides_exact_title_matches(indexes):
    indexes['vector'] = ['v1', 'both']
    indexes['keyword'] = ['both', 'k1']
    indexes['rows'] = {
        'v1': conversation('v1'),
        'both': conversation('both', words={1: 'the budget is final'}),
        'k1': conversation('k1'),
    }
    result = search()
    assert [c['id'] for c in result['conversations']] == ['both', 'v1', 'k1']
    basis = {c['id']: c['match_basis'] for c in result['conversations']}
    assert basis == {'both': ['summary', 'keyword', 'transcript'], 'v1': ['summary'], 'k1': ['keyword']}
    assert result['search_coverage'] == 'summary_vectors_and_keyword' and result['unavailable_indexes'] == []
    jsonschema.validate(result, TOOLS_BY_NAME['search_conversations'].output_schema)


def test_one_index_down_still_answers_and_says_which(indexes):
    indexes['rows'] = {'v1': conversation('v1'), 'k1': conversation('k1')}
    indexes['vector'], indexes['keyword_error'] = ['v1'], RuntimeError('typesense down')
    result = search()
    assert [c['id'] for c in result['conversations']] == ['v1']
    assert (result['search_coverage'], result['unavailable_indexes']) == ('summary_vectors_only', ['keyword'])

    indexes['vector_error'], indexes['keyword_error'], indexes['keyword'] = RuntimeError('pinecone'), None, ['k1']
    result = search()
    assert [c['id'] for c in result['conversations']] == ['k1']
    assert (result['search_coverage'], result['unavailable_indexes']) == ('keyword_only', ['summary_vectors'])


def test_a_vector_index_still_building_falls_back_to_keyword(indexes):
    indexes['rows'] = {'k1': conversation('k1')}
    indexes['vector_error'], indexes['keyword'] = FailedPrecondition('index building'), ['k1']
    result = search()
    assert [c['id'] for c in result['conversations']] == ['k1']
    assert (result['search_coverage'], result['unavailable_indexes']) == ('keyword_only', ['summary_vectors'])
    indexes['keyword_error'] = RuntimeError('typesense down')
    with pytest.raises(ToolExecutionError) as error:
        search()
    assert error.value.code == -32009 and 'index is still being built' in error.value.message


def test_keyword_index_down_is_counted_as_a_fallback_even_with_vector_hits(indexes, monkeypatch):
    fallbacks = []
    monkeypatch.setattr(conversations, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    indexes['rows'], indexes['vector'] = {'v1': conversation('v1')}, ['v1']
    search()
    assert fallbacks == []
    indexes['keyword_error'] = RuntimeError('typesense down')
    search()
    assert len(fallbacks) == 1 and fallbacks[0]['outcome'] == 'degraded'


def test_stale_index_ids_never_crowd_out_valid_hits_further_down(indexes):
    indexes['vector'], indexes['keyword'] = ['v1', 'v2', 'v3'], ['k1', 'k2', 'k3']
    indexes['rows'] = {cid: conversation(cid) for cid in ('k1', 'k2', 'k3')}
    assert [c['id'] for c in search(limit=3)['conversations']] == ['k1', 'k2', 'k3']


def test_an_unconfigured_vector_index_is_reported_unavailable_not_empty(monkeypatch):
    monkeypatch.setattr(conversations.vector_db, 'index', None)
    with pytest.raises(conversations._VectorIndexUnconfigured):
        conversations._query_configured_vectors('budget', 'uid')


def test_unreadable_records_make_coverage_partial_even_at_the_end(scan):
    scan['rows'], scan['unreadable'] = [conversation('ok', words={0: 'series a'})], 1
    result = find()
    assert result['complete'] is True and result['search_coverage'] == 'literal_transcript_scan_partial'


def test_no_hits_with_the_keyword_index_down_is_an_actionable_503(indexes):
    indexes['keyword_error'] = RuntimeError('typesense down')
    with pytest.raises(ToolExecutionError) as error:
        search()
    assert error.value.http_status == 503 and 'get_conversations' in error.value.message


def test_empty_search_points_at_transcript_search(indexes):
    result = search()
    assert result['conversations'] == [] and 'search_transcripts' in result['message']


def test_a_snippet_segment_index_is_where_an_offset_read_starts(indexes, monkeypatch):
    long_row = conversation('long', count=900, words={640: 'we agreed the budget at last'})
    indexes['vector'], indexes['rows'] = ['long'], {'long': long_row}
    (card,) = search()['conversations']
    (snippet,) = card['match_snippets']
    assert snippet['segment_index'] == 640
    monkeypatch.setattr(conversations, 'fetch_conversation_for_detail', lambda *a, **k: dict(long_row))
    page = conversations.get_conversation_by_id(
        OWNER, {'conversation_id': 'long', 'offset': snippet['segment_index'], 'max_segments': 1}
    )
    assert page['conversation']['transcript_segments'][0]['text'] == 'we agreed the budget at last'


# search_transcripts


@pytest.fixture
def scan(monkeypatch):
    state = {'rows': [], 'exhausted': True, 'unreadable': 0, 'error': None, 'calls': []}

    def read_page(uid, query, *, cursor=None, start_date=None, end_date=None, budget=None):
        state['calls'].append({'cursor': cursor, 'query': query})
        if state['error']:
            raise state['error']
        return TranscriptScanPage(
            [TranscriptScanRow(row, f'cursor-{i}') for i, row in enumerate(state['rows'])],
            exhausted=state['exhausted'],
            unreadable=state['unreadable'],
        )

    monkeypatch.setattr(transcripts, 'read_transcript_search_page', read_page)
    monkeypatch.setattr(transcripts, 'local_date_window', lambda *a, **k: (None, None, ZoneInfo('UTC')))
    return state


def find(query='series a', **arguments):
    return transcripts.search_transcripts(OWNER, {'query': query, **arguments})


def test_transcript_search_finds_a_passing_mention_and_locates_it(scan):
    scan['rows'] = [
        conversation('quiet', count=50),
        conversation('long', count=1300, words={777: 'Bob said the Series A closes in March'}),
    ]
    result = find()
    (match,) = result['matches']
    assert match['conversation']['id'] == 'long' and match['conversation']['title'] == 'Title long'
    (hit,) = match['hits']
    assert hit['segment_index'] == 777 and hit['segment_id'] == 'long-s777' and 'Series A' in hit['text']
    assert result['complete'] is True and result['next_cursor'] is None and result['examined'] == 2
    assert result['search_coverage'] == 'literal_transcript_scan'
    jsonschema.validate(result, TOOLS_BY_NAME['search_transcripts'].output_schema)


def test_transcript_search_resumes_after_the_last_conversation_it_examined(scan):
    scan['rows'] = [conversation(f'c{i}', words={0: 'series a update'}) for i in range(4)]
    result = find(limit=2)
    assert [m['conversation']['id'] for m in result['matches']] == ['c0', 'c1']
    assert result['complete'] is False and result['next_cursor'] == 'cursor-1'
    assert result['search_coverage'] == 'literal_transcript_scan_partial'
    scan['exhausted'] = False
    assert find()['next_cursor'] == 'cursor-3'
    find(cursor='cursor-3')
    assert scan['calls'][-1]['cursor'] == 'cursor-3'


def test_transcript_search_never_quotes_locked_discarded_deferred_or_unreadable_records(scan):
    words = {0: 'series a terms'}
    scan['rows'] = [
        None,
        conversation('locked', words=words, is_locked=True),
        conversation('discarded', words=words, discarded=True),
        conversation('deferred', words=words, processing_deferred=True),
        conversation('ok', words=words),
    ]
    scan['unreadable'] = 1
    result = find()
    assert [m['conversation']['id'] for m in result['matches']] == ['ok']
    assert result['examined'] == 5 and result['unreadable'] == 1


def test_a_one_letter_word_in_the_query_must_be_said(scan):
    scan['rows'] = [
        conversation('other', words={0: 'the series finale aired'}),
        conversation('said', words={0: 'Series B closed, then a Series... A? yes'}),
    ]
    assert [m['conversation']['id'] for m in find()['matches']] == ['said']


def test_legacy_segments_without_ids_still_get_a_segment_index(scan):
    row = conversation('legacy', count=30, words={21: 'the series a terms'})
    for segment in row['transcript_segments']:
        segment.pop('id')
    scan['rows'] = [row]
    (hit,) = find()['matches'][0]['hits']
    assert hit['segment_index'] == 21 and hit.get('segment_id') is None and '_position' not in hit


def test_a_long_segment_is_clipped_around_all_of_its_words(scan):
    text = 'budget ' + 'filler words here ' * 40 + 'then the review of the budget closed it'
    scan['rows'] = [conversation('long-segment', words={0: text})]
    (hit,) = find('budget review')['matches'][0]['hits']
    assert 'review' in hit['text'] and 'budget' in hit['text'] and hit['segment_index'] == 0


def test_matching_stops_at_its_deadline_and_resumes_after_the_last_finished_record(scan, monkeypatch):
    ticks = iter([0.0] + [0.0] * 2 + [100.0] * 50)
    monkeypatch.setattr(transcripts, '_clock', lambda: next(ticks))
    fallbacks = []
    monkeypatch.setattr(transcripts, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    scan['rows'] = [conversation(f'c{i}', words={0: 'series a'}) for i in range(5)]
    result = find()
    assert result['complete'] is False and result['examined'] == len(result['matches']) >= 1
    assert result['next_cursor'] == f'cursor-{result["examined"] - 1}'
    assert [f['reason'] for f in fallbacks] == ['capacity_full']


def test_unreadable_records_are_counted_as_a_degraded_fallback(scan, monkeypatch):
    fallbacks = []
    monkeypatch.setattr(transcripts, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    scan['rows'], scan['unreadable'] = [conversation('ok', words={0: 'series a'})], 2
    assert find()['unreadable'] == 2 and [f['to_mode'] for f in fallbacks] == ['partial_page']


def test_many_hits_in_one_conversation_are_capped_and_flagged(scan):
    scan['rows'] = [conversation('dense', count=20, words={i: f'series a point {i}' for i in range(0, 20, 2)})]
    (match,) = find()['matches']
    assert len(match['hits']) == search_views.TRANSCRIPT_HITS_PER_CONVERSATION and match['more_hits'] is True


def test_a_page_of_large_hits_stays_inside_the_serialized_budget_and_resumes(scan):
    cjk = '系列A轮融资' * 64  # escapes to six characters each on the wire
    scan['rows'] = [
        conversation(f'c{i}', count=10, words={j: f'series a {cjk}' for j in range(0, 10, 2)}) for i in range(10)
    ]
    result = find()
    served = [m['conversation']['id'] for m in result['matches']]
    assert 0 < len(served) < 10 and result['complete'] is False
    assert tool_response_serialized_chars(result) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
    # The cursor points at the last served conversation, so the next page starts with the first one left out.
    assert result['next_cursor'] == f'cursor-{len(served) - 1}' and result['examined'] == len(served)


def test_transcript_search_in_one_conversation(monkeypatch, scan):
    row = conversation('one', count=400, words={12: 'series a', 300: 'the series a again'})
    projections = []

    def fetch(uid, cid, extra_field_paths=None):
        projections.append(extra_field_paths)
        return dict(row) if cid == 'one' else None

    monkeypatch.setattr(transcripts, 'fetch_conversation_for_detail', fetch)
    result = find(conversation_id='one')
    assert [h['segment_index'] for h in result['matches'][0]['hits']] == [12, 300]
    assert result['complete'] is True and result['next_cursor'] is None and scan['calls'] == []
    with pytest.raises(ToolExecutionError) as error:
        find(conversation_id='missing')
    assert error.value.code == -32001
    row['is_locked'] = True
    with pytest.raises(ToolExecutionError) as error:
        find(conversation_id='one')
    assert error.value.code == -32002
    # The scoped read asks for the deferred flag the unscoped scanner excludes on.
    assert all('processing_deferred' in (paths or []) for paths in projections)
    row['is_locked'] = False
    row['processing_deferred'] = True
    assert find(conversation_id='one')['matches'] == []


@pytest.mark.parametrize(
    'arguments, code',
    [
        ({'query': ''}, -32602),
        ({'query': 'x' * 201}, -32602),
        ({'conversation_id': 'one', 'cursor': 'c'}, -32602),
        ({'conversation_id': 'one', 'start_date': '2026-11-01'}, -32602),
    ],
)
def test_transcript_search_argument_errors(scan, arguments, code):
    with pytest.raises(ToolExecutionError) as error:
        transcripts.search_transcripts(OWNER, {'query': 'series a', **arguments})
    assert error.value.code == code


def test_bad_cursor_and_scan_outage_are_distinct_errors(scan):
    scan['error'] = InvalidTranscriptCursor('bad')
    with pytest.raises(ToolExecutionError) as error:
        find(cursor='tampered')
    assert error.value.code == -32602
    scan['error'] = RuntimeError('firestore down')
    with pytest.raises(ToolExecutionError) as error:
        find()
    assert error.value.code == -32009 and error.value.http_status == 503
