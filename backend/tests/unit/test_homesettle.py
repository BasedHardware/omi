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
        **updates
    )


def test_hold_floor_without_lane_with_long_capture_window():
    assert not conversations.is_visible_conversation(floor())


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
        finished_at=NOW - timedelta(hours=3),
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
        **updates
    )


def configure_membership(monkeypatch):
    monkeypatch.setattr(home_membership.client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setattr(home_membership, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(home_membership.episodes, 'get_episode', lambda uid, eid: episode() if eid == 'e' else None)
    monkeypatch.setattr(
        home_membership.home_read, 'project_episode', lambda uid, e, **kw: {'members': [{'id': 'a'}, {'id': 'b'}]}
    )


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


def test_list_projection_detects_legacy_echo_without_returning_transcripts(monkeypatch):
    from fake_firestore import FakeFirestoreClient

    store = FakeFirestoreClient()
    root = store.collection('users').document('u').collection('conversations')
    root.document('a').set({'transcript_segments': [{'text': 'Thank you.'}]})
    monkeypatch.setattr(conversations, 'db', store)
    raw = floor()
    before = deepcopy(raw)
    from database.conversation_home_titles import neutralize_legacy_list_titles

    neutralize_legacy_list_titles('u', [raw])
    assert raw['structured']['title'].startswith('Recording · ')
    assert 'transcript_segments' not in raw
    assert root.document('a').get().to_dict() == {'transcript_segments': [{'text': 'Thank you.'}]}
    assert before['structured']['title'] == 'Thank you.'


def test_membership_outages_and_merged_donors_keep_members_reachable(monkeypatch):
    configure_membership(monkeypatch)
    row = floor(episode_id='e')
    monkeypatch.setattr(home_membership.episodes, 'get_episode', lambda *_: episode(recorded_merged_into='successor'))
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]
    monkeypatch.setattr(home_membership.episodes, 'get_episode', Mock(side_effect=RuntimeError('offline')))
    assert home_membership.suppress_held_members('u', [row], 'e:a') == [row]


def test_conversation_route_preserves_page_cursor_and_unfetched_members(monkeypatch):
    from fastapi import Request, Response
    from routers import conversations as routes

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
    monkeypatch.setattr(home_read.episodes, 'get_episode', lambda *a, **kw: latest)
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
