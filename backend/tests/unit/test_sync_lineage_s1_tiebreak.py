"""S1 frame-evidence tiebreak for ambiguous overlapping lineage generations.

Several generations can strictly contain a segment when merges, discards and
back-dated intervals overlap. Under the safe-overlap gate the stamp picks only
among visible covering canonicals; failing the stamp, exactly one canonical
backed by a validated committed live run covering or exactly adjoining the
segment's source coordinates wins; failing that, exactly one visible canonical
wins; anything else stays ``ambiguous_pending``. All ids are synthetic.
"""

import math
from types import SimpleNamespace

import pytest

from config import sync_lineage
from tests.unit.test_sync_recording_lineage import ORIGIN, at
from utils.capture_evidence import SourcePositionMap
from utils.sync import recording_lineage
from utils.sync.lineage_frame_evidence import unique_committed_canonical
from utils.sync.recording_lineage import select_segment_targets

ROOT = 'a1b2c3d4-1111-4222-8333-444455556666'
OTHER_ROOT = '999e4567-e89b-12d3-a456-426614174999'
EPOCH = 7
RATE = 16000
SPF = 8000
T = 1760000000.0

CLAIM = {
    'capture_root': ROOT,
    'clock_epoch': EPOCH,
    'source_frame_start': 100,
    'frame_count': 10,
    'rate_hz': RATE,
    'codec': 'pcm16',
    'channel': 'mono',
}
OFFSETS = [i * SPF for i in range(11)]


@pytest.fixture(autouse=True)
def default_flag(monkeypatch):
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, raising=False)
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)


def committed_env(first, last, *, wall_first, spf=SPF, root=ROOT, epoch=EPOCH, rate=RATE):
    """Real committed proof: ordinals first..last-1 receipted, wall_first = wall at first's start."""
    source = SourcePositionMap(committed=True)
    ordinals = list(range(first, last))
    cursor = 0
    for ordinal in ordinals:
        source.accept(
            {'capture_root': root, 'clock_epoch': epoch, 'source_frame': ordinal},
            sample_start=cursor,
            sample_count=spf,
            rate_hz=rate,
            payload=b'\x02\x00' * min(spf, 2048),
            receipt_wall_time=wall_first + (ordinal - first + 1) * spf / rate,
        )
        cursor += spf
    source.remember_transcripts([{'id': 's0', '_capture_word_ranges': ((0, cursor),)}])
    return source.committed_snapshot(
        'conv', [SimpleNamespace(id='s0', text='live words', start=0.0, end=1.0, audio_alignment=None)]
    )


def row(row_id, start, end, evidence=None, **extra):
    base = {
        'id': row_id,
        'started_at': at(start),
        'finished_at': at(end),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'discarded': False,
        'status': 'completed',
        'external_data': {'recording_session_id': f'SESSION-{row_id}', 'recording_origin_id': ORIGIN},
        'transcript_segments': [],
    }
    if evidence is not None:
        base['capture_evidence'] = evidence
    base.update(extra)
    return base


def source_map(*, claim=None, offsets=None, derivative_start=0):
    frame_map = {'claim': claim or CLAIM, 'offsets': offsets if offsets is not None else OFFSETS, 'incomplete': False}
    return (frame_map, derivative_start)


def select(rows, *, stamp=None, maps=None, start=T, end=T + 5.0, **kwargs):
    return select_segment_targets(
        rows,
        ORIGIN,
        {'SEG': (start, end)},
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        segment_source_maps=maps if maps is not None else {'SEG': source_map()},
        **kwargs,
    )


def overlapping(evidence=None, back_evidence=None, disc_evidence=None):
    """A merged visible row plus a backdated visible row plus five discarded rows.

    The segment occupies source frames 100..110 across wall [T, T + 5]; every
    row strictly contains it."""
    rows = [
        row('GEN-MERGED', T - 1200, T + 1200, evidence=evidence, created_at=at(T - 1200)),
        row('GEN-BACK', T - 100, T + 300, evidence=back_evidence, created_at=at(T + 800)),
    ]
    for i in range(5):
        rows.append(
            row(
                f'GEN-DISC-{i}',
                T - 900 + i * 100,
                T + 100 + i * 200,
                discarded=True,
                evidence=disc_evidence if i == 2 else None,
            )
        )
    return rows


def test_covering_run_binds_the_proven_canonical():
    """Run frames 95..115 cover segment frames 100..110; wall at frame 95 = T - 2.5."""
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': 'GEN-BACK'}
    assert result.binding_reasons == {'SEG': 'bound'}


def test_exact_left_adjoining_run_binds():
    """Run frames 80..99 end exactly at the segment's first frame 100."""
    env = committed_env(80, 100, wall_first=T - 10.0)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': 'GEN-BACK'}


def test_exact_right_adjoining_run_binds():
    """Run frames 110..130 start exactly at the segment's last frame boundary."""
    env = committed_env(110, 130, wall_first=T + 5.0)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': 'GEN-BACK'}


def test_frame_gap_is_not_decisive():
    env = committed_env(80, 98, wall_first=T - 11.0)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_mere_partial_overlap_is_not_decisive():
    env = committed_env(105, 115, wall_first=T + 0.5)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_non_frame_aligned_boundary_is_not_adjacent():
    """The segment starts mid-frame, so a run ending at frame 100 adjoins nothing."""
    env = committed_env(80, 100, wall_first=T - 10.0)
    result = select(overlapping(back_evidence=env), maps={'SEG': source_map(derivative_start=4000)}, end=T + 4.75)
    assert result.targets == {'SEG': None}


def test_covering_partial_frames_allowed_with_geometry_and_clock():
    """Segment touches frames 100..110 with partial endpoints: map starts 4000
    samples into frame 100 and ends inside frame 109's successor boundary."""
    offsets = list(OFFSETS)
    env = committed_env(95, 115, wall_first=T - 2.5)
    maps = {'SEG': source_map(offsets=offsets, derivative_start=4000)}
    result = select(overlapping(back_evidence=env), maps=maps, start=T + 0.25, end=T + 5.0)
    assert result.targets == {'SEG': 'GEN-BACK'}


def test_nonuniform_touched_frame_geometry_abstains():
    """Frame 103 decodes one sample wider than the run's samples-per-frame."""
    offsets = list(OFFSETS)
    offsets[4] += 1
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), maps={'SEG': source_map(offsets=offsets)})
    assert result.targets == {'SEG': None}


@pytest.mark.parametrize(
    'mutate',
    [
        lambda env: env['runs'][0].update(rate_hz=RATE * 2),
        lambda env: env['runs'][0].update(capture_root=OTHER_ROOT),
        lambda env: env['runs'][0].update(clock_epoch=EPOCH + 1),
        lambda env: env['runs'][0].update(channel='stereo'),
    ],
    ids=['rate', 'root', 'epoch', 'channel'],
)
def test_mismatched_run_identity_never_decides(mutate):
    env = committed_env(95, 115, wall_first=T - 2.5)
    mutate(env)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': None}


@pytest.mark.parametrize('drift', [-2.5, 2.5, -86400.0])
def test_stale_wall_anchors_never_decide(drift):
    env = committed_env(95, 115, wall_first=T - 2.5 + drift)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': None}


def test_receipt_only_envelope_without_proof_never_decides():
    env = committed_env(95, 115, wall_first=T - 2.5)
    env.pop('proof')
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': None}


@pytest.mark.parametrize(
    'mutate',
    [
        lambda env: env['lifetime'].update(complete=False),
        lambda env: env['lifetime'].update(conflicts=1),
        lambda env: env.update(conflicts=2),
        lambda env: env['lifetime'].update(history=[]),
        lambda env: env['lifetime']['history'].append(dict(env['lifetime']['history'][0])),
    ],
    ids=['incomplete', 'lifetime-conflict', 'envelope-conflict', 'empty-history', 'duplicate-history'],
)
def test_incomplete_or_conflicting_history_never_decides(mutate):
    env = committed_env(95, 115, wall_first=T - 2.5)
    mutate(env)
    result = select(overlapping(back_evidence=env))
    assert result.targets == {'SEG': None}


def test_competing_same_root_lifetimes_abstain_everything():
    first = committed_env(95, 115, wall_first=T - 2.5)
    second = committed_env(95, 115, wall_first=T - 2.5 + 86400.0)
    result = select(overlapping(evidence=first, back_evidence=second))
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_two_supported_canonicals_stay_pending():
    env = committed_env(95, 115, wall_first=T - 2.5)
    other = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(evidence=env, back_evidence=other))
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_two_visible_rows_without_maps_stay_pending():
    result = select_segment_targets(
        overlapping(),
        ORIGIN,
        {'SEG': (T, T + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        segment_source_maps=None,
    )
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_visible_stamp_wins_ahead_of_contrary_frame_evidence():
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), stamp='GEN-MERGED')
    assert result.targets == {'SEG': 'GEN-MERGED'}


def test_hidden_stamp_cannot_win_against_visible_covering():
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), stamp='GEN-DISC-2')
    assert result.targets == {'SEG': 'GEN-BACK'}


def test_hidden_stamp_and_hidden_evidence_cannot_decide_visible_conflict():
    """A discarded row's stamp and committed proof both lose to two visible
    covering canonicals: the segment stays pending rather than going hidden."""
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(disc_evidence=env), stamp='GEN-DISC-2')
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_hidden_stamp_without_frame_evidence_binds_the_single_visible():
    rows = overlapping()[:1]
    for i in range(5):
        rows.append(row(f'GEN-DISC-{i}', T - 900 + i * 100, T + 100 + i * 200, discarded=True))
    result = select(rows, stamp='GEN-DISC-0')
    assert result.targets == {'SEG': 'GEN-MERGED'}


def test_single_visible_canonical_beats_discarded_only_rivals():
    rows = overlapping()[:1]
    for i in range(5):
        rows.append(row(f'GEN-DISC-{i}', T - 900 + i * 100, T + 100 + i * 200, discarded=True))
    result = select_segment_targets(
        rows,
        ORIGIN,
        {'SEG': (T, T + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        segment_source_maps=None,
    )
    assert result.targets == {'SEG': 'GEN-MERGED'}


def test_discarded_only_matches_keep_stamp_disambiguation():
    rows = [
        row('GEN-DISC-A', T - 100, T + 300, discarded=True),
        row('GEN-DISC-B', T - 200, T + 400, discarded=True),
    ]
    result = select(rows, stamp='GEN-DISC-B')
    assert result.targets == {'SEG': 'GEN-DISC-B'}


def test_discarded_only_unique_canonical_still_binds():
    """A single discarded covering row keeps the documented recoverable-show
    binding: with nothing visible competing, its own canonical is unique."""
    rows = [row('GEN-DISC-A', T - 100, T + 300, discarded=True)]
    result = select(rows)
    assert result.targets == {'SEG': 'GEN-DISC-A'}
    assert result.binding_reasons == {'SEG': 'bound'}


def test_discarded_only_conflicting_canonicals_stay_pending():
    rows = [
        row('GEN-DISC-A', T - 100, T + 300, discarded=True),
        row('GEN-DISC-B', T - 200, T + 400, discarded=True),
    ]
    result = select(rows)
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_donor_redirect_uses_the_survivor_visibility():
    donor = row(
        'GEN-DONOR',
        T - 100,
        T + 300,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-MERGED',
        smart_merge={'role': 'donor'},
    )
    rows = overlapping()[:1] + [donor]
    result = select_segment_targets(
        rows,
        ORIGIN,
        {'SEG': (T, T + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        segment_source_maps=None,
    )
    assert result.targets == {'SEG': 'GEN-MERGED'}


def test_donor_evidence_canonicalizes_to_the_survivor():
    """Committed proof stored on the donor row counts for its canonical
    survivor: with a competing visible row the segment still binds GEN-MERGED."""
    env = committed_env(95, 115, wall_first=T - 2.5)
    donor = row(
        'GEN-DONOR',
        T - 100,
        T + 300,
        evidence=env,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-MERGED',
        smart_merge={'role': 'donor'},
    )
    result = select(overlapping() + [donor])
    assert result.targets == {'SEG': 'GEN-MERGED'}
    assert result.binding_reasons == {'SEG': 'bound'}


def test_missing_canonical_establishes_no_visibility():
    donor = row(
        'GEN-DONOR',
        T - 100,
        T + 300,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-ABSENT',
        smart_merge={'role': 'donor'},
    )
    rows = overlapping()[:1] + [donor]
    result = select_segment_targets(
        rows,
        ORIGIN,
        {'SEG': (T, T + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        segment_source_maps=None,
    )
    assert result.targets == {'SEG': 'GEN-MERGED'}


def test_donor_only_match_binds_the_redirect_never_the_deleted_survivor():
    """A donor tombstone whose survivor is absent is the only match: the plan
    names the donor id so intake follows the redirect and supersedes the audio
    rather than recreating a deleted row."""
    donor = row(
        'GEN-DONOR',
        T - 100,
        T + 300,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-GONE',
        smart_merge={'role': 'donor'},
    )
    result = select([donor])
    assert result.targets == {'SEG': 'GEN-DONOR'}
    assert result.binding_reasons == {'SEG': 'bound'}


def test_strict_ambiguity_is_not_rescued_by_a_tolerant_only_row():
    """A tolerant-only generation overlapping the edge window with contrary
    proof cannot join a strict multi-canonical set's decision."""
    rows = overlapping(back_evidence=committed_env(95, 115, wall_first=T - 2.5))
    tolerant_only = row(
        'GEN-TOL',
        T + 4.0,
        T + 60,
        evidence=committed_env(110, 130, wall_first=T + 5.0),
    )
    result = select(rows + [tolerant_only], stamp='GEN-TOL')
    assert result.targets == {'SEG': 'GEN-BACK'}


def test_strict_ambiguity_with_tolerant_stamp_stays_pending():
    rows = overlapping()
    tolerant_only = row('GEN-TOL', T + 4.0, T + 60)
    result = select_segment_targets(
        rows + [tolerant_only],
        ORIGIN,
        {'SEG': (T, T + 5.0)},
        stamped_target='GEN-TOL',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


def test_unique_canonical_wins_before_any_tiebreak():
    """Two strict rows sharing one canonical are already unique; contrary
    evidence on a tolerant-only row is never consulted."""
    donor = row(
        'GEN-DONOR',
        T - 100,
        T + 300,
        deleted=True,
        discarded=True,
        sync_merged_into='GEN-MERGED',
        smart_merge={'role': 'donor'},
    )
    tolerant_only = row('GEN-TOL', T + 4.0, T + 60, evidence=committed_env(110, 130, wall_first=T + 5.0))
    rows = overlapping()[:1] + [donor, tolerant_only]
    result = select(rows)
    assert result.targets == {'SEG': 'GEN-MERGED'}
    assert result.binding_reasons == {'SEG': 'bound'}


def test_tolerant_multi_canonical_set_uses_frame_evidence():
    env = committed_env(95, 115, wall_first=T - 2.5)
    rows = [
        row('GEN-LEFT', T - 100, T + 2.0),
        row('GEN-RIGHT', T + 4.0, T + 60, evidence=env),
    ]
    result = select(rows)
    assert result.targets == {'SEG': 'GEN-RIGHT'}
    assert result.binding_reasons == {'SEG': 'bound'}


def test_truncated_lineage_read_never_resolves_on_frame_evidence():
    """A truncated overlap set proves no target even when a committed run
    would otherwise decide it."""
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), truncated_before=math.inf)
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'unbound'}


def test_safe_overlap_off_keeps_the_plain_miss():
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), safe_overlap=False)
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'unbound'}


def test_malformed_map_or_claim_never_raises():
    rows = overlapping(back_evidence=committed_env(95, 115, wall_first=T - 2.5))
    for bad_map in (
        None,
        ('x',),
        ({}, 0),
        ({'claim': CLAIM}, 0),
        ({'claim': CLAIM, 'offsets': [1] + OFFSETS[1:]}, 0),
        ({'claim': {**CLAIM, 'rate_hz': 'x'}}, 0),
        ({'claim': CLAIM, 'offsets': OFFSETS}, -1),
        ({'claim': CLAIM, 'offsets': OFFSETS}, True),
    ):
        result = select(rows, maps={'SEG': bad_map})
        assert result.targets == {'SEG': None}


@pytest.mark.parametrize(
    'bad_offsets',
    [
        [False] + OFFSETS[1:],
        [0.0] + OFFSETS[1:],
        [0, SPF, True] + OFFSETS[3:],
        [0, SPF, float(2 * SPF)] + OFFSETS[3:],
        OFFSETS[:-1] + [float(OFFSETS[-1])],
    ],
    ids=['first-bool', 'first-float', 'interior-bool', 'interior-float', 'last-float'],
)
def test_nonint_offsets_never_decide(bad_offsets):
    """Bool and float offsets are not integers: neither a zero-valued first
    element nor an interior derivative-zero variant can sneak through."""
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), maps={'SEG': source_map(offsets=bad_offsets)})
    assert result.targets == {'SEG': None}
    assert result.binding_reasons == {'SEG': 'ambiguous_pending'}


@pytest.mark.parametrize('derivative_start', [0.0, False, -1, OFFSETS[-1] + 1])
def test_nonint_or_out_of_range_derivative_start_never_decides(derivative_start):
    env = committed_env(95, 115, wall_first=T - 2.5)
    result = select(overlapping(back_evidence=env), maps={'SEG': source_map(derivative_start=derivative_start)})
    assert result.targets == {'SEG': None}


def test_helper_rejects_every_nondeciding_shape():
    matches = [SimpleNamespace(canonical='A', evidence={'runs': []})]
    good_map = source_map()
    for args in (
        (matches, T, T + 5.0, None),
        (matches, T, T + 5.0, ('x',)),
        (matches, float('nan'), T + 5.0, good_map),
        (matches, T, T - 1.0, good_map),
        (matches, T, T + 5.0, ({'claim': None, 'offsets': OFFSETS, 'incomplete': False}, 0)),
        (matches, T, T + 5.0, ({'claim': CLAIM, 'offsets': [0, 0] + OFFSETS[2:], 'incomplete': False}, 0)),
    ):
        assert unique_committed_canonical(*args) is None


def test_plan_rechecks_forward_the_source_maps(monkeypatch):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    seen_maps = []
    original = recording_lineage.resolve_segment_targets

    def spy(*args, **kwargs):
        seen_maps.append(kwargs.get('segment_source_maps'))
        return original(*args, **kwargs)

    monkeypatch.setattr(recording_lineage, 'resolve_segment_targets', spy)
    monkeypatch.setattr(recording_lineage, '_load_lineage', lambda *args, **kwargs: (list(overlapping()), None, False))
    maps = {'seg.wav': source_map()}
    targets = recording_lineage.plan_segment_targets(
        ['seg.wav'],
        lambda path: T,
        lambda path: 5.0,
        'u',
        ORIGIN,
        None,
        'omi',
        'pendant',
        False,
        'job-1',
        None,
        segment_source_maps=maps,
    )
    assert targets == {'seg.wav': None}
    assert len(seen_maps) == 3
    assert all(seen is maps for seen in seen_maps)


def test_resolver_requests_evidence_only_when_admitted(monkeypatch):
    """Projection is requested exactly when the evidence can decide, and the
    stored envelopes reach the selector only through that admitted read: the
    same rows still bind, stay pending or miss plain together with the flag."""
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    env = committed_env(95, 115, wall_first=T - 2.5)
    rows = overlapping(back_evidence=env)
    projections = []
    monkeypatch.setattr(
        recording_lineage,
        '_load_lineage',
        lambda *args, **kwargs: projections.append(kwargs.get('include_capture_evidence')) or (list(rows), None, False),
    )
    spans_map = {'seg.wav': (T, T + 5.0)}
    kwargs = dict(stamped_target=None, source='omi', client_device_id='pendant', is_locked=False, firestore_client=None)
    reasons = {}
    targets = recording_lineage.resolve_segment_targets(
        'u', ORIGIN, spans_map, segment_source_maps={'seg.wav': source_map()}, binding_reasons=reasons, **kwargs
    )
    assert projections == [True]
    assert targets == {'seg.wav': 'GEN-BACK'}
    assert reasons == {'seg.wav': 'bound'}
    reasons.clear()
    targets = recording_lineage.resolve_segment_targets(
        'u', ORIGIN, spans_map, segment_source_maps=None, binding_reasons=reasons, **kwargs
    )
    assert projections == [True, False]
    assert targets == {'seg.wav': None}
    assert reasons == {'seg.wav': 'ambiguous_pending'}
    reasons.clear()
    targets = recording_lineage.resolve_segment_targets(
        'u', ORIGIN, spans_map, segment_source_maps={'seg.wav': None}, binding_reasons=reasons, **kwargs
    )
    assert projections == [True, False, False]
    assert targets == {'seg.wav': None}
    assert reasons == {'seg.wav': 'ambiguous_pending'}
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'false')
    reasons.clear()
    targets = recording_lineage.resolve_segment_targets(
        'u', ORIGIN, spans_map, segment_source_maps={'seg.wav': source_map()}, binding_reasons=reasons, **kwargs
    )
    assert projections == [True, False, False, False]
    assert targets == {'seg.wav': None}
    assert reasons == {'seg.wav': 'ambiguous_pending'}
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'off')
    reasons.clear()
    targets = recording_lineage.resolve_segment_targets(
        'u', ORIGIN, spans_map, segment_source_maps={'seg.wav': source_map()}, binding_reasons=reasons, **kwargs
    )
    assert projections == [True, False, False, False, False]
    assert targets == {'seg.wav': None}
    assert reasons == {'seg.wav': 'unbound'}


def test_resolver_stub_rows_carrying_evidence_still_need_the_gate(monkeypatch):
    """A resolver-side stub that returns fully evidenced rows despite
    ``include_capture_evidence=False`` proves the gate is explicit: with dark
    write off the maps never reach the selector and two visible rows stay
    pending — the evidence cannot decide through the projection alone."""
    monkeypatch.delenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', raising=False)
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    env = committed_env(95, 115, wall_first=T - 2.5)
    rows = overlapping(back_evidence=env)
    projections = []
    monkeypatch.setattr(
        recording_lineage,
        '_load_lineage',
        lambda *args, **kwargs: projections.append(kwargs.get('include_capture_evidence')) or (list(rows), None, False),
    )
    reasons = {}
    targets = recording_lineage.resolve_segment_targets(
        'u',
        ORIGIN,
        {'seg.wav': (T, T + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        firestore_client=None,
        binding_reasons=reasons,
        segment_source_maps={'seg.wav': source_map()},
    )
    assert projections == [False]
    assert targets == {'seg.wav': None}
    assert reasons == {'seg.wav': 'ambiguous_pending'}


def test_resolver_outside_uid_cohort_neither_projects_nor_uses_evidence(monkeypatch):
    """Outside the dedupe allowlist the resolver keeps the pre-gate path: no
    evidence projection and no map input even when every row is evidenced."""
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid')
    env = committed_env(95, 115, wall_first=T - 2.5)
    rows = overlapping(back_evidence=env)
    projections = []
    monkeypatch.setattr(
        recording_lineage,
        '_load_lineage',
        lambda *args, **kwargs: projections.append(kwargs.get('include_capture_evidence')) or (list(rows), None, False),
    )
    reasons = {}
    targets = recording_lineage.resolve_segment_targets(
        'u',
        ORIGIN,
        {'seg.wav': (T, T + 5.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        firestore_client=None,
        binding_reasons=reasons,
        segment_source_maps={'seg.wav': source_map()},
    )
    assert projections == [False]
    assert targets == {'seg.wav': None}
    assert reasons == {'seg.wav': 'unbound'}
