"""Overlapping strict generations bind deterministically to the later-created row.

A stamp append or smart merge can grow one generation's stored interval over its
successor's, so more than one generation can strictly contain a segment. Silence
rollovers also mint rows whose ``started_at`` is back-dated before wall-clock
creation (``created_at`` is the rollover time). The segment belongs to exactly
one of them: prefer the row whose creation interval proxy — its stored start
clamped to its observed creation time — holds the segment; among those, the
later-created row wins, with the row id as the final deterministic tie-break.
Tolerant-only overlap stays ambiguous, and a truncated lineage still binds
nothing. All ids are synthetic.
"""

import math

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
    """Two strict-overlap generations; the later one was created inside the first's span."""
    return [
        backdated('GEN-EARLY', 1000, 2000, 1000),
        backdated('GEN-LATE', 1400, 2400, 1800),
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


def test_segment_inside_both_proxy_intervals_binds_the_later_created():
    result = select(overlap_rows(), sync_chunk(1900, 1910, 'buffered speech both rows could own'))
    assert result.targets == {'SYNC-1900': 'GEN-LATE'} and result.outcome == 'bound'


def test_segment_before_the_later_creation_binds_the_row_that_covers_it():
    result = select(overlap_rows(), sync_chunk(1500, 1510, 'speech only the first row captured'))
    assert result.targets == {'SYNC-1500': 'GEN-EARLY'}


@pytest.mark.parametrize('overlap', [290, 420])
def test_backdated_overlap_width_does_not_change_the_winner(overlap):
    rows = [
        backdated('GEN-EARLY', 1000, 2000, 1000),
        backdated('GEN-LATE', 2000 - overlap, 3000 - overlap, 1500),
    ]
    result = select(rows, sync_chunk(1990, 1999, 'speech inside the overlap'))
    assert result.targets == {'SYNC-1990': 'GEN-LATE'}


@pytest.mark.parametrize('reverse', [False, True])
def test_exact_creation_tie_picks_a_stable_id_regardless_of_row_order(reverse):
    rows = [
        backdated('GEN-AAA', 1000, 2000, 1500),
        backdated('GEN-ZZZ', 1000, 2000, 1500),
    ]
    chunk = sync_chunk(1500, 1510, 'speech inside identical intervals')
    first = select(list(reversed(rows)) if reverse else rows, chunk)
    second = select(rows if reverse else list(reversed(rows)), chunk)
    assert first.targets == second.targets == {'SYNC-1500': 'GEN-ZZZ'}


@pytest.mark.parametrize('reverse', [False, True])
def test_missing_creation_metadata_still_resolves_deterministically(reverse):
    rows = [backdated('GEN-AAA', 1000, 2000, None), backdated('GEN-ZZZ', 1000, 2000, None)]
    chunk = sync_chunk(1500, 1510, 'speech inside identical intervals')
    first = select(list(reversed(rows)) if reverse else rows, chunk)
    second = select(rows if reverse else list(reversed(rows)), chunk)
    assert first.targets == second.targets == {'SYNC-1500': 'GEN-ZZZ'}


def test_overlapping_generations_sharing_a_canonical_keep_the_unique_binding():
    donor = backdated(
        'GEN-DONOR',
        1500,
        2300,
        1700,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-EARLY',
        smart_merge={'role': 'donor'},
    )
    rows = [backdated('GEN-EARLY', 1000, 2000, 1000), donor]
    result = select(rows, sync_chunk(1700, 1710, 'speech both folded rows contain'))
    assert result.targets == {'SYNC-1700': 'GEN-EARLY'}


def test_an_incomplete_overlap_set_still_binds_nothing():
    store = seeded_store(overlap_rows())
    chunk = sync_chunk(1900, 1910, 'speech inside both rows')
    result = plan(store, [chunk], truncated_before=math.inf)
    assert result.targets == {chunk['id']: None} and result.reason == 'truncated'


def test_tolerant_only_overlap_stays_ambiguous():
    rows = [backdated('GEN-EARLY', 1000, 2000, 1000), backdated('GEN-LATE', 2003, 2400, 2003)]
    chunk = sync_chunk(1999, 2010, 'speech straddling the rollover')
    result = select(rows, chunk)
    assert result.targets == {chunk['id']: None} and result.reason == 'interval_miss'


def test_new_speech_lands_on_the_chosen_row_without_new_conversations():
    rows = overlap_rows()
    store = seeded_store(rows)
    before = {row['id'] for row in conversations(store)}
    chunk = sync_chunk(1900, 1910, 'genuinely new speech the live socket missed')
    targets = plan(store, [chunk]).targets
    assert targets == {chunk['id']: 'GEN-LATE'}
    replay(store, [chunk], targets)
    assert {row['id'] for row in conversations(store)} == before
    assert 'genuinely new speech the live socket missed' in texts(store, 'GEN-LATE')
    assert 'genuinely new speech the live socket missed' not in texts(store, 'GEN-EARLY')


def test_late_created_row_does_not_steal_speech_outside_its_creation_interval():
    store = seeded_store(overlap_rows())
    before = {row['id'] for row in conversations(store)}
    chunks = [
        sync_chunk(1500, 1510, 'early speech only the first generation captured'),
        sync_chunk(1900, 1910, 'later speech inside both proxy intervals'),
    ]
    targets = plan(store, chunks).targets
    assert [targets[chunk['id']] for chunk in chunks] == ['GEN-EARLY', 'GEN-LATE']
    replay(store, chunks, targets)
    assert {row['id'] for row in conversations(store)} == before
    assert chunks[0]['transcript_segments'][0]['text'] in texts(store, 'GEN-EARLY')
    assert chunks[1]['transcript_segments'][0]['text'] in texts(store, 'GEN-LATE')
