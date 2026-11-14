"""Containment refuses any donor speech the target did not capture.

The reviewed predicate applied its tolerance outward, so a donor could hold up
to twice the tolerance of speech outside the target and still be absorbed. The
donor then becomes a tombstone and that speech is lost. These proofs pin the
inward-only contract: tolerance tightens the target window and never loosens
it, and the donor span is never shrunk.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from utils.conversations.recorded_time import conversation_span, segment_span
from utils.sync.live_overlap import span_contained

ORIGIN = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

# L7b wires the configured tolerance in config/sync_bridge_containment.py. The
# matrix pins zero and the reviewed 0.5 s so a stricter setting can only refuse
# more.
TOLERANCES = {
    'zero': 0.0,
    'reviewed': 0.5,
}


def placed(start: float, end: float, *, alignment: str | None = None) -> dict:
    segment = {'start': start, 'end': end}
    if alignment is not None:
        segment['audio_alignment'] = alignment
    return segment


def row(*segments: dict, started_at: datetime | None = ORIGIN, **extra) -> dict:
    return {'started_at': started_at, 'transcript_segments': list(segments), **extra}


def target() -> dict:
    return row(placed(0.0, 20.0))


@pytest.mark.parametrize('tolerance', TOLERANCES.values(), ids=TOLERANCES.keys())
def test_donor_with_extra_leading_speech_is_refused(tolerance):
    # 0.4 s of donor speech starts before the target ever captured audio.
    donor = row(placed(-0.4, 10.0))
    assert not span_contained(donor, target(), tolerance_seconds=tolerance)


@pytest.mark.parametrize('tolerance', TOLERANCES.values(), ids=TOLERANCES.keys())
def test_donor_with_extra_trailing_speech_is_refused(tolerance):
    # 0.4 s of donor speech ends after the target stopped capturing.
    donor = row(placed(0.0, 20.4))
    assert not span_contained(donor, target(), tolerance_seconds=tolerance)


def test_outward_tolerance_would_have_passed_but_inward_refuses():
    # The reviewed predicate accepted this donor at 0.5 s on both sides, losing
    # up to 1.0 s of speech. The inward contract refuses it at every setting.
    donor = row(placed(-0.4, 20.4))
    for tolerance in TOLERANCES.values():
        assert not span_contained(donor, target(), tolerance_seconds=tolerance)


def test_donor_equal_to_the_target_boundaries_is_accepted_at_zero_tolerance():
    donor = row(placed(0.0, 20.0))
    assert span_contained(donor, target(), tolerance_seconds=0.0)


@pytest.mark.parametrize('tolerance', [0.5, 1.0])
def test_donor_equal_to_the_target_boundaries_is_refused_once_tolerance_tightens(tolerance):
    # Tolerance tightens the target, so an exact boundary match no longer fits.
    donor = row(placed(0.0, 20.0))
    assert not span_contained(donor, target(), tolerance_seconds=tolerance)


@pytest.mark.parametrize('tolerance', TOLERANCES.values(), ids=TOLERANCES.keys())
def test_donor_strictly_inside_is_accepted(tolerance):
    donor = row(placed(1.0, 19.0))
    assert span_contained(donor, target(), tolerance_seconds=tolerance)


def test_tolerance_wider_than_the_target_interval_refuses():
    # A 0.4 s target cannot survive a 0.5 s inward tolerance on both sides. The
    # tightened window inverts, so the final comparison cannot hold; this is a
    # shape case, not coverage of a separate guard.
    narrow = row(placed(0.0, 0.4))
    donor = row(placed(0.1, 0.3))
    assert not span_contained(donor, narrow, tolerance_seconds=0.5)


@pytest.mark.parametrize('tolerance', [float('inf'), float('-inf'), float('nan'), 1e12, -1.0])
def test_malformed_tolerance_resolves_strict_without_raising(tolerance):
    # A malformed config value must refuse, not crash the caller. Resolving to
    # zero keeps the equal-boundary donor accepted and the outside donor refused.
    assert span_contained(row(placed(0.0, 20.0)), target(), tolerance_seconds=tolerance)
    assert not span_contained(row(placed(-0.4, 10.0)), target(), tolerance_seconds=tolerance)


@pytest.mark.parametrize(
    'tolerance',
    [10**1000, -(10**1000), Decimal('1e1000')],
    ids=['huge-int', 'huge-negative-int', 'huge-decimal'],
)
def test_float_overflow_tolerance_resolves_strict_without_raising(tolerance):
    # float() raises OverflowError for a finite value too large to represent.
    # That is malformed config, not an authorization to widen: it must resolve
    # strict (0) and let the containment comparison refuse, never escape.
    assert span_contained(row(placed(0.0, 20.0)), target(), tolerance_seconds=tolerance)
    assert not span_contained(row(placed(-0.4, 10.0)), target(), tolerance_seconds=tolerance)


def test_tolerance_near_datetime_max_does_not_overflow():
    # The clamp to half the target width keeps the subtraction in range even
    # when the target ends at the datetime ceiling.
    near_max = datetime.max.replace(tzinfo=timezone.utc) - timedelta(seconds=10)
    target_row = row(placed(0.0, 10.0), started_at=near_max)
    donor = row(placed(1.0, 9.0), started_at=near_max)
    assert span_contained(donor, target_row, tolerance_seconds=1e12)
    assert not span_contained(donor, target_row, tolerance_seconds=5.0)


def test_donor_with_unplaced_speech_is_refused():
    # The placed extent is inside the target, but the unplaced segment has no
    # proven position, so the donor's whole speech cannot be shown contained.
    donor = row(placed(0.0, 20.0), placed(90.0, 95.0, alignment='unplaced'))
    assert segment_span(donor) == (ORIGIN, ORIGIN + timedelta(seconds=20))
    assert not span_contained(donor, target(), tolerance_seconds=0.0)


def test_wall_clock_envelope_only_is_refused():
    # conversation_span derives a finished_at envelope, but no placed segment
    # proves the target captured the donor's speech.
    donor = row(finished_at=ORIGIN + timedelta(seconds=20))
    assert conversation_span(donor) is not None
    assert segment_span(donor) is None
    assert not span_contained(donor, target(), tolerance_seconds=0.5)


def test_missing_or_invalid_span_is_refused():
    assert not span_contained({}, target())
    assert not span_contained(row(), target())
    assert not span_contained(row(placed(5.0, 5.0)), target())
    assert not span_contained(row(placed(6.0, 5.0)), target())
    assert not span_contained(row(placed(float('nan'), 5.0)), target())
    assert not span_contained(row(placed(0.0, 20.0), started_at=None), target())


def test_unplaced_segments_do_not_prove_a_span():
    donor = row(placed(0.0, 20.0, alignment='unplaced'))
    assert segment_span(donor) is None
    assert not span_contained(donor, target())


def test_segment_span_uses_placed_segment_extent_not_the_envelope():
    donor = row(placed(2.0, 4.0), placed(6.0, 8.0), finished_at=ORIGIN + timedelta(seconds=20))
    assert segment_span(donor) == (ORIGIN + timedelta(seconds=2), ORIGIN + timedelta(seconds=8))


def test_choose_live_overlap_can_stay_side_effect_inert(monkeypatch):
    from utils.sync import live_overlap

    calls = []
    monkeypatch.setattr(live_overlap.refactor_modes, 'shadow_or_serve', lambda _: True)
    monkeypatch.setattr(live_overlap.refactor_modes, 'serving_for', lambda *_: False)
    monkeypatch.setattr(live_overlap, 'compare', lambda *args: calls.append(args))

    assert live_overlap.choose_live_overlap([], {}, record_comparison=False) is None
    assert calls == []
    assert live_overlap.choose_live_overlap([], {}) is None
    assert calls == [('live_bind', 'agree')]
