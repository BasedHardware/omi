"""Pure tests for the committed-only WAL coverage validator.

Fixtures come from the real producer (SourcePositionMap + CommittedCaptureMap)
so every valid envelope is one the live path can actually emit; adversarial
cases mutate copies of that real shape. Wall anchors follow the producer's
frame-end convention: receipt_wall = WAV_start + (i + 1) * frame_duration.
"""

import copy
import math
from types import SimpleNamespace

import pytest

from utils.capture_evidence import SourcePositionMap
import utils.sync.committed_coverage as committed
from utils.sync.committed_coverage import validated_committed_ranges
from utils.sync.audio_coverage import validated_live_ranges

ROOT = '123e4567-e89b-12d3-a456-426614174000'
OTHER_ROOT = '999e4567-e89b-12d3-a456-426614174999'
EPOCH = 7
RATE = 16000
SPF = 8000
WAV_START = 1760000000.0

CLAIM = {
    'capture_root': ROOT,
    'clock_epoch': EPOCH,
    'source_frame_start': 0,
    'frame_count': 10,
    'rate_hz': RATE,
    'codec': 'pcm16',
    'channel': 'mono',
}

FRAMES = [SPF] * 10


def _envelope(
    covered=range(8),
    *,
    feed=None,
    wall0=WAV_START,
    spf=SPF,
    root=ROOT,
    epoch=EPOCH,
    rate=RATE,
):
    """Real committed proof: ordinals `covered` committed out of `feed` received."""
    fed = list(range(max(covered) + 1)) if feed is None else list(feed)
    covered_set = set(covered)
    sample_cursor = 0
    notes = []
    note_start = None
    source = SourcePositionMap(committed=True)
    for ordinal in fed:
        source.accept(
            {'capture_root': root, 'clock_epoch': epoch, 'source_frame': ordinal},
            sample_start=sample_cursor,
            sample_count=spf,
            rate_hz=rate,
            payload=b'\x01\x00' * min(spf, 4096),
            receipt_wall_time=wall0 + (ordinal + 1) * spf / rate,
        )
        if ordinal in covered_set:
            if note_start is None:
                note_start = sample_cursor
            note_end = sample_cursor + spf
        elif note_start is not None:
            notes.append((note_start, note_end))
            note_start = None
        sample_cursor += spf
    if note_start is not None:
        notes.append((note_start, note_end))
    source.remember_transcripts(
        [{'id': f's{i}', '_capture_word_ranges': ((start, end),)} for i, (start, end) in enumerate(notes)]
    )
    segments = [
        SimpleNamespace(id=f's{i}', text='x', start=0.0, end=1.0, audio_alignment=None) for i in range(len(notes))
    ]
    return source.committed_snapshot('conv', segments)


def _ranges(env, *, wall=WAV_START, frames=FRAMES, claim=CLAIM):
    return validated_committed_ranges(
        claim, [env] if env is not None else [], wal_start_seconds=wall, frame_samples=frames
    )


def test_committed_run_yields_positive_ranges():
    env = _envelope(range(8))
    assert _ranges(env) == ((0, 8),)


def test_committed_hole_keeps_two_ranges():
    env = _envelope(range(3, 7))
    assert _ranges(env) == ((3, 7),)


def test_ranges_clipped_to_wal_domain():
    env = _envelope(range(8, 15), feed=range(15))
    claim = {**CLAIM, 'frame_count': 10}
    assert _ranges(env, claim=claim) == ((8, 10),)


def test_no_context_yields_no_positive_ranges():
    env = _envelope(range(8))
    assert validated_committed_ranges(CLAIM, [env], wal_start_seconds=None, frame_samples=None) == ()
    assert validated_committed_ranges(CLAIM, [env], wal_start_seconds=WAV_START, frame_samples=None) == ()
    assert validated_committed_ranges(CLAIM, [env], wal_start_seconds=None, frame_samples=FRAMES) == ()
    assert validated_live_ranges(CLAIM, [env]) == ()


def test_validated_live_ranges_delegates_with_context():
    env = _envelope(range(8))
    assert validated_live_ranges(CLAIM, [env], wal_start_seconds=WAV_START, frame_samples=FRAMES) == ((0, 8),)


def test_receipt_only_envelope_yields_no_ranges():
    receipt = {
        'version': 1,
        'capability': 'source_position',
        'origin': 'live',
        'coverage': 'mapped',
        'conflicts': 0,
        'runs': [
            {
                'capture_root': ROOT,
                'clock_epoch': EPOCH,
                'source_frame_start': 0,
                'source_frame_end': 8,
                'decoded_sample_start': 0,
                'decoded_sample_end': 8 * SPF,
                'samples_per_frame': SPF,
                'rate_hz': RATE,
                'channel': 'mono',
            }
        ],
    }
    assert _ranges(receipt) == ()
    assert validated_live_ranges(CLAIM, [receipt], wal_start_seconds=WAV_START, frame_samples=FRAMES) == ()


@pytest.mark.parametrize('skew', [-2.0, 2.0])
def test_exact_skew_boundary_still_proves(skew):
    env = _envelope(range(8), wall0=WAV_START + skew)
    assert _ranges(env) == ((0, 8),)


@pytest.mark.parametrize('skew', [-2.000001, 2.000001, 86400.0])
def test_beyond_skew_abstains_whole_batch(skew):
    env = _envelope(range(8), wall0=WAV_START + skew)
    assert _ranges(env) is None


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1.0, 0.0, True, 'x'])
def test_malformed_wall_anchor_abstains(bad):
    env = _envelope(range(8))
    env['runs'][0]['receipt_wall_start'] = bad
    assert _ranges(env) is None
    env = _envelope(range(8))
    env['runs'][0]['receipt_wall_end'] = bad
    assert _ranges(env) is None


def test_missing_history_entry_for_run_abstains():
    env = _envelope(range(8))
    env['lifetime']['history'] = [entry for entry in env['lifetime']['history'] if entry['capture_root'] != ROOT]
    assert _ranges(env) is None


def test_history_not_containing_run_abstains():
    env = _envelope(range(8))
    env['lifetime']['history'][0]['source_frame_end'] = 5
    assert _ranges(env) is None


def test_history_not_containing_receipt_window_abstains():
    env = _envelope(range(8))
    env['lifetime']['history'][0]['receipt_wall_end'] = WAV_START + 1.0
    assert _ranges(env) is None


def test_empty_and_overflow_history_abstain():
    env = _envelope(range(8))
    env['lifetime']['history'] = []
    assert _ranges(env) is None
    env = _envelope(range(8))
    entry = env['lifetime']['history'][0]
    env['lifetime']['history'] = [dict(entry, capture_root=f'{i:08d}-0000-0000-0000-000000000000') for i in range(17)]
    assert _ranges(env) is None


def test_duplicate_history_key_abstains():
    env = _envelope(range(8))
    env['lifetime']['history'].append(dict(env['lifetime']['history'][0]))
    assert _ranges(env) is None


def test_incomplete_lifetime_abstains():
    env = _envelope(range(8))
    env['lifetime']['complete'] = False
    assert _ranges(env) is None
    env = _envelope(range(8))
    env['lifetime']['conflicts'] = 1
    assert _ranges(env) is None
    env = _envelope(range(8))
    env['lifetime']['version'] = 2
    assert _ranges(env) is None
    env = _envelope(range(8))
    env['conflicts'] = 1
    assert _ranges(env) is None


def test_competing_lifetimes_cannot_pool():
    first = _envelope(range(8), wall0=WAV_START)
    second = _envelope(range(8), wall0=WAV_START + 86400.0)
    assert validated_committed_ranges(CLAIM, [first, second], wal_start_seconds=WAV_START, frame_samples=FRAMES) is None
    assert validated_committed_ranges(CLAIM, [second, first], wal_start_seconds=WAV_START, frame_samples=FRAMES) is None


def test_stale_reused_root_proof_rejected():
    env = _envelope(range(8), wall0=WAV_START - 86400.0)
    assert _ranges(env) is None


def test_variable_frame_geometry_abstains():
    env = _envelope(range(8))
    frames = [SPF] * 5 + [SPF - 1] + [SPF] * 4
    assert _ranges(env, frames=frames) is None


def test_malformed_frame_samples_abstain():
    env = _envelope(range(8))
    assert _ranges(env, frames=[SPF] * 9 + [0]) is None
    assert _ranges(env, frames=[SPF] * 9 + [True]) is None
    assert _ranges(env, frames=[SPF] * 9 + [-5]) is None
    assert _ranges(env, frames=[SPF] * 11) is None


def test_malformed_wal_start_abstains():
    env = _envelope(range(8))
    assert _ranges(env, wall=float('nan')) is None
    assert _ranges(env, wall=True) is None
    assert _ranges(env, wall='soon') is None
    assert _ranges(env, wall=-1) is None
    assert _ranges(env, wall=0) is None


def test_matching_envelope_wrong_proof_abstains():
    env = _envelope(range(8))
    env['proof'] = 'receipt_v1'
    assert _ranges(env) is None


def test_matching_envelope_bad_shape_abstains():
    for mutate in (
        lambda e: e.update(version=2),
        lambda e: e.update(capability='other'),
        lambda e: e.update(origin='sync'),
        lambda e: e.update(coverage='unknown'),
        lambda e: e.update(conflicts=True),
        lambda e: e.pop('lifetime'),
    ):
        env = _envelope(range(8))
        mutate(env)
        assert _ranges(env) is None


def test_malformed_matching_run_abstains():
    env = _envelope(range(8))
    env['runs'][0]['decoded_sample_end'] = 999
    assert _ranges(env) is None
    env = _envelope(range(8))
    env['runs'][0]['source_frame_start'] = True
    assert _ranges(env) is None


def test_run_duration_cap_abstains():
    env = _envelope(range(8))
    run = env['runs'][0]
    run['source_frame_end'] = 70
    run['decoded_sample_end'] = 70 * SPF
    run['receipt_wall_end'] = run['receipt_wall_start'] + 35.0
    env['lifetime']['history'][0]['source_frame_end'] = 70
    env['lifetime']['history'][0]['receipt_wall_end'] = run['receipt_wall_end']
    claim = {**CLAIM, 'frame_count': 70}
    assert _ranges(env, frames=[SPF] * 70, claim=claim) is None


def test_other_root_proof_is_irrelevant():
    env = _envelope(range(8), root=OTHER_ROOT)
    assert _ranges(env) == ()
    other_claim = {**CLAIM, 'capture_root': OTHER_ROOT}
    assert validated_committed_ranges(other_claim, [env], wal_start_seconds=WAV_START, frame_samples=FRAMES) == (
        (0, 8),
    )


def test_ordinal_gaps_and_new_speech_stay_unproven():
    env = _envelope(range(0, 5))
    assert _ranges(env) == ((0, 5),)
    env = _envelope([0, 1, 2, 6, 7, 8, 9])
    got = _ranges(env)
    assert got == ((0, 3), (6, 10))


def test_public_ranges_still_abstain_on_legacy_malformed():
    bad_claim = {**CLAIM, 'codec': 'aac'}
    assert validated_live_ranges(bad_claim, [], wal_start_seconds=WAV_START, frame_samples=FRAMES) is None
    conflicted = _envelope(range(8))
    conflicted['conflicts'] = 1
    assert validated_live_ranges(CLAIM, [conflicted], wal_start_seconds=WAV_START, frame_samples=FRAMES) is None


def test_uniform_span_index_prepared_once_at_max_bound(monkeypatch):
    """360000 alternating-size frames: the bisect index is built once, then
    reused for every validated run instead of rebuilt per run."""
    frame_count = committed.MAX_DECODED_FRAMES
    alt = SPF // 2
    frames = [SPF, SPF, alt, alt] * (frame_count // 4)
    offsets = [0]
    for size in frames:
        offsets.append(offsets[-1] + size)

    def run(start, spf):
        wall_start = WAV_START + offsets[start] / RATE
        return {
            'capture_root': ROOT,
            'clock_epoch': EPOCH,
            'source_frame_start': start,
            'source_frame_end': start + 2,
            'decoded_sample_start': offsets[start],
            'decoded_sample_end': offsets[start] + 2 * spf,
            'samples_per_frame': spf,
            'rate_hz': RATE,
            'channel': 'mono',
            'receipt_wall_start': wall_start,
            'receipt_wall_end': wall_start + 2 * spf / RATE,
        }

    env = {
        'proof': 'committed_transcript_v1',
        'version': 1,
        'capability': 'source_position',
        'origin': 'live',
        'coverage': 'mapped',
        'conflicts': 0,
        'lifetime': {
            'version': 1,
            'complete': True,
            'conflicts': 0,
            'history': [
                {
                    'capture_root': ROOT,
                    'clock_epoch': EPOCH,
                    'source_frame_start': 0,
                    'source_frame_end': frame_count,
                    'rate_hz': RATE,
                    'receipt_wall_start': WAV_START,
                    'receipt_wall_end': WAV_START + offsets[-1] / RATE,
                }
            ],
        },
        'runs': [run(frame_count - 4, SPF), run(frame_count - 2, alt)],
    }
    claim = {**CLAIM, 'frame_count': frame_count}
    seen_starts = []
    real_check = committed._span_covers_uniform

    def spy(spans, span_starts, lo, hi, spf):
        seen_starts.append(span_starts)
        return real_check(spans, span_starts, lo, hi, spf)

    monkeypatch.setattr(committed, '_span_covers_uniform', spy)
    got = validated_committed_ranges(claim, [env], wal_start_seconds=WAV_START, frame_samples=frames)
    assert got == ((frame_count - 4, frame_count),)
    assert len(seen_starts) == 2
    assert seen_starts[0] is seen_starts[1]
    assert len(seen_starts[0]) == frame_count // 2
