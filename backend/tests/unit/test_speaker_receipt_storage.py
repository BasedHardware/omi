"""Real receipt codecs across protection changes; no cloud dependencies."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversations as db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection
from tests.unit.test_manual_speaker_assignments import world, read


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_stored_protection_level_wins_over_cached_hint(world, level):
    store, path, stale = world
    store.rows[path]['data_protection_level'] = level
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    db.update_conversation_segments(
        'u', 'c', stale, data_protection_level='enhanced' if level == 'standard' else 'standard'
    )
    assert isinstance(store.rows[path]['transcript_segments'], str if level == 'enhanced' else bytes)
    assert read(world)['transcript_segments'][1]['person_id'] == 'new'


@pytest.mark.parametrize('value', [[], 'text', 1, None, False])
def test_invalid_receipt_rejected_only_at_write_boundary(value):
    with pytest.raises(ValueError, match='must be an object'):
        db._prepare_conversation_for_write({'manual_speaker_assignments': value}, 'u', 'standard')
    assert db.decode_manual_speaker_assignments('u', db._protect_json_value(value, 'u', 'standard'), True) == {}


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
@pytest.mark.parametrize('receipt_present', [False, True])
@pytest.mark.parametrize('grouping_present', [False, True])
def test_migration_reencodes_receipt_and_transcript_from_current_transaction(
    world, monkeypatch, source, target, receipt_present, grouping_present
):
    store, path, _ = world
    store.rows[path]['data_protection_level'] = source
    if grouping_present:
        store.rows[path]['transcript_segments'][1]['provider_speaker'] = {'scope': 'epoch:a', 'id': 43}
        store.rows[path]['transcript_segments'][1]['speaker_grouping_shadow'] = {'provider_strict': 'user'}
        store.rows[path] = db._prepare_conversation_for_write(store.rows[path], 'u', source)
    if receipt_present:
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    store.rows[path] = db._prepare_conversation_for_write(
        read(world) if receipt_present else store.rows[path], 'u', source
    )
    expected = read(world)
    projection = []

    def get_all(refs, field_paths):
        projection.extend(field_paths)
        for ref in refs:
            snap = ref.get()
            snap.reference = ref
            snap.id = 'c'
            # Simulate an edit committed after the scan's snapshot was obtained.
            if receipt_present:
                db.assign_conversation_speaker('u', 'c', is_user=True, segment_ids=['s0'])
                expected.update(read(world))
            yield snap

    monkeypatch.setattr(store, 'get_all', get_all, raising=False)
    monkeypatch.setattr(store, 'batch', MagicMock, raising=False)
    monkeypatch.setattr(
        StrictFirestoreCollection, 'select', lambda self, fields: SimpleNamespace(stream=lambda: []), raising=False
    )
    monkeypatch.setattr(db, 'db', store)
    db.migrate_conversations_level_batch('u', ['c'], target)
    saved = read(world)
    assert saved['transcript_segments'] == expected['transcript_segments']
    assert saved['manual_speaker_assignments'] == expected['manual_speaker_assignments']
    raw = store.rows[path]
    assert raw['data_protection_level'] == target
    if grouping_present:
        encoded_rows = db._reveal_json_value(raw['transcript_segments'], 'u', True)
        assert 'speaker_grouping_internal' in encoded_rows[1]
        assert 'provider_speaker' not in encoded_rows[1] and 'speaker_grouping_shadow' not in encoded_rows[1]
    assert isinstance(raw['transcript_segments'], str if target == 'enhanced' else bytes)
    if receipt_present:
        assert isinstance(raw['manual_speaker_assignments'], str if target == 'enhanced' else bytes)
    else:
        assert 'manual_speaker_assignments' not in raw
    assert {'manual_speaker_assignments', 'manual_speaker_assignments_compressed'} <= set(projection)
    before = deepcopy(raw)
    # Retry with no intervening edit: already migrated documents stay unchanged.
    monkeypatch.setattr(
        store,
        'get_all',
        lambda refs, field_paths: [SimpleNamespace(exists=True, id='c', reference=ref) for ref in refs],
    )
    db.migrate_conversations_level_batch('u', ['c'], target)
    assert store.rows[path] == before


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_automatic_review_is_emitted_after_commit_and_not_on_retry(world, monkeypatch, level):
    store, path, _ = world
    store.rows[path]['data_protection_level'] = level
    store.rows[path]['transcript_segments'][1]['speaker_match_source'] = 'sync_embedding'
    store.rows[path] = db._prepare_conversation_for_write(store.rows[path], 'u', level)
    observed = []

    def observe(uid, conversation_id, before, after):
        # The callback sees a durably committed manual label and cleared marker.
        saved = read(world)['transcript_segments'][1]
        assert saved['person_id'] == 'new' and saved['speaker_match_source'] is None
        observed.append(before[0].get('speaker_match_source'))

    monkeypatch.setattr(db, 'record_speaker_review', observe)
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    assert observed == ['sync_embedding', None]


@pytest.mark.parametrize('field,error', [('is_locked', PermissionError), ('deleted', LookupError)])
def test_blocked_manual_write_never_emits_review(world, monkeypatch, field, error):
    store, path, _ = world
    store.rows[path][field] = True
    observed = []
    monkeypatch.setattr(db, 'record_speaker_review', lambda *args: observed.append(args))
    with pytest.raises(error):
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    assert observed == []


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_shadow_agreement_only_after_committed_correction(world, monkeypatch, level):
    from utils.conversations import speaker_grouping_shadow as shadow

    store, path, _ = world
    store.rows[path]['data_protection_level'] = level
    store.rows[path]['transcript_segments'][1]['speaker_grouping_shadow'] = {
        'provider_strict': 'person:new',
        'owner_link': 'user',
    }
    store.rows[path] = db._prepare_conversation_for_write(store.rows[path], 'u', level)
    events = []
    monkeypatch.setattr(shadow, 'count', lambda variant, outcome, amount=1: events.append((variant, outcome)))
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    assert events == [('provider_strict', 'correction_agreed'), ('owner_link', 'correction_disagreed')]
    assert read(world)['transcript_segments'][1]['speaker_grouping_shadow']['owner_link'] == 'user'
    events.clear()
    with pytest.raises(ValueError):
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['missing'])
    assert not events


@pytest.mark.parametrize('kind', ['not_me', 'not_person', 'not_a_person'])
@pytest.mark.parametrize('selection', ['speaker', 'segment_spillover', 'segment_only'])
def test_negative_corrections_never_enter_exact_identity_denominator(world, monkeypatch, kind, selection):
    from utils.conversations import speaker_grouping_shadow as shadow

    store, path, _ = world
    # Same voice: selected rejection may spill over to the other saved segment.
    rows = store.rows[path]['transcript_segments']
    for s in rows[:2]:
        s['speaker_id'] = 0
        s['speaker_grouping_shadow'] = {'provider_strict': 'user', 'owner_link': 'unknown'}
    store.rows[path] = db._prepare_conversation_for_write(store.rows[path], 'u', 'standard')
    events = []
    monkeypatch.setattr(shadow, 'count', lambda variant, outcome, amount=1: events.append((variant, outcome)))
    kwargs = {'speaker_id': 0} if selection == 'speaker' else {'segment_ids': ['s0']}
    if selection == 'segment_only':
        kwargs['time_range'] = (0, 1)
    rejection = {'kind': kind, 'person_id': 'new'}
    _, selected, _, _ = db.assign_conversation_speaker('u', 'c', rejection=rejection, **kwargs)
    assert len(selected) == (1 if selection == 'segment_only' else 2)
    assert len(events) == len(selected) * 2
    assert all(outcome == 'correction_negative_skipped' for _, outcome in events)
    # A newer positive identity wins over the prior rejection for scoring too.
    events.clear()
    db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    assert ('provider_strict', 'correction_agreed') in events
    assert ('owner_link', 'correction_disagreed') in events
    assert all(outcome != 'correction_negative_skipped' for _, outcome in events)
