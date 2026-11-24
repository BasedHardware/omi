"""Homegate phase 1: API presentation cannot become lifecycle authority."""

import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import DeadlineExceeded

from config.episodes import (
    home_transcription_deadline_seconds,
    home_transcription_max_age_seconds,
    home_transcription_presentation_gate_enabled,
    home_transcription_queue_hold_enabled,
)
from database import conversations
from models.conversation import ProcessConversationRequest
from routers import conversations as routes
from tests.unit.test_batch_pipeline_live import incoming, recording
from tests.unit.test_indexed_list_read_path import Db
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing
from utils.batch_pipeline.live_projection import replace_record
from utils.conversations import home_step, transcribing_hold
from utils.developer_item_reads import read_conversation_item
from utils.episodes import home_membership
from utils.other.list_budget import ListReadBudget

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
        (7200, 'Transcribing…', 'processing'),
        (7201, 'Transcribing…', 'processing'),
        (86399, 'Transcribing…', 'processing'),
        (86400, "Couldn't transcribe", 'completed'),
        (86401, "Couldn't transcribe", 'completed'),
    ],
)
@pytest.mark.parametrize('queue_hold', ['true', 'false'])
def test_deadline_decay_and_raw_state(monkeypatch, elapsed, title, status, queue_hold):
    monkeypatch.setenv('HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED', queue_hold)
    if queue_hold == 'false' and elapsed >= 7200:
        title, status = "Couldn't transcribe", 'completed'
    row = capture(finished_at=NOW)
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
        started_at=NOW - timedelta(hours=25 if overdue else 0, seconds=45),
        finished_at=NOW - timedelta(hours=25 if overdue else 0, seconds=20),
        home_transcription_pending_at=NOW - timedelta(hours=25 if overdue else 0),
        home_transcription_deadline_at=NOW + timedelta(seconds=-1 if overdue else 7200),
    )
    _install_listing(monkeypatch, {'capture': row})
    assert conversations.is_visible_conversation(row) is overdue
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
    if overdue:
        row['finished_at'] = NOW - timedelta(hours=25)
        row['home_transcription_pending_at'] = NOW - timedelta(hours=25)
    expected = "Couldn't transcribe" if overdue else 'Transcribing…'
    for url in ('/v1/conversations', '/v1/conversations/capture'):
        response = client.get(url)
        assert response.status_code == 200, response.text
        wire = response.json()[0] if url == '/v1/conversations' else response.json()
        assert wire['structured']['title'] == expected
        assert wire['status'] == ('completed' if overdue else 'processing')
        assert 'home_transcription_deadline_at' not in wire  # Server-owned clock.
        # An expired wait with no failure receipt says so; a young wait carries nothing new.
        assert wire.get('transcription_wait') == ('overdue' if overdue else None)
    assert row['status'] == 'completed' and row['structured']['title'] == ''


def test_conditional_list_fetch_keeps_transcribing_presentation(api):
    client, row = api
    row['home_transcription_deadline_at'] = NOW + timedelta(seconds=7200)
    response = client.get('/v1/conversations', headers={'If-None-Match': 'W/"lp1-retired-validator"'})
    assert response.status_code == 200
    assert response.json()[0]['status'] == 'processing'
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
    raw = recording(transcript_segments=[], structured={'title': ''})
    raw.update(
        finished_at=NOW, home_transcription_pending_at=NOW, home_transcription_deadline_at=NOW + timedelta(hours=2)
    )
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
        started_at=NOW - timedelta(hours=25, seconds=45),
        finished_at=NOW - timedelta(hours=25, seconds=20),
        home_transcription_pending_at=NOW - timedelta(hours=25),
        home_transcription_deadline_at=NOW - timedelta(seconds=1),
    )
    stored = conversations.encode_conversation_for_write('u', row, level=level)
    assert stored['transcript_segments_compressed']
    assert not isinstance(stored['transcript_segments'], list)
    assert conversations.is_visible_conversation(stored)
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


@pytest.mark.parametrize('raw', ['', 'true', 'on', 'unexpected'])
def test_queue_hold_defaults_on(monkeypatch, raw):
    monkeypatch.setenv('HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED', raw)
    assert home_transcription_queue_hold_enabled()


@pytest.mark.parametrize('raw,expected', [('', 86400), ('bad', 86400), ('0', 86400), ('-1', 86400), ('600', 600)])
def test_queue_wait_setting(monkeypatch, raw, expected):
    monkeypatch.setenv('HOME_TRANSCRIPTION_MAX_AGE_SECONDS', raw)
    assert home_transcription_max_age_seconds() == expected


@pytest.mark.parametrize('surface', ['home_transcription', 'episode_transcription'])
@pytest.mark.parametrize('anchor_key', ['pending_at', 'created_at', 'stamp_only'])
def test_effective_deadline_is_stable_and_heals_old_stamps(monkeypatch, surface, anchor_key):
    monkeypatch.setenv('HOME_TRANSCRIPTION_MAX_AGE_SECONDS', '86400')
    row = {f'{surface}_deadline_at': NOW + timedelta(hours=2), 'updated_at': NOW + timedelta(days=5)}
    if anchor_key != 'stamp_only':
        key = f'{surface}_pending_at' if anchor_key == 'pending_at' else anchor_key
        row[key] = NOW.replace(tzinfo=None)  # Old naive timestamps are UTC.
    assert transcribing_hold.deadline(row, prefix=surface) == NOW + timedelta(hours=24)
    monkeypatch.setenv('HOME_TRANSCRIPTION_MAX_AGE_SECONDS', '3600')
    assert transcribing_hold.deadline(row, prefix=surface) == NOW + timedelta(hours=1)


@pytest.mark.parametrize('switch', ['false', '0', 'off', 'no'])
def test_queue_hold_kill_switch_restores_two_hour_failure(monkeypatch, switch):
    monkeypatch.setenv('HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED', switch)
    row = capture(finished_at=NOW)
    assert transcribing_hold.project(row, now=NOW + timedelta(hours=3))['structured']['title'] == "Couldn't transcribe"


@pytest.mark.parametrize('failure', [{'record_upload_failed': True}, {'finalization_status': 'dead_letter'}])
def test_explicit_failure_wins_while_capture_is_young(failure):
    row = capture(**failure)
    assert home_step.classify(row) == 'failed'
    wire = transcribing_hold.project(row, now=NOW)
    assert wire['structured']['title'] == "Couldn't transcribe"
    assert wire['status'] == 'completed'


def test_old_two_hour_stamp_heals_api_title_step_and_retry_without_writing(api):
    client, row = api
    row.update(
        finished_at=NOW - timedelta(hours=3),
        home_transcription_pending_at=NOW - timedelta(hours=3),
        home_transcription_deadline_at=NOW - timedelta(hours=1),
        summary_retryable=True,  # Even a stale marker cannot offer a summary retry on queued audio.
    )
    before = deepcopy(row)
    for url in ('/v1/conversations', '/v1/conversations/capture'):
        response = client.get(url)
        assert response.status_code == 200, response.text
        wire = response.json()[0] if url == '/v1/conversations' else response.json()
        assert wire['structured']['title'] == 'Transcribing…'
        assert wire['status'] == 'processing'
        assert wire['summary_retryable'] is False
        if url == '/v1/conversations':
            assert wire['home_step'] == 'transcribing'
    assert row == before


@pytest.mark.parametrize('lane', ['batch_live_v1', 'batch_sync_v1'])
@pytest.mark.parametrize('capture_age', [timedelta(hours=25), timedelta(days=16)])
def test_late_upload_wait_starts_at_server_pending_clock(lane, capture_age):
    row = capture(
        record_lane_owner=lane,
        finished_at=NOW - capture_age,
        home_transcription_pending_at=NOW,
        updated_at=NOW,
        home_transcription_deadline_at=NOW + timedelta(days=5),
    )
    assert home_step.classify(row) == 'transcribing'
    assert transcribing_hold.project(row, now=NOW)['structured']['title'] == 'Transcribing…'
    assert transcribing_hold.project(row, now=NOW + timedelta(hours=24))['structured']['title'] == "Couldn't transcribe"


def test_episode_iso_stamp_remains_supported():
    row = {'episode_transcription_deadline_at': (NOW + timedelta(hours=2)).isoformat()}
    assert transcribing_hold.deadline(row, prefix='episode_transcription') == NOW + timedelta(hours=24)


@pytest.mark.parametrize('prefix', ['home_transcription', 'episode_transcription'])
@pytest.mark.parametrize('key', ['pending_at', 'created_at', 'deadline_at'])
def test_iso_clock_is_parsed_before_selecting_the_first_valid_anchor(prefix, key):
    row = {'finished_at': NOW - timedelta(days=16), 'updated_at': NOW}
    field = key if key == 'created_at' else f'{prefix}_{key}'
    row[field] = (NOW - timedelta(hours=23 if key == 'deadline_at' else 25)).isoformat()
    assert transcribing_hold.deadline(row, prefix=prefix) == NOW - timedelta(hours=1)


@pytest.mark.parametrize('queue_hold,title', [('true', 'Transcribing…'), ('false', "Couldn't transcribe")])
def test_iso_capture_end_does_not_shorten_server_wait(monkeypatch, queue_hold, title):
    monkeypatch.setenv('HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED', queue_hold)
    row = capture(
        finished_at=(NOW - timedelta(hours=25)).isoformat(),
        home_transcription_pending_at=NOW - timedelta(hours=3),
        home_transcription_deadline_at=NOW - timedelta(hours=1),
    )
    assert transcribing_hold.project(row, now=NOW)['structured']['title'] == title


@pytest.mark.parametrize('invalid', [None, 'invalid', '', 123])
def test_invalid_capture_clock_does_not_override_a_valid_iso_pending_clock(invalid):
    row = capture(finished_at=invalid, home_transcription_pending_at=(NOW - timedelta(hours=3)).isoformat())
    assert transcribing_hold.deadline(row) == NOW + timedelta(hours=21)


@pytest.mark.parametrize('prefix', ['home_transcription', 'episode_transcription'])
def test_stamp_only_wait_uses_the_configured_deadline_interval(monkeypatch, prefix):
    monkeypatch.setenv('HOME_TRANSCRIPTION_DEADLINE_SECONDS', '600')
    row = {f'{prefix}_deadline_at': NOW + timedelta(seconds=600), 'created_at': NOW - timedelta(days=16)}
    assert transcribing_hold.deadline(row, prefix=prefix) == NOW + timedelta(hours=24)


@pytest.mark.parametrize('prefix', ['home_transcription', 'episode_transcription'])
@pytest.mark.parametrize('invalid', [None, 'invalid', '', 123])
def test_deadline_recovers_server_wait_before_old_creation(prefix, invalid):
    row = {
        f'{prefix}_pending_at': invalid,
        f'{prefix}_deadline_at': (NOW - timedelta(hours=1)).isoformat(),
        'created_at': NOW - timedelta(days=16),
        'finished_at': NOW - timedelta(days=16),
    }
    assert transcribing_hold.deadline(row, prefix=prefix) == NOW + timedelta(hours=21)


@pytest.mark.parametrize('prefix', ['home_transcription', 'episode_transcription'])
def test_later_upload_revision_restarts_a_bounded_server_wait(prefix):
    row = {f'{prefix}_pending_at': NOW - timedelta(hours=25), f'{prefix}_deadline_at': NOW - timedelta(hours=23)}
    assert transcribing_hold.deadline(row, prefix=prefix) == NOW - timedelta(hours=1)
    # A read or a repair update never renews the persisted wait.
    row['updated_at'] = NOW
    assert transcribing_hold.deadline(row, prefix=prefix) == NOW - timedelta(hours=1)
    # Only a writer admitting a new wait can stamp a new 24h window.
    row.update({f'{prefix}_pending_at': NOW, f'{prefix}_deadline_at': NOW + timedelta(hours=2)})
    assert transcribing_hold.deadline(row, prefix=prefix) == NOW + timedelta(hours=24)


def test_overdue_wait_without_failure_receipt_is_marked_waiting():
    row = capture(finished_at=NOW)
    wire = transcribing_hold.project(row, now=NOW + timedelta(hours=25))
    assert wire['structured']['title'] == "Couldn't transcribe"
    assert wire['transcription_wait'] == 'overdue'
    assert 'transcription_wait' not in transcribing_hold.project(row, now=NOW)


@pytest.mark.parametrize(
    'failure', [{'record_upload_failed': True}, {'finalization_status': 'dead_letter'}, {'status': 'failed'}]
)
def test_failure_receipt_is_never_marked_waiting(failure):
    row = capture(finished_at=NOW, **failure)
    for elapsed in (0, 25 * 3600):
        wire = transcribing_hold.project(row, now=NOW + timedelta(seconds=elapsed))
        if wire is not row:
            assert wire['structured']['title'] == "Couldn't transcribe"
        assert 'transcription_wait' not in wire


def admission_job(cid='capture', state='allowance_held', **fields):
    decision = (
        {'outcome': 'held', 'reason': 'allowance_exhausted'}
        if state in {'allowance_held', 'retry'}
        else {'outcome': 'unattempted'}
    )
    return {'owner_id': 'u', 'conversation_id': cid, 'state': state, 'compute_decision': decision, **fields}


@pytest.fixture
def bind_admission_lookup(monkeypatch):
    def bind(find_jobs):
        store = object()

        def read(source, *args, **kwargs):
            assert source is store
            return find_jobs(*args, **kwargs)

        monkeypatch.setattr(transcribing_hold, 'read_admission_jobs', read)
        return store

    return bind


@pytest.mark.parametrize('kind', ['ordinary', 'no_clock', 'titled'])
def test_list_and_detail_use_current_admission_then_clear_on_transcript(api, monkeypatch, kind, bind_admission_lookup):
    client, row = api
    row.update(
        finished_at=NOW - timedelta(hours=26),
        home_transcription_pending_at=NOW - timedelta(hours=26),
        home_transcription_deadline_at=NOW - timedelta(hours=24),
        summary_retryable=True,
    )
    if kind == 'no_clock':
        row.pop('home_transcription_pending_at')
        row.pop('home_transcription_deadline_at')
        row['record_audio_closed'] = True
    if kind == 'titled':
        row.update(user_title='My capture', structured={**row['structured'], 'title': 'My capture'})
    jobs = []
    reads = []

    def find_jobs(uid, ids, *, limit, timeout):
        reads.append((uid, ids))
        assert limit <= 256 and 0 < timeout <= 1.5
        return jobs

    store = bind_admission_lookup(find_jobs)
    read_admissions = transcribing_hold.read_admissions
    monkeypatch.setattr(
        transcribing_hold,
        'read_admissions',
        lambda uid, rows, **kwargs: read_admissions(uid, rows, store=store, now=NOW, **kwargs),
    )

    def home_and_detail():
        home = client.get('/v1/conversations')
        detail = client.get('/v1/conversations/capture')
        assert home.status_code == detail.status_code == 200
        return home.json()[0], detail.json()

    before = deepcopy(row)
    for wire in home_and_detail():
        assert wire.get('transcription_wait') == ('overdue' if kind == 'ordinary' else None)
        assert 'transcription_admission' not in wire

    jobs[:] = [admission_job()]
    for wire in home_and_detail():
        assert wire.get('transcription_wait') == ('overdue' if kind == 'ordinary' else None)
        assert wire['transcription_admission'] == 'allowance_held'
        if kind == 'titled':
            assert wire['structured']['title'] == 'My capture'

    jobs[:] = [admission_job(state='ready', compute_decision={'outcome': 'unattempted'}, available_at=NOW.timestamp())]
    home, detail = home_and_detail()
    assert home['home_step'] == 'transcribing'
    for wire in (home, detail):
        assert wire['status'] == 'processing'
        assert wire['transcription_admission'] == 'processing'
        assert 'transcription_wait' not in wire
        assert wire['summary_retryable'] is False
        if kind == 'titled':
            assert wire['structured']['title'] == 'My capture'
    assert row == before
    assert reads == [('u', ['capture'])] * 6

    final_title = 'My capture' if kind == 'titled' else 'Landed transcript'
    row.update(record_projection_revision=1, structured={**row['structured'], 'title': final_title})
    for wire in home_and_detail():
        assert wire['structured']['title'] == final_title
        assert wire['status'] == 'completed'
        assert 'transcription_admission' not in wire
    assert len(reads) == 6


def test_admissions_require_current_owner_and_usable_job_state(bind_admission_lookup):
    current = NOW.timestamp()
    jobs = [
        admission_job('held'),
        admission_job('held_legacy_retry', state='retry'),
        admission_job('budget', compute_decision={'outcome': 'held', 'reason': 'budget_exhausted'}),
        admission_job(
            'sticky_hold', state='retry', compute_decision={}, last_policy_hold={'reason': 'allowance_exhausted'}
        ),
        admission_job('other_owner', owner_id='someone-else'),
        admission_job('locked'),
        admission_job('deleted'),
        admission_job('discarded'),
        admission_job('failed_receipt'),
        admission_job('no_clock_or_audio_proof'),
        admission_job('live_empty_stub'),
        admission_job('settled_empty'),
        admission_job('existing_notes'),
        admission_job('expired_lease', state='leased', lease_until=current - 1),
        admission_job('old_ready', state='ready', available_at=(NOW - timedelta(days=2)).timestamp()),
        admission_job(
            'legacy_requeue',
            state='ready',
            available_at=current,
            compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'},
        ),
        admission_job('in_flight', state='leased', lease_until=current + 1),
        admission_job('result_ready', state='result_ready', ready_at=current - 1),
        admission_job('committed', state='committed', ready_at=current - 1),
        admission_job('failed_sibling'),
        admission_job('failed_sibling', state='quarantined'),
        admission_job('expired_sibling', state='ready', available_at=current),
        admission_job('expired_sibling', state='dead'),
        admission_job('privacy_blocked_sibling', state='ready', available_at=current),
        admission_job('privacy_blocked_sibling', state='privacy_blocked'),
        admission_job('projection_held', state='committed', ready_at=current, recovery_state='held'),
    ]
    rows = [capture(id=cid) for cid in dict.fromkeys(job['conversation_id'] for job in jobs)]
    rows += [capture(id='missing_job')]
    excluded = {
        'locked': {'is_locked': True},
        'deleted': {'deleted': True},
        'discarded': {'discarded': True},
        'failed_receipt': {'record_upload_failed': True},
        'no_clock_or_audio_proof': {'home_transcription_deadline_at': None},
        'live_empty_stub': {'status': 'in_progress', 'has_content': False},
        'settled_empty': {'record_projection_revision': 1, 'record_transcription_empty': {'version': 1}},
        'existing_notes': {'structured': {'title': '', 'overview': 'Existing notes'}},
    }
    for row in rows:
        row.update(excluded.get(row['id'], {}))

    def find_jobs(uid, ids, **kwargs):
        assert uid == 'u'
        assert set(ids).isdisjoint(excluded)
        return jobs

    store = bind_admission_lookup(find_jobs)
    assert transcribing_hold.read_admissions('u', rows, store=store, now=NOW) == {
        'held': 'allowance_held',
        'held_legacy_retry': 'allowance_held',
        'in_flight': 'processing',
        'result_ready': 'processing',
        'committed': 'processing',
    }


def test_admissions_batch_conversation_ids_and_stop_on_truncation(monkeypatch, bind_admission_lookup):
    rows = [capture(id=f'capture-{i}') for i in range(75)]
    reads = []

    def find_jobs(uid, ids, *, limit, timeout):
        reads.append((ids, limit))
        if len(reads) == 1:
            return [admission_job(ids[0])]
        return [admission_job(cid) for cid in ids[:limit]]

    monkeypatch.setattr(transcribing_hold, '_MAX_ADMISSION_JOB_READS', 3)
    store = bind_admission_lookup(find_jobs)
    assert transcribing_hold.read_admissions('u', rows, store=store, now=NOW) == {'capture-0': 'allowance_held'}
    assert [(len(ids), limit) for ids, limit in reads] == [(30, 3), (30, 2)]


def test_admissions_charge_empty_queries_to_the_request_budget(bind_admission_lookup):
    rows = [capture(id=f'capture-{i}') for i in range(75)]
    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 1, max_documents=2)
    limits = []

    def find_jobs(uid, ids, *, limit, timeout):
        limits.append(limit)
        return []

    store = bind_admission_lookup(find_jobs)
    assert transcribing_hold.read_admissions('u', rows, budget=budget, store=store, now=NOW) == {}
    assert budget.docs_scanned == 2
    assert limits == [2, 1]


def test_admission_lookup_timeout_preserves_existing_wait(bind_admission_lookup):
    def timeout(*args, **kwargs):
        raise DeadlineExceeded('lookup deadline')

    store = bind_admission_lookup(timeout)
    assert transcribing_hold.read_admissions('u', [capture()], store=store, now=NOW) == {}


@pytest.mark.parametrize('value', ['allowance_held', 'processing'])
def test_client_or_stored_payload_cannot_supply_transcription_admission(value):
    state = {'transcription_admission': value}
    request = ProcessConversationRequest.model_validate(state)
    assert 'transcription_admission' not in request.model_dump()
    payload = {'id': 'capture', **state}
    assert 'transcription_admission' not in conversations.encode_conversation_for_write('u', payload)
    assert 'transcription_admission' not in conversations.prepare_conversation_for_read(payload, 'u')
    assert payload['transcription_admission'] == value
