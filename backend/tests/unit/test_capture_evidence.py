"""Hermetic S1 identity, coverage, and unsupported-clock fixtures."""

import json

import pytest

from utils.capture_evidence import (
    Capability,
    CaptureRoot,
    DeliveryVerdict,
    EvidenceUnit,
    Span,
    Surface,
    Track,
    bounded_envelope,
    classify_delivery,
    coverage_union,
    digest,
    envelope,
    novel_coverage,
    unknown_envelope,
)


def track(uid='a', root='capture', channel='mono', epoch='0', rate=16000):
    return Track(CaptureRoot(uid, root, Surface('pendant', 'install-1', 'phone')), channel, epoch, rate, 'source_pcm')


def unit(t, unit_id, start, end, payload=b'a', kind='audio', revision='v1'):
    return EvidenceUnit(t, unit_id, kind, revision, Span(start, end), digest(payload))


def test_live_and_wal_different_batching_have_same_union_but_not_same_receipt():
    t = track()
    live = [unit(t, 'f0', 0, 16000), unit(t, 'f1', 16000, 32000)]
    wal = unit(t, 'wal-batch', 0, 32000)
    assert coverage_union(u.source_span for u in live) == (Span(0, 32000),)
    assert classify_delivery(wal, live) == (DeliveryVerdict.overlap, ())
    assert wal.identity not in {u.identity for u in live}


def test_truncated_tail_is_novel_and_gap_is_not_silently_filled():
    t = track()
    present = unit(t, 'prefix', 0, 20000)
    assert novel_coverage(Span(0, 32000), [present.source_span]) == (Span(20000, 32000),)
    assert coverage_union([Span(0, 16000), Span(20000, 32000)]) == (Span(0, 16000), Span(20000, 32000))


def test_restart_and_repeated_delivery_keep_source_identity():
    before = unit(track(), 'frame-7', 700, 800)
    after = unit(track(), 'frame-7', 700, 800)
    assert json.loads(json.dumps(envelope(before))) == envelope(after)
    assert classify_delivery(after, [before]) == (DeliveryVerdict.replay, ())


def test_changed_payload_or_range_under_same_version_is_conflict():
    original = unit(track(), 'frame-7', 700, 800)
    for revised in (unit(track(), 'frame-7', 700, 800, b'changed'), unit(track(), 'frame-7', 700, 801)):
        assert classify_delivery(revised, [original]) == (DeliveryVerdict.conflict, ())


def test_retranscription_is_an_attributable_alternative():
    t = track()
    live = unit(t, 'segment-1', 0, 8000, kind='transcript', revision='live')
    final = unit(t, 'segment-1', 0, 8000, b'better', kind='transcript', revision='final')
    assert classify_delivery(final, [live]) == (DeliveryVerdict.novel, (Span(0, 8000),))
    assert live.identity != final.identity


def test_wrap_and_rate_change_require_new_epoch():
    old = unit(track(epoch='0'), 'seq-0', 0, 100)
    wrapped = unit(track(epoch='1'), 'seq-0', 0, 100)
    rate_changed = unit(track(epoch='2', rate=48000), 'seq-0', 0, 100)
    assert old.identity != wrapped.identity != rate_changed.identity
    with pytest.raises(ValueError):
        track(rate=0)


def test_uploader_change_preserves_source_identity_and_unannounced_rate_change_conflicts():
    original = unit(track(), 'f0', 0, 100)
    uploader_changed = unit(
        Track(
            CaptureRoot('a', 'capture', Surface('pendant', 'install-1', 'other-phone')),
            'mono',
            '0',
            16000,
            'source_pcm',
        ),
        'f0',
        0,
        100,
    )
    rate_changed_without_epoch = unit(track(rate=48000), 'f0', 0, 100)
    assert classify_delivery(uploader_changed, [original])[0] == DeliveryVerdict.replay
    assert classify_delivery(rate_changed_without_epoch, [original])[0] == DeliveryVerdict.conflict


def test_clock_jump_does_not_change_key():
    sample = unit(track(), 'f0', 0, 16000)
    assert 'wall_time' not in envelope(sample)
    assert sample.identity == unit(track(), 'f0', 0, 16000).identity


def test_account_switch_and_cross_device_do_not_dedupe():
    source = unit(track(), 'f0', 0, 100)
    other_account = unit(track(uid='b'), 'f0', 0, 100)
    other_device = unit(
        Track(CaptureRoot('a', 'capture', Surface('desktop', 'install-1')), 'mono', '0', 16000, 'source_pcm'),
        'f0',
        0,
        100,
    )
    assert source.identity != other_account.identity
    assert source.identity != other_device.identity
    assert classify_delivery(other_account, [source])[0] == DeliveryVerdict.novel


def test_stereo_imbalance_has_independent_channel_coverage():
    left = unit(track(channel='left'), 'f0', 0, 16000)
    right = unit(track(channel='right'), 'f0', 0, 12000)
    assert classify_delivery(right, [left])[0] == DeliveryVerdict.novel
    assert unknown_envelope('multichannel_mix', origin='live')['coverage'] == 'unknown'


def test_overflow_abstains_instead_of_claiming_complete_coverage():
    sample = unit(track(), 'f0', 0, 100)
    assert bounded_envelope(envelope(sample))['capability'] == Capability.source_position.value
    assert bounded_envelope({'units': ['x' * 5000]})['coverage'] == 'incomplete'
    with pytest.raises(ValueError):
        Span(5, 5)
