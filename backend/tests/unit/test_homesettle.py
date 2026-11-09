"""Home settling regressions, hermetic: no customer data or provider calls."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from database import conversations
from utils.episodes import home_read, service

try:
    from utils.episodes import home_membership
except ImportError:  # Base-ref regression run predates this protocol.
    home_membership = None
from utils.llm.output_language import resolve_output_language

NOW = datetime.now(timezone.utc)


def floor(**updates):
    return dict(
        {
            'id': 'a',
            'status': 'completed',
            'started_at': NOW - timedelta(minutes=3),
            'finished_at': NOW - timedelta(minutes=1),
            'summary_blocked_reason': 'content_below_floor',
            'structured': {'title': 'Thank you.', 'overview': ''},
        },
        **updates,
    )


def test_hold_floor_without_lane_with_long_capture_window():
    assert not conversations.is_visible_conversation(floor())


def test_phase_shadow_preserves_permanent_floor_verdict_without_mutating_rows(monkeypatch):
    from utils.conversations import fragment_visibility, phase_shadow

    started = NOW - timedelta(hours=12)
    raw = floor(
        started_at=started,
        finished_at=started + timedelta(seconds=458),
        structured={'title': 'Yeah.', 'title_provenance': 'server_minimum'},
    )
    before = deepcopy(raw)
    observed = Mock()
    monkeypatch.setattr(phase_shadow, 'observe', observed)
    assert fragment_visibility.is_settling_fragment(raw, now=NOW.timestamp())
    observed.assert_called_once_with('settling_hold', raw, True, now=NOW.timestamp())
    observed.reset_mock()
    parent = episode(started_at=started, last_activity_at=raw['finished_at'])
    assert home_read.project_episode('u', parent, members={'a': raw}, list_row=True) is None
    observed.assert_called_once_with('episode_member', raw, False, episode=parent)
    assert raw == before


@pytest.mark.parametrize('status', ['pending', 'processing', 'in_progress'])
def test_unfinished_rows_never_settle_or_hide(monkeypatch, status):
    row = floor(status=status, episode_id='e')
    assert conversations.is_visible_conversation(row)
    configure_membership(monkeypatch)
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]


def test_hold_expires_and_respects_user_curation_and_switch(monkeypatch):
    assert conversations.is_visible_conversation(
        floor(
            summary_blocked_reason=None,
            structured={'title_provenance': 'server_minimum'},
            started_at=NOW - timedelta(hours=4),
            finished_at=NOW - timedelta(hours=3),
        )
    )
    assert conversations.is_visible_conversation(floor(user_title='My recording'))
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'off')
    assert conversations.is_visible_conversation(floor())


@pytest.mark.parametrize(
    'provenance,title',
    [('server_minimum', 'Thank you.'), (None, 'Thank you.'), (None, 'Thank you for the visit and the breakfast')],
)
def test_minimum_titles_are_neutral_on_conversation_and_episode_reads(provenance, title):
    raw = floor(
        summary_blocked_reason=None,
        started_at=NOW - timedelta(hours=4),
        finished_at=NOW - timedelta(hours=4) + timedelta(seconds=30),
        transcript_segments=[{'text': 'Thank you for the visit and the breakfast today. More words.'}],
    )
    if title == 'Thank you.':
        raw['transcript_segments'] = [{'text': 'Thank you.'}]
    raw['structured']['title'] = title
    if provenance:
        raw['structured']['title_provenance'] = provenance
    before = deepcopy(raw)
    projected = conversations.prepare_conversation_for_read(raw, 'u')
    assert projected['structured']['title'].startswith('Recording · ')
    wire = home_read.project_episode('u', episode(), members={'a': raw})
    assert wire['members'][0]['title'].startswith('Recording · ')
    assert raw == before


def test_curated_title_survives_minimum_projection():
    raw = floor(user_title='My breakfast', structured={'title': 'Thank you.', 'title_provenance': 'server_minimum'})
    assert conversations.prepare_conversation_for_read(raw, 'u')['structured']['title'] == 'My breakfast'


@pytest.mark.parametrize('as_objects', [False, True])
def test_wrong_capture_tag_cannot_choose_output_language(monkeypatch, as_objects):
    from database import users
    from utils.episodes.output_language import resolve_episode_language

    monkeypatch.setattr(users, 'get_user_language_preference', lambda uid: '')
    segments = [
        {'text': 'We should meet tomorrow to discuss the entire project and budget.', 'language': 'en'},
        {'text': 'いいね', 'language': 'ja'},
    ]
    if as_objects:
        from types import SimpleNamespace

        segments = [SimpleNamespace(**segment) for segment in segments]
    assert resolve_output_language('u', 'ja', segments) == 'en'
    assert resolve_episode_language('u', 'ja', preference='', segments=segments) == 'en'
    assert resolve_output_language('u', 'ja', [{'text': '日本語の長い会話です', 'language': 'ja'}]) == 'ja'
    monkeypatch.setattr(users, 'get_user_language_preference', lambda uid: 'ja')
    assert resolve_output_language('u', 'en', segments) == 'ja'


def episode(**updates):
    return dict(
        {
            'id': 'e',
            'status': 'closed',
            'started_at': NOW - timedelta(hours=3),
            'last_activity_at': NOW - timedelta(hours=2),
            'conversation_ids': ['a', 'b'],
        },
        **updates,
    )


def configure_membership(monkeypatch):
    monkeypatch.setattr(home_membership.client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setattr(home_membership, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(
        home_membership.episodes, 'get_home_episode_snapshots', lambda uid, ids: {'e': episode()} if 'e' in ids else {}
    )
    monkeypatch.setattr(home_read, 'project_episode', lambda uid, e, **kw: {'members': [{'id': 'a'}, {'id': 'b'}]})


def test_membership_hides_only_exact_members_with_held_extant_replacement(monkeypatch):
    configure_membership(monkeypatch)
    rows = [
        floor(episode_id='e'),
        floor(id='b', episode_id='e'),
        floor(id='old', episode_id='older'),
        floor(id='orphan', episode_id='missing'),
    ]
    result = home_membership.suppress_held_members('u', rows, 'e:a,missing:orphan')
    assert [r['id'] for r in result] == ['b', 'old', 'orphan']
    # Any range/page whose episodes have not landed keeps all members visible.
    assert home_membership.suppress_held_members('u', rows, '') == rows
    # All omitted members have the exact client-held replacement, even if the
    # server episode has gained a new member since that snapshot was read.
    assert {r['id'] for r in rows} - {r['id'] for r in result} == {'a'}


def test_membership_kill_switch_off_and_capability_fail_open(monkeypatch):
    configure_membership(monkeypatch)
    row = floor(episode_id='e')
    monkeypatch.setenv('HOME_HIDE_EPISODE_MEMBERS', 'off')
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]
    monkeypatch.delenv('HOME_HIDE_EPISODE_MEMBERS')
    monkeypatch.setattr(home_membership.client_gate, 'client_seen', lambda uid: False)
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]


def test_floor_member_with_long_window_is_not_a_standalone_home_row(monkeypatch):
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'on')
    assert home_read._too_short_for_a_home_row(
        floor(started_at=NOW - timedelta(hours=4), finished_at=NOW - timedelta(hours=3))
    )


def test_list_titles_use_only_loaded_fields_and_never_refetch_transcripts(monkeypatch):
    from tests.unit.test_indexed_list_read_path import Db

    raw = floor(
        created_at=NOW,
        updated_at=NOW,
        memory_id='a',
        discarded=False,
        summary_blocked_reason=None,
        started_at=NOW - timedelta(hours=4),
        finished_at=NOW - timedelta(hours=4) + timedelta(seconds=30),
    )
    store = Db([raw])
    transcript_refetch = Mock(return_value=[])
    monkeypatch.setattr(store, 'get_all', transcript_refetch, raising=False)
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    rows = conversations.get_conversations_without_photos('u', list_fields_only=True)
    assert rows[0]['structured']['title'] == 'Thank you.'  # Unknown provenance needs absent speech: leave it alone.
    assert 'transcript_segments' not in rows[0]
    transcript_refetch.assert_not_called()
    assert raw['structured']['title'] == 'Thank you.'


def test_membership_outages_and_merged_donors_keep_members_reachable(monkeypatch):
    configure_membership(monkeypatch)
    row = floor(episode_id='e')
    monkeypatch.setattr(
        home_membership.episodes,
        'get_home_episode_snapshots',
        lambda *_: {'e': episode(recorded_merged_into='successor')},
    )
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]
    monkeypatch.setattr(
        home_membership.episodes, 'get_home_episode_snapshots', Mock(side_effect=RuntimeError('offline'))
    )
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]


@pytest.fixture
def conversation_routes():
    from routers import conversations as routes

    return routes


def test_conversation_route_preserves_page_cursor_and_unfetched_members(monkeypatch, conversation_routes):
    from fastapi import Request, Response

    routes = conversation_routes

    configure_membership(monkeypatch)
    rows = [floor(episode_id='e'), floor(id='old', episode_id='unfetched')]
    calls = []
    monkeypatch.setattr(
        routes.conversations_db,
        'get_conversations_without_photos',
        lambda uid, limit, offset, **kwargs: (calls.append(offset), deepcopy(rows))[1],
    )
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *args: None)
    monkeypatch.setattr(routes, 'redact_conversations_for_list', lambda *args: None)
    request = Request(
        {
            'type': 'http',
            'path': '/v1/conversations',
            'method': 'GET',
            'query_string': b'',
            'headers': [(b'x-omi-home-episode-ids', b'e:a')],
        }
    )
    response = Response()
    result = routes.get_conversations(
        request=request,
        response=response,
        uid='u',
        offset=100,
        sources=None,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
    )
    assert [row['id'] for row in result] == ['old']
    assert response.headers['X-Omi-Conversation-Page-Size'] == '2'
    assert response.headers['X-Omi-Home-Suppressed-Ids'] == 'a'
    assert calls == [100]


def test_explicit_model_title_provenance_is_respected():
    raw = floor(
        structured={'title': 'Thank you.', 'title_provenance': 'llm'}, transcript_segments=[{'text': 'Thank you.'}]
    )
    assert conversations.prepare_conversation_for_read(raw, 'u')['structured']['title'] == 'Thank you.'


def test_indexed_home_list_loads_floor_reason_before_filtering(monkeypatch):
    from tests.unit.test_indexed_list_read_path import Db

    row = floor(created_at=NOW, updated_at=NOW, memory_id='a', discarded=False)
    monkeypatch.setattr(conversations, 'db', Db([row]))
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    assert conversations.get_conversations_without_photos('u', list_fields_only=True) == []


def test_settled_below_floor_never_expires_but_remains_search_reachable(monkeypatch):
    row = floor(
        started_at=NOW - timedelta(hours=12, seconds=458),
        finished_at=NOW - timedelta(hours=12),
        structured={'title': 'Yeah.', 'overview': 'Old provisional notes'},
    )
    assert not conversations.is_visible_conversation(row)
    assert home_read._too_short_for_a_home_row(row)
    # Search/detail callers explicitly retain non-discarded short clips.
    assert conversations.is_visible_conversation(row, include_discarded=True)
    assert not row.get('discarded')
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'off')
    assert conversations.is_visible_conversation(row)
    assert not home_read._too_short_for_a_home_row(row)


def test_list_projection_retains_pagination_and_filtered_reachability(monkeypatch):
    from types import SimpleNamespace

    configure_membership(monkeypatch)
    request = SimpleNamespace(headers={home_membership.HELD_EPISODES_HEADER: 'e:a'})
    response = SimpleNamespace(headers={})
    rows = [floor(episode_id='e'), floor(id='older', episode_id='unfetched')]
    assert home_membership.project_list('u', rows, request, response, filtered=False) == rows[1:]
    assert response.headers[home_membership.PAGE_SIZE_HEADER] == '2'
    assert response.headers[home_membership.SUPPRESSED_HEADER] == 'a'
    response.headers.clear()
    assert home_membership.project_list('u', rows, request, response, filtered=True) == rows
    assert response.headers == {}


@pytest.mark.parametrize('latest_status', ['closed', 'live'])
def test_idle_list_read_uses_the_winner_of_a_concurrent_close_or_activity_update(monkeypatch, latest_status):
    stale = episode(status='live', last_activity_at=NOW - timedelta(hours=3))
    latest = dict(stale, status=latest_status, last_activity_at=NOW)
    close = Mock(return_value=False)
    monkeypatch.setattr(service, '_close', close)
    monkeypatch.setattr(home_read.episodes, 'get_home_episode_snapshots', lambda *a, **kw: {'e': latest})
    monkeypatch.setattr(
        home_read,
        '_read_members',
        lambda *a, **kw: {'a': floor(summary_blocked_reason=None), 'b': floor(summary_blocked_reason=None)},
    )
    checked = []
    monkeypatch.setattr(home_read, 'schedule_missed_composes', lambda uid, rows, wires: checked.extend(rows))
    wires = home_read.project_episodes('u', [stale])
    assert wires[0]['status'] == latest_status
    assert wires[0]['last_activity_at'] == NOW
    close.assert_called_once()
    # A parallel closer already scheduled compose; the list must not schedule it again.
    assert checked == ([] if latest_status == 'closed' else [latest])


@pytest.mark.parametrize('not_modified', [False, True])
def test_member_kill_switch_restores_version_and_cache_with_header(monkeypatch, conversation_routes, not_modified):
    from fastapi import Request, Response
    from types import SimpleNamespace

    routes = conversation_routes
    # All independent time-dependent Home projections must be off for writer-version caching.
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', 'off')
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'off')
    monkeypatch.setenv('HOME_HIDE_EPISODE_MEMBERS', 'off')
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'false')
    request = Request(
        {
            'type': 'http',
            'headers': [
                (b'x-omi-home-episode-ids', b'e:a'),
                (b'x-omi-home-ownership', b'1'),
                (b'x-omi-app-channel', b'beta'),
            ],
            'query_string': b'',
        }
    )
    cached = Response(status_code=304) if not_modified else None
    finish = Mock()
    start = Mock(return_value=SimpleNamespace(not_modified=cached, finish=finish))
    monkeypatch.setattr(routes.ListVersionCheck, 'start', start)
    fetch = Mock(return_value=[floor(summary_blocked_reason=None)])
    monkeypatch.setattr(routes.conversations_db, 'get_conversations_without_photos', fetch)
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    monkeypatch.setattr(routes, 'redact_conversations_for_list', lambda *a: None)
    response = Response()
    result = routes.get_conversations(
        request=request,
        response=response,
        uid='u',
        sources=None,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
    )
    start.assert_called_once_with(request, 'u', 'conversations')
    if not_modified:
        assert result is cached
        fetch.assert_not_called()
    else:
        assert finish.call_args.kwargs['cacheable'] is True
        assert home_membership.PAGE_SIZE_HEADER not in response.headers


@pytest.mark.parametrize('value', ['off', '0', 'false', 'no'])
def test_neutral_title_kill_switch_covers_all_home_projections(monkeypatch, value):
    monkeypatch.setenv('HOME_NEUTRAL_MINIMUM_TITLES', value)
    for provenance in [None, 'server_minimum']:
        raw = floor(
            summary_blocked_reason=None,
            finished_at=NOW - timedelta(hours=3),
            transcript_segments=[{'text': 'Thank you.'}],
            structured={'title': 'Thank you.', 'title_provenance': provenance},
        )
        assert conversations.prepare_conversation_for_read(raw, 'u')['structured']['title'] == 'Thank you.'
        wire = home_read.project_episode('u', episode(), members={'a': raw})
        assert wire['members'][0]['title'] == 'Thank you.'


@pytest.mark.parametrize('pin', ['on', 'off'])
def test_capture_language_without_segments_retains_valid_capture(monkeypatch, pin):
    from database import users
    from utils.episodes.output_language import resolve_episode_language

    monkeypatch.setenv('EPISODE_OUTPUT_LANGUAGE_PIN', pin)
    monkeypatch.setattr(users, 'get_user_language_preference', lambda uid: '')
    assert resolve_output_language('u', 'ja') == 'ja'
    assert resolve_episode_language('u', 'ja', preference='') == 'ja'
    segments = [{'text': 'The whole transcript is a discussion about the project budget.', 'language': 'en'}]
    assert resolve_output_language('u', 'ja', segments) == ('ja' if pin == 'off' else 'en')
    assert resolve_episode_language('u', 'ja', preference='', segments=segments) == ('ja' if pin == 'off' else 'en')


def test_member_validation_has_fixed_read_budget_and_excess_members_stay_visible(monkeypatch):
    from fake_firestore import FakeFirestoreClient

    monkeypatch.setattr(home_membership.client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setattr(home_membership, 'episodes_enabled_for', lambda uid: True)
    store = FakeFirestoreClient()
    rows = [floor(id=f'c{i}', episode_id=f'e{i}') for i in range(50)]
    for row in rows:
        store.collection('users').document('u').collection('episodes').document(row['episode_id']).set(
            episode(id=row['episode_id'], conversation_ids=[row['id']])
        )
    monkeypatch.setattr(home_membership.episodes, '_client', lambda _: store)
    old_read = Mock(side_effect=lambda uid, eid: episode(id=eid, conversation_ids=[f'c{eid[1:]}']))
    monkeypatch.setattr(home_membership.episodes, 'get_episode', old_read)
    monkeypatch.setattr(
        home_read, 'project_episode', lambda uid, e, **kw: {'members': [{'id': cid} for cid in e['conversation_ids']]}
    )
    batch = Mock(wraps=store.get_all)
    monkeypatch.setattr(store, 'get_all', batch)
    result = home_membership.suppress_held_members(
        'u', rows, ','.join(f"{row['episode_id']}:{row['id']}" for row in rows)
    )
    old_read.assert_not_called()
    assert batch.call_count == 1
    assert len(batch.call_args.args[0]) == 5
    hidden = {r['id'] for r in rows} - {r['id'] for r in result}
    assert len(hidden) == 5
    assert len(result) == 45


def test_idle_close_winner_reuses_returned_doc_without_reread(monkeypatch):
    stale = episode(status='live')
    closed = dict(stale, status='closed')
    monkeypatch.setattr(service, '_close', Mock(return_value=closed))
    reread = Mock(side_effect=AssertionError('winner must reuse the close result'))
    monkeypatch.setattr(service.episodes_db, 'get_episode', reread)
    assert service.settle_episode_for_read('u', stale, service.Collaborators()) is closed
    reread.assert_not_called()


def test_episode_page_limits_idle_close_work_without_hiding_unsettled_members(monkeypatch):
    rows = [episode(id=f'e{i}', status='live', conversation_ids=[f'c{i}']) for i in range(50)]
    settle = Mock(side_effect=lambda uid, row, c: dict(row, status='closed'))
    monkeypatch.setattr(service, 'settle_episode_for_read', settle)
    monkeypatch.setattr(home_read, '_read_members', lambda *a, **kw: {})
    monkeypatch.setattr(
        home_read,
        'project_episode',
        lambda uid, row, **kw: {
            'id': row['id'],
            'status': row['status'],
            'members': [{'id': row['conversation_ids'][0]}],
        },
    )
    monkeypatch.setattr(home_read, 'schedule_missed_composes', lambda *a: 0)
    wires = home_read.project_episodes('u', rows)
    assert settle.call_count == 2
    assert len(wires) == 50
    assert sum(w['status'] == 'live' for w in wires) == 48


@pytest.mark.parametrize('provenance', [None, 'server_minimum'])
def test_dead_letter_and_non_floor_normal_titles_remain_authoritative(provenance):
    raw = floor(
        summary_blocked_reason=None,
        finalization_status='dead_letter',
        transcript_segments=[{'text': 'Call the landlord.'}],
        structured={'title': 'Call the landlord.', 'title_provenance': provenance},
    )
    assert conversations.prepare_conversation_for_read(raw, 'u')['structured']['title'] == 'Call the landlord.'
    assert home_read.project_episode('u', episode(), members={'a': raw})['members'][0]['title'] == 'Call the landlord.'
    raw.pop('finalization_status')
    assert conversations.prepare_conversation_for_read(raw, 'u')['structured']['title'] == 'Call the landlord.'


def test_loaded_eight_word_lazy_placeholder_is_neutral_without_floor_metadata():
    raw = floor(
        summary_blocked_reason=None,
        transcript_segments=[{'text': 'Please call the landlord about the leaking pipe this afternoon.'}],
        structured={'title': 'Please call the landlord about the leaking pipe'},
    )
    assert conversations.prepare_conversation_for_read(raw, 'u')['structured']['title'].startswith('Recording · ')


@pytest.mark.parametrize('bound', ['start_date', 'end_date'])
def test_date_filtered_members_stay_reachable_even_with_a_held_header(monkeypatch, bound):
    from types import SimpleNamespace

    configure_membership(monkeypatch)
    request = SimpleNamespace(
        headers={home_membership.HELD_EPISODES_HEADER: 'e:a'}, query_params={bound: NOW.isoformat()}
    )
    response = SimpleNamespace(headers={})
    rows = [floor(episode_id='e')]
    assert home_membership.held_for(request) == ''  # Also restores ordinary cache/version decisions.
    assert home_membership.project_list('u', rows, request, response, filtered=False) == rows
    assert response.headers == {}


@pytest.mark.parametrize(
    'deadline_hours, status, title',
    [(1, 'processing', 'Transcribing…'), (-1, 'failed', "Couldn't transcribe")],
)
def test_batch_placeholders_coexist_with_neutral_titles_and_floor_holding(deadline_hours, status, title):
    neutral = floor(
        summary_blocked_reason=None,
        started_at=NOW - timedelta(hours=4),
        finished_at=NOW - timedelta(hours=4) + timedelta(seconds=30),
        structured={'title': 'Thank you.', 'title_provenance': 'server_minimum'},
    )
    pending = dict(neutral, id='pending', episode_transcription_deadline_at=NOW + timedelta(hours=deadline_hours))
    members = {
        'a': neutral,
        'pending': pending,
        'floor': floor(id='floor', episode_transcription_deadline_at=NOW - timedelta(hours=1)),
    }
    before = deepcopy(members)
    wire = home_read.project_episode(
        'u',
        episode(conversation_ids=list(members)),
        members=members,
        list_row=True,
    )
    by_id = {member['id']: member for member in wire['members']}
    assert by_id['a']['title'].startswith('Recording · ')
    assert (by_id['pending']['title'], by_id['pending']['status']) == (title, status)
    assert 'floor' not in by_id
    assert members == before


@pytest.mark.parametrize(
    'channel,bound,hidden',
    [
        (None, None, False),
        ('store', None, False),
        ('beta', 'start_date', False),
        ('beta', 'end_date', False),
        ('beta', None, True),
    ],
)
def test_live_home_suppression_requires_this_clients_unfiltered_capability(monkeypatch, channel, bound, hidden):
    from types import SimpleNamespace

    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    read = Mock(return_value={'id': 'e', 'conversation_ids': ['a']})
    monkeypatch.setattr(home_membership, 'live_owner', read)
    headers = {
        'X-Omi-Home-Ownership': '1',
        home_membership.HELD_EPISODES_HEADER: 'e:a',
        **({'X-Omi-App-Channel': channel} if channel else {}),
    }
    request = SimpleNamespace(headers=headers, query_params={bound: NOW.isoformat()} if bound else {})
    response = SimpleNamespace(headers={})
    rows = [floor(id='a', episode_id='e')]
    assert home_membership.project_list('u', rows, request, response, filtered=False) == ([] if hidden else rows)
    assert read.call_count == int(hidden)
    assert response.headers.get(home_membership.SUPPRESSED_HEADER, '') == ('a' if hidden else '')
    assert home_membership.live_suppression_for('u', request) == hidden  # Version cache must be bypassed when dynamic.


def test_old_beta_client_does_not_opt_into_live_home_suppression(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    request = SimpleNamespace(headers={'X-Omi-App-Channel': 'beta'}, query_params={})
    assert not home_membership.live_suppression_for('u', request)


@pytest.mark.parametrize('echo', ['', 'other:a', 'e:a', 'malformed'])
@pytest.mark.parametrize('held_switch', ['on', 'off'])
def test_live_snapshot_failure_or_disagreement_keeps_recordings_visible(monkeypatch, echo, held_switch):
    from types import SimpleNamespace

    configure_membership(monkeypatch)
    monkeypatch.setenv('HOME_HIDE_EPISODE_MEMBERS', held_switch)
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    monkeypatch.setattr(home_membership, 'live_owner', lambda uid: episode(status='live'))
    monkeypatch.setattr(home_membership.episodes, 'get_home_episode_snapshots', lambda *a: {})
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: echo,
        },
        query_params={},
    )
    rows = [floor(episode_id='e'), floor(id='outside', episode_id='closed')]
    # Snapshot-fetch failure sends no echo; stale or missing echoes fail visible.
    assert home_membership.project_list('u', rows, request, None, filtered=False) == (
        rows[1:] if echo == 'e:a' else rows
    )


@pytest.mark.parametrize('linked', [False, True])
def test_stale_live_snapshot_keeps_unacknowledged_new_member_visible(monkeypatch, linked):
    from types import SimpleNamespace

    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    owner = episode(status='live', conversation_ids=['a', 'b'] if linked else ['a'])
    monkeypatch.setattr(home_membership, 'live_owner', lambda uid: owner)
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: 'e:a',
        },
        query_params={},
    )
    # b is either newly attached or only overlaps the server's live window.
    rows = [
        floor(episode_id='e'),
        floor(
            id='b',
            episode_id='e' if linked else None,
            started_at=owner['started_at'] + timedelta(minutes=1),
            finished_at=owner['started_at'] + timedelta(minutes=2),
        ),
    ]
    response = SimpleNamespace(headers={})
    assert home_membership.project_list('u', rows, request, response, filtered=False) == rows[1:]
    assert response.headers[home_membership.SUPPRESSED_HEADER] == 'a'
    assert response.headers[home_membership.PAGE_SIZE_HEADER] == '2'
