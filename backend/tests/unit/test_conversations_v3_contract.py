"""Synthetic v3 switch, read boundaries, capture and released-wire contracts."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from config import conversations_v3 as switch
from database import conversations as db
from routers import conversations as routes, episodes
from utils.conversations.v3 import service, audio, triggers
from utils.conversations.processing_trigger import ProcessingTrigger


@pytest.mark.parametrize(
    'stage,seen,cohort,expected',
    [
        ('beta', False, False, False),
        ('beta', True, False, True),
        ('cohort', True, False, False),
        ('cohort', False, True, True),
        ('all', False, False, True),
        ('invalid', True, False, False),
    ],
)
def test_switch_is_per_owner_not_device(monkeypatch, stage, seen, cohort, expected):
    monkeypatch.setenv('CONVERSATIONS_V3_STAGE', stage)
    monkeypatch.delenv('CONVERSATIONS_V3', raising=False)
    monkeypatch.setattr(switch.client_gate, 'client_seen_cached', lambda uid: seen)
    monkeypatch.setattr(switch, 'in_rollout_cohort', lambda uid, key: cohort)
    assert switch.conversations_v3_enabled('synthetic') is expected
    monkeypatch.setenv('CONVERSATIONS_V3', 'off')
    assert switch.conversations_v3_enabled('synthetic') is False


def test_beta_call_refreshes_marker_before_v3_check(monkeypatch):
    calls = []
    monkeypatch.setattr(routes.client_gate, 'note_client_seen', lambda uid: calls.append('seen'))
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: calls.append('check') or False)
    assert routes.get_live_conversation('synthetic', 'beta') == {'v3': False, 'conversation': None}
    assert calls == ['seen', 'check']


@pytest.mark.parametrize('include', [False, True])
def test_visibility_predicate_requires_recording_opt_in(include):
    row = {'recording': True, 'status': 'completed', 'discarded': False}
    assert db.is_visible_conversation(row, include_recordings=include) is include
    assert db.is_visible_conversation({**row, 'recording': False, 'home_hidden': True})


@pytest.mark.parametrize('allow', [False, True])
def test_by_id_recording_opt_in(monkeypatch, allow):
    monkeypatch.setattr(db, 'get_conversation', lambda *a, **kw: {'id': 'r', 'recording': True})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    if allow:
        assert routes._get_valid_conversation_by_id('synthetic', 'r', allow_recording=True)['id'] == 'r'
    else:
        with pytest.raises(HTTPException) as error:
            routes._get_valid_conversation_by_id('synthetic', 'r')
        assert error.value.status_code == 404


@pytest.mark.parametrize('trigger', list(ProcessingTrigger))
def test_all_processing_triggers_take_no_model_recording_path(monkeypatch, trigger):
    from utils.conversations import lifecycle
    from models.conversation import Conversation

    at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    row = Conversation(id='r', created_at=at, started_at=at, finished_at=at, structured={}, recording=True)
    forbidden = MagicMock(side_effect=AssertionError('recording reached processing body'))
    monkeypatch.setattr(lifecycle, 'complete', lambda *a: True)
    monkeypatch.setattr(db, 'get_conversation', lambda *a: {'status': 'completed', 'recording': True})
    marked = []
    monkeypatch.setattr(service, 'changed', lambda *a, **kw: marked.append((a, kw)))
    disposition = []
    result = service.recording_short_path(forbidden)(
        'synthetic', 'en', row, trigger=trigger, derived_effects_disposition_observer=disposition.append
    )
    assert disposition[0].value == 'terminal_no_derived_effects'
    assert result.status.value == 'completed'
    assert marked
    forbidden.assert_not_called()


def test_non_v3_processing_is_unchanged():
    original = MagicMock(return_value='ordinary')
    assert service.recording_short_path(original)('synthetic', 'en', object()) == 'ordinary'
    original.assert_called_once()


@pytest.mark.parametrize(
    'source,marked',
    [('omi', True), ('phone', True), ('desktop', False), ('phone_call', False), ('external_integration', False)],
)
def test_only_pendant_creation_is_marked(monkeypatch, source, marked):
    monkeypatch.setattr(triggers, 'conversations_v3_enabled', lambda uid: True)
    row = {'source': source, 'data_protection_level': 'standard'}
    triggers.mark_new('synthetic', row)
    assert bool(row.get('recording')) is marked
    assert bool(row.get('terminal_no_derived_effects')) is marked


def test_kill_switch_does_not_suppress_existing_recordings(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3', 'off')
    called = []
    monkeypatch.setattr(service.store, 'mark_pending', lambda *a, **kw: True)
    monkeypatch.setattr(triggers, 'enqueue', lambda uid: called.append(uid))
    service.changed('synthetic', 'already-marked')
    assert called == ['synthetic']


def test_released_episode_and_home_kind_fallback(monkeypatch):
    monkeypatch.setattr(episodes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(episodes.client_gate, 'note_client_seen', lambda uid: None)
    assert episodes.get_live_episode('synthetic', 'beta') == {'enabled': False, 'episode': None}
    # The released decoder's closed vocabulary remains unchanged.
    from models.home_feed import HomeFeedCard

    assert set(HomeFeedCard.model_fields['kind'].annotation.__args__) == {'episode', 'conversation'}


def test_audio_alias_is_owner_checked(monkeypatch):
    calls = []

    def load(uid, cid):
        calls.append((uid, cid))
        if cid == 'c':
            return {'id': 'c'}
        if cid != 'r':
            return None
        return {'recording': True, 'claims': [{'conversation_id': 'c'}], 'audio_files': [{'id': 'file'}]}

    monkeypatch.setattr(db, 'get_conversation', load)
    assert audio.resolve('synthetic', {'id': 'c'}, {'id': 'alias', 'recording_id': 'r', 'recording_file_id': 'file'})[
        :2
    ] == ('r', {'id': 'file'})
    assert calls == [('synthetic', 'c'), ('synthetic', 'r')]
    with pytest.raises(HTTPException):
        audio.resolve('synthetic', {'id': 'different'}, {'id': 'file', 'recording_id': 'r'})


def test_deleted_manifest_spans_preserve_neighbours():
    assert audio.subtract_spans(0, 100, [(20, 30), (60, 120)]) == [(0, 20), (30, 60)]


def test_index_planted_recording_is_rejected_on_hydration(monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    client = StrictFirestore(
        {
            ('users', 'synthetic', 'conversations', 'r'): {'id': 'r', 'recording': True, 'status': 'completed'},
            ('users', 'synthetic', 'conversations', 'short'): {
                'id': 'short',
                'home_hidden': True,
                'status': 'completed',
            },
        }
    )
    monkeypatch.setattr(db, 'db', client)
    assert [r['id'] for r in db._get_conversations_by_id('synthetic', ['r', 'short'])] == ['short']
    assert len(db._get_conversations_by_id('synthetic', ['r', 'short'], include_recordings=True)) == 2


def test_counts_include_legacy_documents_without_recording_field(monkeypatch):
    from tests.unit.test_sync_donor_tombstone_visibility import _install_listing

    at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    rows = {
        cid: {'id': cid, 'created_at': at, 'status': 'completed', 'discarded': False, **fields}
        for cid, fields in [
            ('legacy', {}),
            ('ordinary', {'recording': False}),
            ('recording', {'recording': True}),
            ('short', {'home_hidden': True}),
        ]
    }
    _install_listing(monkeypatch, rows)
    assert db.get_conversations_count('synthetic') == 3
    assert db.get_conversations_count('synthetic', hide_home=True) == 2


@pytest.mark.parametrize('update_only', [False, True])
def test_recordings_never_embed_even_on_completed_replay(monkeypatch, update_only):
    from types import SimpleNamespace
    from utils.conversations import process_conversation as process

    forbidden = MagicMock(side_effect=AssertionError('recording embedded'))
    monkeypatch.setattr(process, 'generate_embedding', forbidden)
    assert process.save_structured_vector('synthetic', SimpleNamespace(recording=True), update_only=update_only)
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    'statuses,capture', [('in_progress', True), ('completed', False), ('processing,completed', False)]
)
def test_released_capture_poll_keeps_recording_identity(monkeypatch, statuses, capture):
    from types import SimpleNamespace
    from utils.episodes import home_membership

    class CapturedRead(BaseException):
        pass

    bound = {}

    def read(*args, **kwargs):
        bound.update(kwargs)
        raise CapturedRead()

    monkeypatch.setattr(routes, 'home_transcription_presentation_gate_enabled', lambda: False)
    monkeypatch.setattr(routes, 'home_step_projection_enabled', lambda: False)
    monkeypatch.setattr(home_membership, 'held_for', lambda request: False)
    monkeypatch.setattr(home_membership, 'live_suppression_for', lambda *a: False)
    monkeypatch.setattr(routes.ListVersionCheck, 'start', lambda *a: SimpleNamespace(not_modified=None))
    monkeypatch.setattr(routes, 'list_read_budget_for_request', lambda *a, **kw: None)
    monkeypatch.setattr(db, 'get_conversations_without_photos', read)
    with pytest.raises(CapturedRead):
        routes.get_conversations(
            uid='synthetic',
            statuses=statuses,
            sources=None,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
        )
    assert bound['include_recordings'] is capture
    assert bound['capture_only'] is capture
    if capture:
        assert db.is_visible_conversation(
            {'id': 'recording', 'recording': True, 'status': 'in_progress'}, include_recordings=True, capture_only=True
        )
        assert not db.is_visible_conversation(
            {'id': 'derived', 'v3_derived': True, 'status': 'in_progress'}, include_recordings=True, capture_only=True
        )


@pytest.mark.parametrize(
    'include_recordings,hide_home,expected', [(True, False, 'r'), (False, True, 'good'), (False, False, 'short')]
)
def test_cursor_refills_after_recording_and_hidden_rows(include_recordings, hide_home, expected):
    from tests.unit.test_sync_donor_tombstone_visibility import _ListingDoc, _ListingQuery

    anchor = _ListingDoc('anchor', {})
    docs = [anchor] + [
        _ListingDoc(cid, {'status': 'completed', 'discarded': False, **fields})
        for cid, fields in [('r', {'recording': True}), ('short', {'home_hidden': True}), ('good', {})]
    ]
    rows, last = db._collect_cursor_conversation_page(
        _ListingQuery(docs),
        limit=1,
        include_discarded=False,
        budget=None,
        bookmark=anchor,
        include_recordings=include_recordings,
        hide_home=hide_home,
    )
    assert len(rows) == 1 and rows[0]['id'] == expected
    assert last.id == expected


@pytest.mark.parametrize('recording', [False, True])
def test_live_response_is_compact_and_never_a_recording(monkeypatch, recording):
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(
        db,
        'get_conversations_without_photos',
        lambda *a, **kw: [
            {
                'id': 'c',
                'started_at': datetime(2026, 11, 16, tzinfo=timezone.utc),
                'status': 'in_progress',
                'created_at': datetime(2026, 11, 16, tzinfo=timezone.utc),
                'recording': recording,
                'transcript_segments': [{'text': 'private capture'}],
                'structured': {'title': 'Plan', 'emoji': '🌳', 'overview': 'omit'},
            }
        ],
    )
    result = routes.get_live_conversation('u', 'store')
    if recording:
        assert result['conversation'] is None
    else:
        from models.conversation import ConversationsLiveResponse

        wire = ConversationsLiveResponse(**result).model_dump(exclude_unset=True)
        assert 'transcript_segments' not in wire['conversation']
        assert wire['conversation']['structured'] == {'title': 'Plan', 'emoji': '🌳'}


def test_merge_rejects_recording_before_admission(monkeypatch):
    from fastapi import BackgroundTasks
    from models.conversation import MergeConversationsRequest

    monkeypatch.setattr(db, 'get_conversation', lambda *a, **kw: {'id': 'r', 'recording': True})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    with pytest.raises(HTTPException) as error:
        routes.merge_conversations(MergeConversationsRequest(conversation_ids=['r', 'c']), BackgroundTasks(), 'u')
    assert error.value.status_code == 404


def test_reprocess_rejects_recording_before_processing(monkeypatch):
    monkeypatch.setattr(db, 'get_conversation', lambda *a, **kw: {'id': 'r', 'recording': True})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    with pytest.raises(HTTPException) as error:
        routes.reprocess_conversation('r', uid='u')
    assert error.value.status_code == 404


def test_joan_rejects_recording_before_prompt(monkeypatch):
    from routers import users

    monkeypatch.setattr(users, 'get_conversation', lambda *a: {'id': 'r', 'recording': True})
    monkeypatch.setattr(users, 'followup_question_prompt', lambda *a: pytest.fail('raw capture sent to prompt'))
    with pytest.raises(HTTPException) as error:
        users.delete_followup_question_endpoint('r', 'u')
    assert error.value.status_code == 404


def test_lapsed_beta_marker_restores_legacy_capture_and_episode_admission(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_STAGE', 'beta')
    monkeypatch.delenv('CONVERSATIONS_V3', raising=False)
    monkeypatch.setattr(switch, 'in_rollout_cohort', lambda *a: False)
    monkeypatch.setattr(switch.client_gate, 'client_seen_cached', lambda uid: False)
    monkeypatch.setattr(triggers, 'conversations_v3_enabled', switch.conversations_v3_enabled)
    row = {'source': 'omi', 'data_protection_level': 'standard'}
    triggers.mark_new('u', row)
    assert 'recording' not in row and 'v3_pending' not in row
    monkeypatch.setattr(episodes, 'conversations_v3_enabled', switch.conversations_v3_enabled)
    monkeypatch.setattr(episodes, 'episodes_enabled_for', lambda *a: True)
    monkeypatch.setattr(episodes, 'client_channel_admitted', lambda *a: True)
    assert episodes._admitted('u', 'store') is True


def test_episode_admission_is_cached_once_per_request(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    calls = []
    monkeypatch.setattr(episodes, 'conversations_v3_enabled', lambda uid: calls.append(uid) or True)
    monkeypatch.setattr(episodes.client_gate, 'note_client_seen', lambda *a: None)
    app = FastAPI()
    app.include_router(episodes.router)
    app.dependency_overrides[episodes.auth.get_current_user_uid] = lambda: 'u'
    assert TestClient(app).get('/v1/episodes/live', headers={'X-Omi-App-Channel': 'beta'}).status_code == 200
    assert calls == ['u']


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('992', 'pre_v3'),
        ('993', 'v3_capable'),
        ('1200', 'v3_capable'),
        ('', 'unknown'),
        ('1.0.599', 'unknown'),
        ('-1', 'unknown'),
    ],
)
def test_episode_build_bucket_uses_first_v3_build(monkeypatch, raw, expected):
    monkeypatch.setenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '993')  # synthetic boundary, not a release assertion
    assert switch.episode_build_bucket(raw) == expected


def test_episode_request_uses_build_header_not_marketing_version(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    meter = MagicMock()
    monkeypatch.setenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '993')
    monkeypatch.setattr(episodes.v3_metrics, 'EPISODE_CALLS', meter)
    request = SimpleNamespace(
        url=SimpleNamespace(path='/v1/episodes/live'),
        headers={'X-App-Version': '1.0.599', 'X-App-Build': '992'},
        scope={'route': SimpleNamespace(path='/v1/episodes/live')},
    )
    episodes._record_episode_request(request, 'u', 'store', False)
    meter.labels.assert_called_once_with('/v1/episodes/live', 'store', 'pre_v3', 'false')
    monkeypatch.delenv('CONVERSATIONS_V3_FIRST_APP_BUILD')
    assert switch.episode_build_bucket('992') == 'unknown'
