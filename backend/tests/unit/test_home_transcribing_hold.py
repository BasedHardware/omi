"""Homegate phase 1: API presentation cannot become lifecycle authority."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.episodes import home_transcription_deadline_seconds, home_transcription_presentation_gate_enabled
from database import conversations
from routers import conversations as routes
from utils.conversations import home_step, transcribing_hold
from utils.episodes import home_membership
from utils.developer_item_reads import read_conversation_item
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing
from tests.unit.test_indexed_list_read_path import Db

NOW = datetime.now(timezone.utc)


def capture(**changes):
    return {
        'id': 'capture',
        'created_at': NOW - timedelta(minutes=4),
        'started_at': NOW - timedelta(minutes=4),
        'finished_at': NOW - timedelta(minutes=1),
        'status': 'completed',
        'source': 'desktop',
        'discarded': False,
        'deleted': False,
        'has_content': True,  # Closed raw audio, not a transcript receipt.
        'record_lane_owner': 'batch_live_v1',
        'home_transcription_pending_at': NOW,
        'home_transcription_deadline_at': NOW + timedelta(hours=2),
        'transcript_segments': [],
        'structured': {'title': '', 'overview': '', 'emoji': '', 'category': 'other'},
        **changes,
    }


@pytest.mark.parametrize('raw', ['', 'true', 'on', 'unexpected'])
def test_gate_defaults_on(monkeypatch, raw):
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', raw)
    assert home_transcription_presentation_gate_enabled()


@pytest.mark.parametrize('raw,expected', [('', 7200), ('bad', 7200), ('0', 7200), ('-1', 7200), ('600', 600)])
def test_deadline_setting(monkeypatch, raw, expected):
    monkeypatch.setenv('HOME_TRANSCRIPTION_DEADLINE_SECONDS', raw)
    assert home_transcription_deadline_seconds() == expected


@pytest.mark.parametrize(
    'elapsed,title,status',
    [
        (0, 'Transcribing…', 'processing'),
        (7200, "Couldn't transcribe", 'completed'),
        (7201, "Couldn't transcribe", 'completed'),
    ],
)
def test_deadline_decay_and_raw_state(elapsed, title, status):
    row = capture()
    before = deepcopy(row)
    wire = transcribing_hold.project(row, now=NOW + timedelta(seconds=elapsed))
    assert wire['status'] == status
    assert wire['structured']['title'] == title
    assert conversations.is_visible_conversation(wire)
    assert row == before
    assert conversations.prepare_conversation_for_read(row, 'u')['status'] == 'completed'


@pytest.mark.parametrize(
    'changes',
    [
        {'transcript_segments': [{'text': 'landed speech'}]},
        {'structured': {'title': 'A real title'}},
        {'user_title': 'My title'},
        {'record_projection_revision': 1},
        {'record_lane_owner': 'legacy_final_pass_v1'},
        {'home_transcription_deadline_at': None},
        {'status': 'processing'},
    ],
)
def test_finished_or_unrelated_rows_untouched(changes):
    row = capture(**changes)
    assert transcribing_hold.project(row) is row


@pytest.mark.parametrize('value', ['false', '0', 'off', 'no'])
def test_kill_switch_restores_stored_presentation(monkeypatch, value):
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', value)
    row = capture()
    assert transcribing_hold.project(row) is row


@pytest.mark.parametrize('overdue', [False, True])
def test_home_collector_keeps_even_short_pending_and_overdue_rows(monkeypatch, overdue):
    row = capture(
        started_at=NOW - timedelta(seconds=45),
        finished_at=NOW - timedelta(seconds=20),
        home_transcription_deadline_at=NOW + timedelta(seconds=-1 if overdue else 7200),
    )
    _install_listing(monkeypatch, {'capture': row})
    assert not conversations.is_visible_conversation(row)
    assert conversations.is_visible_conversation(row, presentation=True)
    page = conversations.get_conversations_without_photos('u', limit=1, offset=0, presentation=True)
    assert [r['id'] for r in page] == ['capture']
    assert page[0]['status'] == 'completed'  # Workers use this same authoritative reader.
    wire = transcribing_hold.project(page[0])
    assert wire['structured']['title'] == ("Couldn't transcribe" if overdue else 'Transcribing…')


@pytest.mark.parametrize(
    'changes',
    [
        {'deleted': True},
        {'discarded': True},
        {'dream_duplicate_of': 'other'},
        {'sync_bridge_pending': {'expires_at': NOW.timestamp() + 7200}},
    ],
)
def test_gate_does_not_bypass_custody_visibility(changes):
    assert not conversations.is_visible_conversation(capture(**changes))


@pytest.fixture
def api(monkeypatch):
    row = capture()
    monkeypatch.setattr(routes.conversations_db, 'get_conversations_without_photos', lambda *a, **k: [deepcopy(row)])
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a, **k: deepcopy(row))
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    monkeypatch.setattr(home_membership, 'project_list', lambda uid, rows, *a, **k: rows)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        yield client, row


@pytest.mark.parametrize('overdue', [False, True])
def test_list_and_detail_wire_serialization(api, overdue):
    client, row = api
    row['home_transcription_deadline_at'] = NOW + timedelta(seconds=-1 if overdue else 7200)
    expected = "Couldn't transcribe" if overdue else 'Transcribing…'
    for url in ('/v1/conversations', '/v1/conversations/capture'):
        response = client.get(url)
        assert response.status_code == 200, response.text
        wire = response.json()[0] if url == '/v1/conversations' else response.json()
        assert wire['structured']['title'] == expected
        assert wire['status'] == ('completed' if overdue else 'processing')
        assert 'home_transcription_deadline_at' not in wire  # Server-owned clock.
    assert row['status'] == 'completed' and row['structured']['title'] == ''


def test_gate_disables_writer_only_conditional_get_before_query(api, monkeypatch):
    client, _ = api
    start = Mock(wraps=routes.ListVersionCheck.start)
    monkeypatch.setattr(routes.ListVersionCheck, 'start', start)
    response = client.get('/v1/conversations', headers={'If-None-Match': 'old-writer-version'})
    assert response.status_code == 200
    assert start.call_args.args[0] is None
    assert 'etag' not in response.headers


@pytest.mark.parametrize('include_transcript', [False, True])
def test_developer_detail_projects_before_transcript_omission(include_transcript):
    row = capture()
    wire = read_conversation_item(
        'capture',
        include_transcript,
        SimpleNamespace(uid='u'),
        None,
        conversations_db=SimpleNamespace(get_conversation=lambda *a: deepcopy(row)),
        cache_client=lambda: None,
        check_transcript=lambda *a, **k: None,
        populate_speaker_names=lambda *a, **k: None,
        populate_folder_names=lambda *a, **k: None,
        audit=lambda **k: None,
    )
    assert wire['status'] == 'processing'
    assert wire['structured']['title'] == 'Transcribing…'


@pytest.mark.parametrize('revision', [None, 1])
def test_indexed_list_carries_clock_and_honors_transcript_receipt(monkeypatch, revision):
    row = capture(record_projection_revision=revision, updated_at=NOW, memory_id='capture')
    db = Db([row])
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    rows = conversations.get_conversations_without_photos('u', list_fields_only=True)
    assert len(rows) == 1
    assert 'transcript_segments' not in rows[0]
    assert rows[0]['home_transcription_deadline_at'] == row['home_transcription_deadline_at']
    wire = transcribing_hold.project(rows[0])
    assert wire['status'] == ('completed' if revision else 'processing')
    assert wire['structured']['title'] == ('' if revision else 'Transcribing…')


def test_kill_switch_restores_api_wire(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', 'off')
    for path in ('/v1/conversations', '/v1/conversations/capture'):
        result = client.get(path)
        assert result.status_code == 200
        wire = result.json()[0] if path == '/v1/conversations' else result.json()
        assert wire['status'] == 'completed'
        assert wire['structured']['title'] == ''


def test_shared_detail_uses_same_wire_projection(api, monkeypatch):
    client, row = api
    row['visibility'] = 'shared'
    monkeypatch.setattr(routes.redis_db, 'get_conversation_uid', lambda cid: 'u')
    monkeypatch.setattr(routes, 'account_deletion_blocks_user_work', lambda uid: False)
    result = client.get('/v1/conversations/capture/shared')
    assert result.status_code == 200, result.text
    assert result.json()['structured']['title'] == 'Transcribing…'


def test_mcp_rest_detail_uses_same_title(monkeypatch):
    from routers import mcp

    monkeypatch.setattr(mcp.mcp_conversation_handlers, 'fetch_conversation_for_detail', lambda *a, **k: capture())
    monkeypatch.setattr(mcp, 'populate_speaker_names', lambda *a: None)
    result = mcp.get_conversation_by_id('capture', uid='u')
    assert result.structured.title == 'Transcribing…'
    assert set(transcribing_hold.READ_FIELDS) <= set(mcp._REST_CONVERSATION_DETAIL_EXTRA_FIELD_PATHS)


def test_stamped_capture_remains_completed_for_batch_replacement():
    from tests.unit.test_batch_pipeline_live import recording, incoming
    from utils.batch_pipeline.live_projection import replace_record

    raw = recording(transcript_segments=[], structured={'title': ''})
    raw.update(home_transcription_pending_at=NOW, home_transcription_deadline_at=NOW + timedelta(hours=2))
    assert transcribing_hold.project(raw)['status'] == 'processing'
    result, _ = replace_record(raw, incoming(), {'start': 100, 'end': 102})
    assert result['status'] == 'completed'
    assert result['transcript_segments'][0]['text'] == 'Synthetic speech.'
    assert transcribing_hold.project(result) is result
    assert result['home_transcription_deadline_at'] == raw['home_transcription_deadline_at']


def test_star_replacement_retains_transcribing_presentation(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(routes.conversations_db, 'set_conversation_starred', lambda *a: None)
    response = client.patch('/v1/conversations/capture/starred?starred=true')
    assert response.status_code == 200, response.text
    assert response.json()['conversation']['structured']['title'] == 'Transcribing…'
    assert response.json()['conversation']['status'] == 'processing'


def test_folder_list_projects_the_same_title(monkeypatch):
    from routers import folders

    monkeypatch.setattr(folders.folders_db, 'get_folder', lambda *a: {'id': 'folder'})
    monkeypatch.setattr(folders.folders_db, 'get_conversations_in_folder', lambda *a, **k: [capture()])
    result = folders.get_folder_conversations('folder', limit=10, offset=0, include_discarded=False, uid='u')
    assert result[0].structured.title == 'Transcribing…'
    assert result[0].status.value == 'processing'


def test_mcp_list_requests_presentation_receipts_and_projects_title(monkeypatch):
    from routers import mcp
    from starlette.responses import Response

    fields = []

    def page(*a, **k):
        fields.extend(k['extra_field_paths'])
        return [capture()], None

    monkeypatch.setattr(mcp.mcp_conversation_handlers, 'conversation_cards_page_core', page)
    monkeypatch.setattr(mcp, 'rest_datetime_window', lambda *a: (None, None, None))
    monkeypatch.setattr(mcp, 'localize_timestamps', lambda row, zone: row)
    result = mcp.get_conversations(Response(), uid='u')
    assert result[0].structured.title == 'Transcribing…'
    assert set(transcribing_hold.READ_FIELDS) <= set(fields)


@pytest.mark.parametrize('presentation', [False, True])
def test_cursor_collector_only_releases_short_hold_for_product_reads(monkeypatch, presentation):
    from tests.unit.test_sync_donor_tombstone_visibility import _ListingDoc, _ListingQuery

    anchor = _ListingDoc('anchor', capture(id='anchor'))
    row = capture(started_at=NOW - timedelta(seconds=45), finished_at=NOW - timedelta(seconds=20))
    doc = _ListingDoc('capture', row)
    monkeypatch.setattr(conversations, 'document_data_with_revision', lambda snapshot: snapshot.to_dict())
    rows, _ = conversations._collect_cursor_conversation_page(
        _ListingQuery([anchor, doc]),
        limit=1,
        include_discarded=False,
        budget=None,
        bookmark=anchor,
        presentation=presentation,
    )
    assert [item['id'] for item in rows] == (['capture'] if presentation else [])


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_encoded_empty_capture_has_visible_overdue_exit(monkeypatch, level):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'homegate-hermetic-test-secret')
    row = capture(
        data_protection_level=level,
        started_at=NOW - timedelta(seconds=45),
        finished_at=NOW - timedelta(seconds=20),
        home_transcription_deadline_at=NOW - timedelta(seconds=1),
    )
    stored = conversations.encode_conversation_for_write('u', row, level=level)
    assert stored['transcript_segments_compressed']
    assert not isinstance(stored['transcript_segments'], list)
    assert not conversations.is_visible_conversation(stored)
    assert conversations.is_visible_conversation(stored, presentation=True)
    _install_listing(monkeypatch, {'capture': stored})
    page = conversations.get_conversations_without_photos('u', limit=1, presentation=True)
    assert page[0]['transcript_segments'] == []
    assert transcribing_hold.project(page[0])['structured']['title'] == "Couldn't transcribe"


@pytest.mark.parametrize('indexed', [False, True])
def test_stale_processing_list_projection_preserves_stored_state(monkeypatch, indexed):
    raw = capture(status='processing', finished_at=NOW - timedelta(hours=7), updated_at=NOW, memory_id='capture')
    db = Db([raw])
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: indexed)
    rows = conversations.get_conversations_without_photos('u', list_fields_only=True)
    assert len(rows) == 1
    assert rows[0]['finished_at'] == raw['finished_at']
    assert home_step.project(rows[0])['home_step'] == 'failed'
    assert rows[0]['status'] == 'processing'
    assert 'home_step' not in rows[0]


def test_stale_processing_failed_only_on_list_wire(api):
    client, raw = api
    raw.update(status='processing', finished_at=NOW - timedelta(hours=7))
    listed = client.get('/v1/conversations')
    detail = client.get('/v1/conversations/capture')
    assert listed.status_code == detail.status_code == 200
    assert listed.json()[0]['home_step'] == 'failed'
    assert listed.json()[0]['status'] == detail.json()['status'] == 'processing'
    assert 'home_step' not in detail.json()
    assert 'home_step' not in raw
