"""Overlapping strict generations bind only through the phone's stamp.

A stamp append or smart merge can grow one generation's stored interval over its
successor's, so more than one generation can strictly contain a segment. Silence
rollovers also mint rows whose ``started_at`` is back-dated before wall-clock
creation, so no local clock reliably names the owner. When several strict
matches canonicalize differently the plan stays undecidable: the segment
carries no target and the ``ambiguous_pending`` binding token until a stamp
that names one of the strict rows — by id or by canonical — disambiguates it.
A folded donor whose canonical survivor is unambiguous still binds, tolerant
overlap stays ambiguous, and a truncated lineage still binds nothing. All ids
are synthetic.
"""

import math
from copy import deepcopy

import pytest

from tests.unit.test_sync_cross_job_assignment import conversations
from tests.unit.test_sync_recording_lineage import (
    ORIGIN,
    at,
    generation,
    plan,
    replay,
    seeded_store,
    spans,
    sync_chunk,
    texts,
)
from utils.sync.recording_lineage import select_segment_targets


def backdated(row_id, start, end, created, **extra):
    """A generation whose stored interval can reach before its wall-clock creation."""
    row = generation(
        0,
        id=row_id,
        started_at=at(start),
        finished_at=at(end),
        external_data={'recording_session_id': f'SESSION-{row_id}', 'recording_origin_id': ORIGIN},
    )
    if created is not None:
        row['created_at'] = at(created)
    row.update(extra)
    return row


def overlap_rows():
    """Luna A 12:00-12:20 and B backdated to 12:18 while created at 12:19."""
    return [
        backdated('GEN-A', 43200, 44400, 43200),
        backdated('GEN-B', 44280, 45000, 44340),
    ]


def select(rows, chunk, **kwargs):
    return select_segment_targets(
        rows,
        ORIGIN,
        spans([chunk]),
        stamped_target=kwargs.pop('stamp', None),
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        **kwargs,
    )


def test_overlap_with_a_compatible_stamp_binds_the_stamped_row():
    chunk = sync_chunk(44300, 44330, 'buffered speech in the overlap')
    assert select(overlap_rows(), chunk, stamp='GEN-B').targets == {chunk['id']: 'GEN-B'}
    assert select(overlap_rows(), chunk, stamp='GEN-A').targets == {chunk['id']: 'GEN-A'}


def test_overlap_with_a_compatible_stamp_counts_bound_once():
    chunk = sync_chunk(44300, 44330, 'buffered speech in the overlap')
    result = select(overlap_rows(), chunk, stamp='GEN-B')
    assert result.outcome == 'bound' and result.counts == {
        'bound': 1,
        'stamp_overridden': 0,
        'stamp_fallback': 0,
        'unbound': 0,
    }
    assert result.binding_reasons == {chunk['id']: 'bound'}


@pytest.mark.parametrize('stamp', [None, 'STAMP', 'GEN-UNRELATED'])
def test_overlap_without_a_compatible_stamp_stays_pending(stamp):
    chunk = sync_chunk(44300, 44330, 'buffered speech in the overlap')
    result = select(overlap_rows(), chunk, stamp=stamp)
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'}
    assert result.reason == 'ambiguous_overlap' and result.outcome == 'interval_miss'
    assert result.counts['unbound'] == 1


def test_overlap_without_safe_handling_keeps_the_plain_miss():
    chunk = sync_chunk(44300, 44330, 'buffered speech in the overlap')
    result = select(overlap_rows(), chunk, stamp='STAMP', safe_overlap=False)
    assert result.targets == {chunk['id']: 'STAMP'}
    assert result.binding_reasons == {chunk['id']: 'stamp_fallback'}


@pytest.mark.parametrize('created', [44340, None])
@pytest.mark.parametrize('reverse', [False, True])
def test_ambiguity_never_falls_back_to_an_id_winner(created, reverse):
    rows = [
        backdated('GEN-AAA', 43200, 44400, created),
        backdated('GEN-ZZZ', 43200, 44400, created),
    ]
    chunk = sync_chunk(43400, 43430, 'speech inside identical intervals')
    ordered = list(reversed(rows)) if reverse else rows
    result = select(ordered, chunk)
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'}


@pytest.mark.parametrize('reverse', [False, True])
def test_a_compatible_stamp_ignores_row_order_and_id_order(reverse):
    rows = [
        backdated('GEN-AAA', 43200, 44400, 44340),
        backdated('GEN-ZZZ', 43200, 44400, 44340),
    ]
    chunk = sync_chunk(43400, 43430, 'speech inside identical intervals')
    ordered = list(reversed(rows)) if reverse else rows
    result = select(ordered, chunk, stamp='GEN-AAA')
    assert result.targets == {chunk['id']: 'GEN-AAA'}
    assert result.counts['bound'] == 1


def test_overlapping_generations_sharing_a_canonical_keep_the_unique_binding():
    donor = backdated(
        'GEN-DONOR',
        44100,
        44700,
        44340,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-A',
        smart_merge={'role': 'donor'},
    )
    rows = [backdated('GEN-A', 43200, 44400, 43200), donor]
    chunk = sync_chunk(44300, 44330, 'speech both folded rows contain')
    result = select(rows, chunk)
    assert result.targets == {chunk['id']: 'GEN-A'}


def test_an_incomplete_overlap_set_still_binds_nothing():
    store = seeded_store(overlap_rows())
    chunk = sync_chunk(44300, 44330, 'speech inside both rows')
    result = plan(store, [chunk], truncated_before=math.inf)
    assert result.targets == {chunk['id']: None} and result.reason == 'truncated'


def straddling_rows():
    """GEN-A 12:00-12:20 and GEN-B 12:20:03-12:30: a chunk can tolerate both."""
    return [backdated('GEN-A', 43200, 44400, 43200), backdated('GEN-B', 44403, 45000, 44403)]


def test_tolerant_only_overlap_stays_ambiguous():
    chunk = sync_chunk(44399, 44410, 'speech straddling the rollover')
    result = select(straddling_rows(), chunk)
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'}
    assert result.reason == 'ambiguous_overlap'


@pytest.mark.parametrize('stamp', [None, 'STAMP', 'GEN-UNRELATED'])
def test_tolerant_overlap_without_a_compatible_stamp_stays_pending(stamp):
    chunk = sync_chunk(44399, 44410, 'speech straddling the rollover')
    result = select(straddling_rows(), chunk, stamp=stamp)
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'}
    assert result.reason == 'ambiguous_overlap' and result.outcome == 'interval_miss'
    assert result.counts['unbound'] == 1


@pytest.mark.parametrize('stamp', ['GEN-A', 'GEN-B'])
def test_tolerant_overlap_binds_the_compatible_stamp(stamp):
    chunk = sync_chunk(44399, 44410, 'speech straddling the rollover')
    result = select(straddling_rows(), chunk, stamp=stamp)
    assert result.targets == {chunk['id']: stamp}
    assert result.binding_reasons == {chunk['id']: 'bound'}
    assert result.counts['bound'] == 1


def test_tolerant_overlap_sharing_a_canonical_binds_without_a_stamp():
    donor = backdated(
        'GEN-DONOR',
        43100,
        44405,
        43100,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-A',
        smart_merge={'role': 'donor'},
    )
    rows = [backdated('GEN-A', 43200, 44400, 43200), donor]
    chunk = sync_chunk(44399, 44410, 'speech straddling the rollover')
    result = select(rows, chunk)
    assert result.targets == {chunk['id']: 'GEN-A'}
    assert result.binding_reasons == {chunk['id']: 'bound'}


def test_a_stamp_naming_a_row_outside_the_tolerant_set_stays_pending():
    rows = straddling_rows() + [backdated('GEN-C', 40000, 41000, 40000)]
    chunk = sync_chunk(44399, 44410, 'speech straddling the rollover')
    result = select(rows, chunk, stamp='GEN-C')
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'}


def test_tolerant_overlap_without_safe_handling_keeps_the_legacy_miss():
    chunk = sync_chunk(44399, 44410, 'speech straddling the rollover')
    unstamped = select(straddling_rows(), chunk, safe_overlap=False)
    assert unstamped.targets == {chunk['id']: None}
    assert unstamped.binding_reasons == {chunk['id']: 'unbound'}
    assert unstamped.reason == 'interval_miss'
    stamped = select(straddling_rows(), chunk, stamp='STAMP', safe_overlap=False)
    assert stamped.targets == {chunk['id']: 'STAMP'}
    assert stamped.binding_reasons == {chunk['id']: 'stamp_fallback'}
    assert stamped.reason == 'interval_miss'


def test_new_speech_lands_on_the_stamped_row_without_new_conversations():
    store = seeded_store(overlap_rows())
    before = {row['id'] for row in conversations(store)}
    chunk = sync_chunk(44300, 44330, 'genuinely new speech the live socket missed')
    targets = plan(store, [chunk], stamp='GEN-B').targets
    assert targets == {chunk['id']: 'GEN-B'}
    replay(store, [chunk], targets)
    assert {row['id'] for row in conversations(store)} == before
    assert 'genuinely new speech the live socket missed' in texts(store, 'GEN-B')
    assert 'genuinely new speech the live socket missed' not in texts(store, 'GEN-A')


def test_pending_overlap_writes_nothing_until_a_retry_binds_the_stamp():
    store = seeded_store(overlap_rows())
    before = deepcopy(store.rows)
    chunk = sync_chunk(44300, 44330, 'genuinely new speech inside the ambiguous window')
    pending = plan(store, [chunk], stamp='STAMP')
    assert pending.targets == {chunk['id']: None}
    assert pending.binding_reasons == {chunk['id']: 'ambiguous_pending'}
    assert store.rows == before
    bound = plan(store, [chunk], stamp='GEN-B')
    replay(store, [chunk], bound.targets)
    assert 'genuinely new speech inside the ambiguous window' in texts(store, 'GEN-B')
    assert 'genuinely new speech inside the ambiguous window' not in texts(store, 'GEN-A')


def test_a_stamp_that_is_not_strictly_covering_stays_pending():
    rows = [
        backdated('GEN-A', 43200, 44400, 43200),
        backdated('GEN-B', 44280, 45000, 44340),
        backdated('GEN-C', 43260, 44460, 43260),
    ]
    chunk = sync_chunk(43300, 43330, 'speech outside the stamped row')
    result = select(rows, chunk, stamp='GEN-B')
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'}


def test_luna_backdated_buffered_audio_lands_in_stamped_generation():
    """The saved-row set is the observable contract: no sync upload may mint a row."""
    store = seeded_store(overlap_rows())
    chunk = sync_chunk(44300, 44330, 'synthetic Luna buffered speech inside the overlapping generation window')
    replay(store, [chunk], plan(store, [chunk], stamp='GEN-B').targets)
    assert {row['id'] for row in conversations(store)} == {'GEN-A', 'GEN-B'}
    stored = texts(store, 'GEN-B')
    assert 'synthetic Luna buffered speech inside the overlapping generation window' in stored
    assert all('synthetic Luna buffered' not in text for text in texts(store, 'GEN-A'))
