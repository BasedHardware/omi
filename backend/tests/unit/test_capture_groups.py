"""Capture groups (#3244): shared-speech confirmation, membership transactions, and their seams.

Synthetic transcripts only. Transactions run through StrictFirestore so reads
after the first write fail exactly as they would in production.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database import capture_groups as groups_db
from database import conversations as conversations_db
from models.conversation import Conversation
from routers import conversations as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from utils.conversations import duplicate_capture as policy
from utils.conversations import shared_speech

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = 'synthetic-group-user'

MEETING = (
    'we should ship the pendant firmware before the trade show and then fix the battery drain '
    'on the charging case because customers keep reporting that it dies overnight in the drawer '
    'also the factory wants a deposit by friday so finance needs the purchase order today'
)
OTHER = (
    'the recipe needs two cups of flour a pinch of salt and butter at room temperature then '
    'bake it for forty minutes until the crust turns golden and let it rest before slicing it '
    'into eight pieces for the neighbours who are coming over for dinner this weekend'
)


def segments(text):
    return [{'text': text, 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 0.0, 'end': 60.0}]


def row(id, source, start=0, end=600, text=MEETING, **extra):
    return {
        'id': id,
        'source': source,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=start),
        'finished_at': T0 + timedelta(seconds=end),
        'created_at': T0,
        'structured': {},
        'transcript_segments': segments(text),
        'external_data': {},
        **extra,
    }


def path(id, uid=UID):
    return ('users', uid, 'conversations', id)


@pytest.fixture
def store(monkeypatch):
    for name in (
        'CROSS_DEVICE_GROUP_MIN_WORDS',
        'CROSS_DEVICE_GROUP_MIN_SHARED_TRIGRAMS',
        'CROSS_DEVICE_GROUP_MIN_CONTAINMENT',
        'CROSS_DEVICE_DEDUP_MIN_OVERLAP_SECONDS',
        'CROSS_DEVICE_DEDUP_MIN_OVERLAP_RATIO',
    ):
        monkeypatch.delenv(name, raising=False)
    fake = StrictFirestore()
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: fake)
    return fake


def evidence():
    return shared_speech.measure_shared_speech(segments(MEETING), segments(MEETING)).evidence()


# --------------------------------------------------------------- shared speech


def test_same_speech_confirms_and_evidence_is_numeric_only():
    shared = shared_speech.measure_shared_speech(segments(MEETING), segments('hello there ' + MEETING))
    assert shared.confirms()
    assert shared.containment == 1.0
    record = shared.evidence()
    assert set(record) == {'method', 'containment', 'shared_trigrams', 'min_words'}
    assert all(not isinstance(value, str) or value == 'shared_speech' for value in record.values())


def test_unrelated_speech_does_not_confirm():
    assert not shared_speech.measure_shared_speech(segments(MEETING), segments(OTHER)).confirms()


def test_short_or_empty_transcripts_never_confirm():
    short = ' '.join(MEETING.split()[:20])
    assert not shared_speech.measure_shared_speech(segments(short), segments(short)).confirms()
    assert not shared_speech.measure_shared_speech([], segments(MEETING)).confirms()
    assert not shared_speech.measure_shared_speech(None, None).confirms()


def test_containment_is_measured_against_the_smaller_capture():
    # The desktop also heard remote participants the pendant did not: the part
    # both heard still confirms.
    shared = shared_speech.measure_shared_speech(segments(MEETING), segments(MEETING + ' ' + OTHER))
    assert shared.confirms()
    assert shared.containment == 1.0


def test_thresholds_are_configurable_and_validated(monkeypatch):
    monkeypatch.setenv('CROSS_DEVICE_GROUP_MIN_CONTAINMENT', '1.0')
    partial = ' '.join(MEETING.split()[:25]) + ' ' + OTHER
    assert not shared_speech.measure_shared_speech(segments(MEETING), segments(partial)).confirms()
    monkeypatch.setenv('CROSS_DEVICE_GROUP_MIN_CONTAINMENT', 'nan')
    with pytest.raises(ValueError):
        shared_speech.measure_shared_speech(segments(MEETING), segments(MEETING)).confirms()


def test_model_segments_are_accepted():
    conversation = Conversation(**row('m', 'omi'))
    assert shared_speech.measure_shared_speech(conversation.transcript_segments, segments(MEETING)).confirms()


# --------------------------------------------------------------- transactions


def test_pair_founds_a_group_with_independent_id_and_longest_primary(store):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    group_id = groups_db.join_capture_group(UID, 'desktop', 'pendant', evidence())
    assert group_id and group_id not in {'pendant', 'desktop'}
    records = [store.rows[path(cid)]['capture_group'] for cid in ('pendant', 'desktop')]
    assert records[0] == records[1]
    record = records[0]
    assert record['id'] == group_id and record['primary_id'] == 'pendant' and record['revision'] == 1
    assert [m['id'] for m in record['members']] == ['pendant', 'desktop']
    assert record['members'][1]['evidence']['matched_conversation_id'] == 'pendant'
    # Idempotent.
    assert groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence()) == group_id
    assert store.rows[path('pendant')]['capture_group']['revision'] == 1


def test_third_capture_joins_through_a_member_and_primary_moves_without_new_id(store):
    store.rows.update(
        {
            path('desktop'): row('desktop', 'desktop', 0, 600),
            path('frag1'): row('frag1', 'omi', 0, 300),
            path('frag2'): row('frag2', 'omi', 300, 1800),
        }
    )
    group_id = groups_db.join_capture_group(UID, 'frag1', 'desktop', evidence())
    assert groups_db.join_capture_group(UID, 'frag2', 'desktop', evidence()) == group_id
    records = {cid: store.rows[path(cid)]['capture_group'] for cid in ('desktop', 'frag1', 'frag2')}
    assert len({r['revision'] for r in records.values()}) == 1
    record = records['desktop']
    assert record['id'] == group_id and record['revision'] == 2
    assert record['primary_id'] == 'frag2'
    assert {m['id'] for m in record['members']} == {'desktop', 'frag1', 'frag2'}


def test_captures_in_different_groups_are_not_bridged(store):
    for cid, src in (('a', 'omi'), ('b', 'desktop'), ('c', 'omi'), ('d', 'desktop')):
        store.rows[path(cid)] = row(cid, src)
    first = groups_db.join_capture_group(UID, 'a', 'b', evidence())
    second = groups_db.join_capture_group(UID, 'c', 'd', evidence())
    before = deepcopy(store.rows)
    assert groups_db.join_capture_group(UID, 'a', 'd', evidence()) is None
    assert store.rows == before and first != second


@pytest.mark.parametrize('change', ['discarded', 'processing', 'deleted', 'missing', 'window'])
def test_ineligible_or_changed_captures_are_fenced(store, change):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    target = store.rows[path('desktop')]
    if change == 'discarded':
        target['discarded'] = True
    elif change == 'processing':
        target['status'] = 'processing'
    elif change == 'deleted':
        target['deleted'] = True
    elif change == 'missing':
        del store.rows[path('desktop')]
    windows = None
    if change == 'window':
        windows = {'desktop': (T0, T0 + timedelta(seconds=590))}
    before = deepcopy(store.rows)
    assert groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence(), expected_windows=windows) is None
    assert store.rows == before


def test_group_size_is_capped(store, monkeypatch):
    monkeypatch.setattr(groups_db, 'MAX_GROUP_MEMBERS', 2)
    for cid, src in (('a', 'omi'), ('b', 'desktop'), ('c', 'omi')):
        store.rows[path(cid)] = row(cid, src)
    assert groups_db.join_capture_group(UID, 'a', 'b', evidence())
    assert groups_db.join_capture_group(UID, 'c', 'b', evidence()) is None
    assert 'capture_group' not in store.rows[path('c')]


def test_sticky_separation_dissolves_a_pair_and_blocks_regrouping(store):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence())
    assert groups_db.leave_capture_group(UID, 'desktop', sticky=True) is True
    assert store.rows[path('desktop')]['capture_group'] is None
    assert store.rows[path('pendant')]['capture_group'] is None
    assert store.rows[path('desktop')]['capture_group_exclusions'] == ['pendant']
    assert groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence()) is None
    assert groups_db.leave_capture_group(UID, 'desktop', sticky=True) is False


def test_leaving_a_larger_group_recomputes_primary_and_revision(store):
    store.rows.update(
        {
            path('desktop'): row('desktop', 'desktop', 0, 600),
            path('frag1'): row('frag1', 'omi', 0, 300),
            path('frag2'): row('frag2', 'omi', 300, 1800),
        }
    )
    group_id = groups_db.join_capture_group(UID, 'frag1', 'desktop', evidence())
    groups_db.join_capture_group(UID, 'frag2', 'desktop', evidence())
    assert groups_db.leave_capture_group(UID, 'frag2', sticky=False)
    record = store.rows[path('desktop')]['capture_group']
    assert record['id'] == group_id and record['primary_id'] == 'desktop' and record['revision'] == 3
    assert {m['id'] for m in record['members']} == {'desktop', 'frag1'}
    assert store.rows[path('frag2')]['capture_group'] is None
    assert 'capture_group_exclusions' not in store.rows[path('frag2')]


def test_delete_conversation_leaves_its_group_first(monkeypatch):
    calls = []
    monkeypatch.setattr(conversations_db, 'leave_capture_group', lambda *a, **kw: calls.append((a, kw)))
    fake_ref = MagicMock()
    fake_ref.collections.return_value = []
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = fake_ref
    monkeypatch.setattr(conversations_db, 'db', fake_db)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *a: None)
    conversations_db.delete_conversation(UID, 'desktop')
    assert calls == [((UID, 'desktop'), {'sticky': False, 'close': True, 'firestore_client': fake_db})]
    fake_ref.delete.assert_called_once()


def test_processing_writes_never_clobber_membership(monkeypatch):
    fake = StrictFirestore()
    group = {'id': 'g', 'primary_id': 'pendant', 'revision': 1, 'members': []}
    fake.rows[path('pendant')] = {**row('pendant', 'omi', status='processing'), 'capture_group': group}
    monkeypatch.setattr(conversations_db, 'db', fake)
    original_set = StrictFirestoreTransaction.set

    def merge_set(self, ref, data, merge=False):
        # Top-level merge is enough here: the guarded field is a top-level key.
        return original_set(self, ref, {**fake.rows.get(ref.path, {}), **data} if merge else data)

    monkeypatch.setattr(StrictFirestoreTransaction, 'set', merge_set)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(conversations_db, '_reapply_current_manual_assignments', lambda *a: None)
    stale = {
        'id': 'pendant',
        'status': 'completed',
        'data_protection_level': 'standard',
        'capture_group': None,
        'structured': {'title': 'x'},
    }
    assert conversations_db.persist_processing_result_with_lifecycle(UID, stale)
    assert fake.rows[path('pendant')]['capture_group'] == group
    assert fake.rows[path('pendant')]['structured'] == {'title': 'x'}


# --------------------------------------------------------------- finalization seam


@pytest.fixture
def seam(store, monkeypatch):
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, id, **kw: deepcopy(store.rows.get(path(id, uid)))
    )

    def query(uid, *, status, finished_after, limit):
        rows = [
            deepcopy(r)
            for p, r in store.rows.items()
            if p[:2] == ('users', uid) and r['status'] == status and r['finished_at'] >= finished_after
        ]
        return sorted(rows, key=lambda r: r['finished_at'])[:limit]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)
    events = []
    monkeypatch.setattr(policy, 'record_product_event', lambda event, **kw: events.append((event, kw.get('outcome'))))
    return events


def test_confirmed_overlap_is_grouped_and_linked(store, seam):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    policy.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    desktop, pendant = store.rows[path('desktop')], store.rows[path('pendant')]
    assert desktop['external_data']['duplicate_capture_of'] == 'pendant'
    assert desktop['capture_group'] == pendant['capture_group']
    assert ('capture_group_joined', 'applied') in seam


def test_window_overlap_without_shared_speech_is_linked_but_not_grouped(store, seam):
    store.rows.update(
        {path('pendant'): row('pendant', 'omi', text=OTHER), path('desktop'): row('desktop', 'desktop', 100, 590)}
    )
    policy.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert store.rows[path('desktop')]['external_data']['duplicate_capture_of'] == 'pendant'
    assert all('capture_group' not in r for r in store.rows.values())
    assert ('capture_group_joined', 'none') in seam


def test_grouping_failure_is_degraded_not_raised(store, seam, monkeypatch):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    fallback = MagicMock()
    monkeypatch.setattr(policy, 'record_fallback', fallback)
    monkeypatch.setattr(groups_db, 'join_capture_group', MagicMock(side_effect=RuntimeError('must not log this')))
    policy.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert fallback.call_args.kwargs['to_mode'] == 'separate_captures'
    assert store.rows[path('desktop')]['external_data']['duplicate_capture_of'] == 'pendant'


def test_content_checks_are_bounded(store, seam, monkeypatch):
    monkeypatch.setattr(policy, 'MAX_CONTENT_CHECKS', 2)
    store.rows[path('desktop')] = row('desktop', 'desktop', 0, 600)
    for i in range(4):
        store.rows[path(f'p{i}')] = row(f'p{i}', 'omi', 0, 600 + i)
    reads = []
    original = conversations_db.get_conversation_for_capture_check
    monkeypatch.setattr(
        conversations_db,
        'get_conversation_for_capture_check',
        lambda *a, **kw: reads.append(a[1]) or original(*a, **kw),
    )
    policy.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert reads[0] == 'desktop' and len(reads) == 3  # own fresh read + two bounded partners


def test_transcript_changed_after_confirmation_is_not_grouped(store, seam, monkeypatch):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    original = groups_db.join_capture_group

    def edit_then_join(*args, **kwargs):
        store.rows[path('pendant')]['transcript_segments'] = segments(OTHER)
        return original(*args, **kwargs)

    monkeypatch.setattr(groups_db, 'join_capture_group', edit_then_join)
    policy.link_duplicate_captures(UID, Conversation(**store.rows[path('desktop')]))
    assert all('capture_group' not in r for r in store.rows.values())
    assert ('capture_group_joined', 'conflict') in seam


def test_fingerprint_ignores_membership_but_tracks_transcript():
    base = row('a', 'omi')
    grouped = {**base, 'capture_group': {'id': 'g'}, 'external_data': {'x': 1}}
    assert groups_db.transcript_fingerprint(base) == groups_db.transcript_fingerprint(grouped)
    assert groups_db.transcript_fingerprint(base) != groups_db.transcript_fingerprint(row('a', 'omi', text=OTHER))
    assert groups_db.transcript_fingerprint(None) is None


def test_closed_capture_leaves_and_can_never_rejoin(store):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence())
    assert groups_db.leave_capture_group(UID, 'desktop', sticky=False, close=True)
    assert store.rows[path('desktop')]['capture_group_closed'] is True
    assert store.rows[path('pendant')]['capture_group'] is None
    assert groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence()) is None


def test_closing_an_ungrouped_capture_fences_a_racing_join(store):
    store.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    assert groups_db.leave_capture_group(UID, 'desktop', sticky=False, close=True) is False
    assert store.rows[path('desktop')]['capture_group_closed'] is True
    assert groups_db.join_capture_group(UID, 'pendant', 'desktop', evidence()) is None


@pytest.mark.parametrize('gone', ['soft_deleted', 'hard_deleted', 'departed'])
def test_stale_members_are_pruned_when_the_group_is_touched_again(store, gone):
    store.rows.update(
        {
            path('frag1'): row('frag1', 'omi', 0, 300),
            path('desktop'): row('desktop', 'desktop', 0, 600),
            path('long'): row('long', 'omi', 0, 1800),
        }
    )
    group_id = groups_db.join_capture_group(UID, 'frag1', 'desktop', evidence())
    groups_db.join_capture_group(UID, 'long', 'desktop', evidence())
    assert store.rows[path('desktop')]['capture_group']['primary_id'] == 'long'
    if gone == 'soft_deleted':  # e.g. absorbed by sync, which never calls the delete hook
        store.rows[path('long')].update(deleted=True, discarded=True)
    elif gone == 'hard_deleted':
        del store.rows[path('long')]
    else:
        store.rows[path('long')]['capture_group'] = None
    assert groups_db.join_capture_group(UID, 'frag1', 'desktop', evidence()) == group_id
    record = store.rows[path('desktop')]['capture_group']
    assert {m['id'] for m in record['members']} == {'frag1', 'desktop'}
    assert record['primary_id'] == 'desktop' and record['revision'] == 3
    assert store.rows[path('frag1')]['capture_group'] == record


# --------------------------------------------------------------- route


def test_separate_route_is_sticky_and_idempotent(monkeypatch):
    monkeypatch.setattr(router, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    calls = []
    results = iter([True, False])
    monkeypatch.setattr(
        router.conversations_db, 'leave_capture_group', lambda *a, **kw: calls.append((a, kw)) or next(results)
    )
    assert router.separate_conversation_from_capture_group('desktop', uid=UID).status == 'ok'
    assert router.separate_conversation_from_capture_group('desktop', uid=UID).status == 'unchanged'
    assert calls[0] == ((UID, 'desktop'), {'sticky': True})
