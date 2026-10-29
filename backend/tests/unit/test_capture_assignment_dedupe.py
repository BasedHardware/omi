"""Generated lexical fixtures exercise the shared capture decision."""

from copy import deepcopy
from datetime import datetime, timezone
import random
import string

import pytest

from utils.capture.dedupe import choose_segments, dedupe_segments
from utils.capture.identity import compatible_keys
from utils.sync.live_overlap import choose_live_overlap


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from utils.sync import assignment
    from database import conversations


def lexical(seed, count=12):
    rng = random.Random(seed)
    return ' '.join(''.join(rng.choices(string.ascii_lowercase, k=9)) for _ in range(count))


def segment(seed=1, start=1000, *, changed=False, **extra):
    words = lexical(seed).split()
    if changed:
        words[4] = lexical(90, 1)
    return dict(start=start - 1000, end=start - 1000 + 6, timestamp=start, text=' '.join(words), **extra)


def row(key='capture-a', **extra):
    return dict(
        id='live',
        source='omi',
        client_device_id='synthetic-device',
        status='in_progress',
        started_at=datetime.fromtimestamp(1000, timezone.utc),
        finished_at=datetime.fromtimestamp(1100, timezone.utc),
        capture_evidence={'capture_root': key, 'channel': 'mono', 'clock_epoch': '0'},
        **extra,
    )


def dedupe(existing, incoming, **kwargs):
    return dedupe_segments(existing, incoming, incoming_row=row(), reference_row=row(), **kwargs)


@pytest.mark.parametrize('path', ['bridge', 'incoming'])
def test_shared_near_duplicate_ignores_conflicting_owner_labels(monkeypatch, path):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    old = [segment(is_user=True, person_id=None)]
    incoming = [segment(changed=True, start=1000.5, is_user=False, person_id='synthetic-person')]
    snapshot = deepcopy((old, incoming))
    assert (
        choose_segments('synthetic-account', path, old, incoming, incoming, incoming_row=row(), reference_row=row())
        == []
    )
    assert (old, incoming) == snapshot


@pytest.mark.parametrize('mode', ['off', 'shadow', 'typo'])
def test_shadow_and_off_keep_legacy_objects(monkeypatch, caplog, mode):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    old, incoming = [segment()], [segment(changed=True)]
    with caplog.at_level('INFO'):
        kept = choose_segments(
            'synthetic-account', 'bridge', old, incoming, incoming, incoming_row=row(), reference_row=row()
        )
    assert kept is incoming
    assert ('event=refactor_shadow lane=L1 check=bridge outcome=disagree' in caplog.text) == (mode != 'off')
    assert incoming[0]['text'] not in caplog.text and 'synthetic-account' not in caplog.text


def test_frame_proof_requires_lexical_checks_and_same_scope_retry_still_drops():
    existing = [segment(), segment(3, speaker_id_scope='sync:scope')]
    incoming = [segment(2, start=2000), segment(3, speaker_id_scope='sync:scope')]
    assert dedupe(existing, incoming, proof=lambda *args: frozenset({0})) == incoming[:1]


def test_text_fallback_uses_whole_conversation_offset():
    existing = [segment(i, 1000 + i * 10) for i in range(3)]
    incoming = [segment(2, 1060.5, changed=True)]
    donor = row()
    donor['id'] = 'donor'
    donor['transcript_segments'] = [segment(i, 1040 + i * 10) for i in range(2)]
    assert dedupe(existing, incoming) == incoming
    assert dedupe(existing, incoming, conversation_rows=[donor]) == []


def test_repeated_anchor_text_does_not_establish_a_clock():
    old = [segment(1, 1000), segment(1, 1010)]
    new = [segment(1, 1040), segment(1, 1050)]
    assert dedupe(old, new) == new


@pytest.mark.parametrize('distance', [3, 30, 100])
def test_unproven_repeated_text_outside_narrow_window_is_kept(distance):
    incoming = [segment(start=1000 + distance)]
    assert dedupe([segment()], incoming) == incoming


def test_short_repetition_and_changed_numbers_are_kept():
    old, incoming = segment(), segment()
    old['text'] = incoming['text'] = lexical(3, 2)
    assert dedupe([old], [incoming]) == [incoming]
    old, incoming = segment(), segment()
    old['text'] += ' 17'
    incoming['text'] += ' 18'
    assert dedupe([old], [incoming]) == [incoming]


@pytest.mark.parametrize('mismatch', ['source', 'client_device_id', 'sync_clock_run', 'is_locked', 'key'])
def test_dedupe_never_crosses_partition_or_explicit_capture_key(mismatch):
    old, incoming = [segment()], [segment()]
    target, upload = row(), row()
    if mismatch == 'key':
        upload = row('capture-b')
    else:
        upload[mismatch] = True if mismatch == 'is_locked' else 'different'
    assert dedupe_segments(old, incoming, incoming_row=upload, reference_row=target) == incoming


def test_live_runs_and_sync_receipts_share_explicit_key():
    live = dict(
        row(),
        capture_evidence={
            'origin': 'live',
            'runs': [{'capture_root': 'capture-a', 'channel': 'mono', 'clock_epoch': 0}],
        },
    )
    upload = dict(
        row(),
        capture_evidence={
            'origin': 'sync_vad',
            'receipts': [{'capture_root': 'capture-a', 'channel': 'mono', 'clock_epoch': 0}],
        },
    )
    assert compatible_keys(live, upload)
    assert not compatible_keys(live, dict(upload, capture_evidence={}))


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_same_key_open_empty_occasion_binds_only_when_serving(monkeypatch, mode):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    target = row(has_content=False, transcript_segments=[])
    assert choose_live_overlap([target], row()) == ('live' if mode == 'serve' else None)


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_new_bind_rejects_explicit_key_mismatch(monkeypatch, mode):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    target = row(has_content=True, sync_live_target=True)
    assert choose_live_overlap([target], row('capture-b')) == ('live' if mode == 'shadow' else None)


@pytest.mark.parametrize('empty', [False, True])
def test_bridge_and_open_binding_in_transaction(monkeypatch, empty):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync.assignment import assign_in_transaction

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'off')
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    store = StrictFirestore()
    target = row(has_content=not empty, transcript_segments=[] if empty else [segment(is_user=True)], discarded=False)
    store.rows[('users', 'synthetic-account', 'conversations', 'live')] = deepcopy(target)
    if not empty:
        donor = row(
            has_content=True,
            transcript_segments=[segment(changed=True, is_user=False)],
            discarded=False,
            sync_content_revision=1,
        )
        donor['id'] = 'donor'
        store.rows[('users', 'synthetic-account', 'conversations', 'donor')] = donor
    incoming = row(has_content=True, transcript_segments=[segment(9, 1080)], discarded=False)
    incoming['id'] = 'upload'
    merged, created, kept = assign_in_transaction(
        store.transaction(),
        store.collection('users').document('synthetic-account'),
        incoming,
        live_candidate_ids=('live',),
        candidate_id='donor' if not empty else None,
        decode=deepcopy,
        encode=deepcopy,
        invalidate=lambda _: None,
    )
    assert not created and merged['id'] == 'live' and merged['sync_live_target']
    assert len(merged['transcript_segments']) == (1 if empty else 2) and len(kept) == 1
    if not empty:
        assert store.rows[('users', 'synthetic-account', 'conversations', 'donor')]['sync_merged_into'] == 'live'


@pytest.mark.parametrize('dimension', ['channel', 'clock_epoch', 'session', 'missing_session'])
def test_all_explicit_key_dimensions_require_equality(dimension):
    target, upload = row(), row()
    if dimension in ('channel', 'clock_epoch'):
        upload['capture_evidence'][dimension] = 'different'
    else:
        target['external_data'] = {'recording_session_id': 'synthetic-session'}
        if dimension == 'session':
            upload['external_data'] = {'recording_session_id': 'different-session'}
    assert not compatible_keys(target, upload)


def test_real_frame_proof_drops_even_with_fleet_dedupe_enabled(monkeypatch):
    import uuid
    from utils.capture.frame_proof import covered_indices

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    root = str(uuid.UUID(int=1))
    target, upload = row(), row()
    target['capture_evidence'] = dict(
        version=1,
        capability='source_position',
        coverage='mapped',
        origin='live',
        conflicts=0,
        runs=[
            dict(
                capture_root=root,
                clock_epoch=0,
                rate_hz=16000,
                channel='mono',
                source_frame_start=0,
                source_frame_end=100,
                decoded_sample_start=0,
                decoded_sample_end=16000,
                samples_per_frame=160,
            )
        ],
    )
    upload['capture_evidence'] = dict(
        version=1,
        capability='source_position',
        coverage='mapped',
        origin='sync_vad',
        receipts=[
            dict(
                segment_id='synthetic-segment',
                capture_root=root,
                clock_epoch=0,
                rate_hz=16000,
                channel='mono',
                source_start_frame=10,
                source_end_frame=20,
                source_start_offset=0,
                source_end_offset=0,
            )
        ],
    )
    incoming = [segment(1, id='synthetic-segment')]
    target['capture_evidence'].update(
        proof='committed_transcript_v1',
        lifetime=dict(
            version=1,
            complete=True,
            conflicts=0,
            history=[
                dict(
                    capture_root=root,
                    clock_epoch=0,
                    rate_hz=16000,
                    source_frame_start=0,
                    source_frame_end=100,
                    receipt_wall_start=1000.0,
                    receipt_wall_end=1001.0,
                )
            ],
        ),
    )
    target['capture_evidence']['runs'][0].update(receipt_wall_start=1000.0, receipt_wall_end=1001.0)
    assert covered_indices(incoming, upload, [target]) == frozenset({0})
    assert (
        choose_segments(
            'synthetic-account', 'incoming', [segment()], incoming, incoming, incoming_row=upload, reference_row=target
        )
        == []
    )


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_incompatible_key_cannot_become_a_bridge_donor(monkeypatch, mode):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync.assignment import assign_in_transaction

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    store = StrictFirestore()
    target = row(has_content=True, sync_live_target=True, transcript_segments=[segment()], discarded=False)
    donor = row(
        'capture-b', has_content=True, transcript_segments=[segment(3)], discarded=False, sync_content_revision=1
    )
    donor['id'] = 'donor'
    store.rows[('users', 'synthetic-account', 'conversations', 'live')] = deepcopy(target)
    store.rows[('users', 'synthetic-account', 'conversations', 'donor')] = deepcopy(donor)
    incoming = row(has_content=True, transcript_segments=[segment(9, 1080)], discarded=False)
    incoming['id'] = 'upload'
    assigned, _, _ = assign_in_transaction(
        store.transaction(),
        store.collection('users').document('synthetic-account'),
        incoming,
        live_candidate_ids=('live',),
        candidate_id='donor',
        decode=deepcopy,
        encode=deepcopy,
        invalidate=lambda _: None,
    )
    assert assigned['id'] == 'live'
    stored = store.rows[('users', 'synthetic-account', 'conversations', 'donor')]
    assert bool(stored.get('sync_merged_into')) == (mode == 'shadow')
    if mode == 'serve':
        assert stored == donor


def positioned_row(start, end, start_offset=0, end_offset=0, seed=1):
    import uuid

    item = row(has_content=True, transcript_segments=[segment(seed, id=f'segment-{seed}')])
    item['capture_evidence'] = dict(
        version=1,
        capability='source_position',
        origin='sync_vad',
        coverage='mapped',
        receipts=[
            dict(
                segment_id=f'segment-{seed}',
                capture_root=str(uuid.UUID(int=1)),
                channel='mono',
                clock_epoch=0,
                rate_hz=16000,
                source_start_frame=start,
                source_start_offset=start_offset,
                source_end_frame=end,
                source_end_offset=end_offset,
            )
        ],
    )
    return item


@pytest.mark.parametrize(
    'stored,expected',
    [
        ((10, 20, 0, 0), True),
        ((10, 20, 4, 7), False),
        ((10, 20, 0, 7), True),
        ((10, 10, 4, 7), False),
    ],
)
def test_receipt_full_frame_proof(stored, expected):
    from utils.capture.frame_proof import covered_indices

    upload = positioned_row(10, 20, seed=2)
    target = positioned_row(*stored)
    assert bool(covered_indices(upload['transcript_segments'], upload, [target])) == expected


@pytest.mark.parametrize(
    'stored,expected',
    [
        ((10, 10, 4, 7), True),
        ((10, 10, 4, 6), False),
        ((10, 10, 5, 7), False),
        ((10, 10, 0, 7), False),
        ((9, 11, 0, 0), True),
    ],
)
def test_partial_receipt_edges_need_matching_offsets(stored, expected):
    from utils.capture.frame_proof import covered_indices

    upload = positioned_row(10, 10, 4, 7, seed=2)
    target = positioned_row(*stored)
    assert bool(covered_indices(upload['transcript_segments'], upload, [target])) == expected


def test_receipt_union_and_absent_committed_segment():
    from utils.capture.frame_proof import covered_indices

    upload = positioned_row(10, 30, seed=3)
    first, second = positioned_row(10, 20), positioned_row(20, 30, seed=2)
    assert covered_indices(upload['transcript_segments'], upload, [first, second]) == frozenset({0})
    second['transcript_segments'] = []
    assert not covered_indices(upload['transcript_segments'], upload, [first, second])


@pytest.mark.parametrize('scope', [None, 'sync:synthetic-file'])
def test_positioned_uncovered_speech_never_uses_text_fallback(scope):
    upload, target = positioned_row(40, 50), positioned_row(10, 20)
    for item in (upload, target):
        item['transcript_segments'][0]['speaker_id_scope'] = scope
    incoming = upload['transcript_segments']
    assert (
        dedupe_segments(target['transcript_segments'], incoming, incoming_row=upload, reference_row=target) == incoming
    )


def test_same_audio_with_novel_words_is_kept_despite_receipt_proof():
    upload, target = positioned_row(10, 20, seed=2), positioned_row(10, 20)
    assert (
        dedupe_segments(
            target['transcript_segments'], upload['transcript_segments'], incoming_row=upload, reference_row=target
        )
        == upload['transcript_segments']
    )


@pytest.mark.parametrize('session', [None, 'synthetic-session'])
@pytest.mark.parametrize('change', ['novel', 'number', 'negation', 'correction', 'exact'])
def test_transaction_capture_proven_incoming_obeys_lexical_contract(monkeypatch, session, change):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync.assignment import assign_in_transaction

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    store = StrictFirestore()
    first = positioned_row(10, 20, seed=1)
    first['id'] = 'first'
    second = positioned_row(10, 20, seed=2)
    second['id'] = 'second'
    first['transcript_segments'][0]['text'] = lexical(1, 24)
    second['transcript_segments'][0]['text'] = lexical(1, 24)
    if change == 'novel':
        second['transcript_segments'][0]['text'] += ' ' + lexical(99, 1)
    elif change == 'number':
        first['transcript_segments'][0]['text'] += ' 17'
        second['transcript_segments'][0]['text'] += ' 18'
    elif change == 'negation':
        second['transcript_segments'][0]['text'] += " don't"
    elif change == 'correction':
        second['transcript_segments'][0]['text'] += ' actually'
    for item in (first, second):
        if session:
            item['capture_evidence']['recording_session_id'] = session
        assigned, _, kept = assign_in_transaction(
            store.transaction(),
            store.collection('users').document('synthetic-account'),
            item,
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda _: None,
        )
    assert assigned['id'] == 'first'
    assert kept == ([] if change == 'exact' else second['transcript_segments'])
    assert len(assigned['transcript_segments']) == (1 if change == 'exact' else 2)
    assert {s['text'] for s in assigned['transcript_segments']} == {
        first['transcript_segments'][0]['text'],
        second['transcript_segments'][0]['text'],
    }


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_session_persistence_is_serve_only_and_preserves_external_data(monkeypatch, mode):
    from utils.capture.identity import persist_identity

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    result = {'external_data': {'synthetic_field': 'retained'}}
    incoming = row()
    incoming['capture_evidence']['recording_session_id'] = 'synthetic-session'
    persist_identity('synthetic-account', result, incoming, None)
    assert result['external_data']['synthetic_field'] == 'retained'
    assert result['external_data'].get('recording_session_id') == ('synthetic-session' if mode == 'serve' else None)


@pytest.mark.parametrize('change', ['novel', 'number', 'negation', 'correction', 'multiplicity', 'exact'])
@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_capture_proven_incoming_lexical_contract_and_shadow_telemetry(monkeypatch, caplog, change, mode):
    from utils.capture.frame_proof import covered_indices
    from utils.capture.shadow import SHADOW

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S', raising=False)
    upload, target = positioned_row(10, 20, seed=2), positioned_row(10, 20)
    old = target['transcript_segments'][0]
    new = upload['transcript_segments'][0]
    old['text'] = lexical(1, 24)
    new['text'] = old['text']
    if change == 'novel':
        new['text'] += ' ' + lexical(99, 1)
    elif change == 'number':
        old['text'] += ' 17'
        new['text'] += ' 18'
    elif change == 'negation':
        new['text'] += " don't"
    elif change == 'correction':
        new['text'] += ' actually'
    elif change == 'multiplicity':
        new['text'] += ' ' + new['text'].split()[0]
    incoming = [new]
    snapshot = deepcopy((target, upload))
    assert covered_indices(incoming, upload, [target]) == frozenset({0})
    proposed = [] if change == 'exact' else incoming
    assert dedupe_segments([old], incoming, incoming_row=upload, reference_row=target) == proposed
    metric = SHADOW.labels(path='incoming', outcome='disagree' if change == 'exact' else 'agree')
    before = metric._value.get()
    with caplog.at_level('INFO'):
        kept = choose_segments(
            'synthetic-account', 'incoming', [old], incoming, incoming, incoming_row=upload, reference_row=target
        )
    assert kept == (proposed if mode == 'serve' else incoming)
    assert metric._value.get() == before + 1
    assert f"check=incoming outcome={'disagree' if change == 'exact' else 'agree'}" in caplog.text
    assert new['text'] not in caplog.text and 'synthetic-account' not in caplog.text
    assert (target, upload) == snapshot


def test_capture_proven_exact_retry_keeps_original_indices_after_lexical_drop():
    existing = [segment(1), segment(2, start=1010), segment(3, start=1020)]
    incoming = [segment(1), segment(2, start=1010), segment(3, start=1020)]
    incoming[1]['text'] += ' actually'
    # The short exact retry cannot pass the lexical token minimum.
    existing[2]['text'] = incoming[2]['text'] = lexical(3, 2)
    assert dedupe(existing, incoming, proof=lambda *args: frozenset({0, 1, 2})) == incoming[1:2]
