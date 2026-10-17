"""Call-link regression cases; generated metadata and synthetic text only."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from config.desktop_pendant_call_link import call_link_mode, call_pair, capture_windows
from database import capture_groups as groups
from database import conversations as conversations
from models.conversation import Conversation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import duplicate_capture
from utils.conversations.desktop_pendant_call_link import select_pairs

T0 = datetime(2026, 10, 16, tzinfo=timezone.utc)
UID = 'synthetic-call-owner'


def row(cid, source, start=0, end=100, **kwargs):
    return dict(
        id=cid,
        source=source,
        status='completed',
        discarded=False,
        created_at=T0,
        started_at=T0 + timedelta(seconds=start),
        finished_at=T0 + timedelta(seconds=end),
        structured={},
        transcript_segments=[],
        external_data={'conversation_role': 'meeting' if source == 'desktop' else 'ambient'},
        **kwargs,
    )


def path(cid, uid=UID):
    return ('users', uid, 'conversations', cid)


@pytest.fixture
def store(monkeypatch):
    fake = StrictFirestore()
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_MODE', 'on')
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_PERCENT', '100')
    fake.degraded = MagicMock()
    monkeypatch.setattr(duplicate_capture, '_record_degraded', fake.degraded)
    monkeypatch.setattr(groups, 'get_firestore_client', lambda: fake)
    monkeypatch.setattr(conversations, 'get_firestore_client', lambda: fake)
    monkeypatch.setattr(
        conversations, 'get_conversation', lambda uid, cid, **kw: deepcopy(fake.rows.get(path(cid, uid)))
    )
    monkeypatch.setattr(
        conversations,
        'get_conversations_finished_after',
        lambda uid, **kw: [
            deepcopy(value)
            for key, value in fake.rows.items()
            if key[:2] == ('users', uid)
            and value['status'] == kw['status']
            and value['finished_at'] >= kw['finished_after']
        ][: kw['limit']],
    )
    return fake


@pytest.mark.parametrize('duration', [30, 44, 59, 101, 1600])
@pytest.mark.parametrize('arrival', ['desktop', 'pendant'])
def test_short_and_complementary_pairs_both_arrival_orders(store, duration, arrival):
    desktop = row('desktop', 'desktop', 0, duration)
    pendant = row('pendant', 'omi', -1, duration + 10)
    # No shared speech is available, including for the long complementary case.
    earlier = 'pendant' if arrival == 'desktop' else 'desktop'
    records = {'desktop': desktop, 'pendant': pendant}
    store.rows[path(earlier)] = records[earlier]
    duplicate_capture.link_duplicate_captures(UID, Conversation(**records[earlier]))
    assert not store.rows[path(earlier)].get('capture_group')
    store.rows[path(arrival)] = records[arrival]
    duplicate_capture.link_duplicate_captures(UID, Conversation(**records[arrival]))
    assert store.degraded.call_count == 0
    group = store.rows[path('desktop')]['capture_group']
    assert group['primary_id'] == 'desktop'
    assert group['kind'] == 'desktop_pendant_call'
    assert group == store.rows[path('pendant')]['capture_group']
    assert {m['id'] for m in group['members']} == {'desktop', 'pendant'}
    assert all(not r.get('deleted') and not r.get('discarded') for r in store.rows.values())
    assert all(not r['external_data'].get('duplicate_capture_of') for r in store.rows.values())


@pytest.mark.parametrize('raw', ['', 'off', 'shadow', 'on', 'typo'])
def test_modes_and_content_free_shadow(store, monkeypatch, caplog, raw):
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_MODE', raw)
    store.rows.update({path('desktop'): row('desktop', 'desktop', end=44), path('pendant'): row('pendant', 'omi')})
    before = deepcopy(store.rows)
    with caplog.at_level('INFO'):
        duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    if raw == 'on':
        assert store.rows[path('desktop')]['capture_group']['primary_id'] == 'desktop'
    else:
        assert store.rows == before
    logs = [r.getMessage() for r in caplog.records if 'event=desktop_pendant_call_link' in r.getMessage()]
    if raw in {'on', 'shadow'}:
        assert len(logs) == 1
        fields = {part.split('=')[0] for part in logs[0].split()}
        assert fields == {'event', 'role', 'overlap_seconds', 'overlap_ratio', 'candidate_count', 'decision', 'reason'}
    else:
        assert not logs


def test_unset_unknown_and_stable_cohort(monkeypatch):
    monkeypatch.delenv('DESKTOP_PENDANT_CALL_LINK_MODE', raising=False)
    assert call_link_mode(UID) == 'off'
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_MODE', 'on')
    for percent in ('0', '-1', 'nan', 'typo', '101'):
        monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_PERCENT', percent)
        assert call_link_mode(UID) == 'off'
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_PERCENT', '5')
    first = [call_link_mode(f'user-{i}') for i in range(1000)]
    assert first == [call_link_mode(f'user-{i}') for i in range(1000)]
    assert 20 < first.count('on') < 80
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_MODE', 'shadow')
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_PERCENT', '0')
    assert call_link_mode(UID) == 'shadow'


@pytest.mark.parametrize('start,end,accepted', [(0, 29.9, False), (0, 30, True), (50, 150, True), (50.1, 150.1, False)])
def test_inclusive_floors(start, end, accepted):
    assert bool(call_pair(row('d', 'desktop'), row('p', 'omi', start, end))) is accepted


@pytest.mark.parametrize('change', ['ambient', 'processing', 'deleted', 'discarded', 'closed', 'same_source'])
def test_eligibility(change):
    desktop, pendant = row('d', 'desktop'), row('p', 'omi')
    if change == 'ambient':
        desktop['external_data']['conversation_role'] = 'ambient'
    elif change == 'processing':
        desktop['status'] = 'processing'
    elif change == 'closed':
        desktop['capture_group_closed'] = True
    elif change == 'same_source':
        pendant['source'] = 'desktop'
    else:
        desktop[change] = True
    assert call_pair(desktop, pendant) is None


def test_owner_scoped_candidates(store):
    store.rows[path('desktop')] = row('desktop', 'desktop')
    store.rows[path('pendant', 'another-owner')] = row('pendant', 'omi')
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert not store.rows[path('desktop')].get('capture_group')


def test_ambiguity_order_is_stable_one_to_one():
    rows = [row('d2', 'desktop'), row('d1', 'desktop'), row('p2', 'omi'), row('p1', 'omi')]
    assert select_pairs(rows) == select_pairs(list(reversed(rows)))
    assert [pair[:2] for pair in select_pairs(rows)] == [('d1', 'p1'), ('d2', 'p2')]


def test_unlink_and_existing_group_prevent_relink_or_transitive_bridges(store):
    for cid, source in [('desktop', 'desktop'), ('pendant', 'omi')]:
        store.rows[path(cid)] = row(cid, source)
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('pendant')]))
    assert store.rows[path('desktop')]['capture_group']['primary_id'] == 'desktop'
    store.rows[path('other')] = row('other', 'omi')
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('other')]))
    assert not store.rows[path('other')].get('capture_group')
    assert groups.leave_capture_group(UID, 'pendant', sticky=True)
    # Exclude unrelated candidates to verify durable separation of this pair.
    del store.rows[path('other')]
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert not store.rows[path('pendant')].get('capture_group')


@pytest.mark.parametrize('change', ['role', 'window', 'unlink', 'group'])
def test_transaction_fences_stale_matching(store, monkeypatch, change):
    for cid, source in [('desktop', 'desktop'), ('pendant', 'omi')]:
        store.rows[path(cid)] = row(cid, source)
    original = groups.join_capture_group

    def race(*args, **kwargs):
        if change == 'role':
            store.rows[path('desktop')]['external_data']['conversation_role'] = 'ambient'
        elif change == 'window':
            store.rows[path('desktop')]['finished_at'] += timedelta(seconds=1)
        elif change == 'unlink':
            store.rows[path('pendant')]['capture_group_exclusions'] = ['desktop']
        else:
            store.rows[path('third')] = row('third', 'omi')
            original(UID, 'desktop', 'third', {'method': 'shared_speech'})
        return original(*args, **kwargs)

    monkeypatch.setattr(groups, 'join_capture_group', race)
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('pendant')]))
    assert not store.rows[path('pendant')].get('capture_group')


def test_existing_pair_promotes_desktop_primary_and_stays_sticky(store):
    store.rows[path('desktop')] = row('desktop', 'desktop', end=44)
    store.rows[path('pendant')] = row('pendant', 'omi')
    gid = groups.join_capture_group(UID, 'desktop', 'pendant', {'method': 'shared_speech'})
    assert store.rows[path('desktop')]['capture_group']['primary_id'] == 'pendant'
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    group = store.rows[path('desktop')]['capture_group']
    assert group['primary_id'] == 'desktop' and group['id'] == gid
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('pendant')]))
    assert store.rows[path('desktop')]['capture_group']['revision'] == group['revision']


def test_page_saturation_keeps_pair_separate(store, monkeypatch):
    store.rows[path('desktop')] = row('desktop', 'desktop', end=44)
    store.rows[path('pendant')] = row('pendant', 'omi')
    monkeypatch.setattr(duplicate_capture, 'CANDIDATE_PAGE_LIMIT', 2)
    duplicate_capture.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert not store.rows[path('desktop')].get('capture_group')


def test_on_mode_preserves_ordinary_nonmeeting_cross_source_hints(store):
    desktop = row('desktop', 'desktop', end=120)
    desktop['external_data']['conversation_role'] = 'ambient'
    store.rows[path('desktop')] = desktop
    store.rows[path('phone')] = row('phone', 'phone')
    duplicate_capture.link_duplicate_captures(UID, Conversation(**desktop))
    assert store.degraded.call_count == 0
    assert store.rows[path('phone')]['external_data']['duplicate_capture_of'] == 'desktop'
    assert not store.rows[path('desktop')].get('capture_group')


def test_transaction_window_map_rejects_invalid_windows():
    assert capture_windows(row('p', 'omi', 10, 0)) is None
    assert capture_windows(dict(row('p', 'omi'), started_at=None)) is None
    assert capture_windows(row('', 'omi')) is None
