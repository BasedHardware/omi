"""Independent source-frame capture proof for lexical WAL repeat drops.

``capture_covered_indices`` proves an incoming segment only when its own
``sync_vad`` receipt uniquely names a nonempty frame span AND the live row's
``origin=live`` snapshot positively covers every touched frame for the same
root, epoch, rate and mono channel. Anything missing, malformed, conflicting
or partial is unproven. All ids and evidence are synthetic.
"""

from utils.sync.capture_repeat_evidence import capture_covered_indices

ROOT = 'a1b2c3d4-1111-4222-8333-444455556666'
OTHER_ROOT = 'b2c3d4e5-2222-4333-8444-555566667777'
EPOCH = 7
RATE = 16000
SPF = 160


def receipt(segment_id, start_frame=0, end_frame=99, start_offset=0, end_offset=0, **over):
    value = {
        'segment_id': segment_id,
        'capture_root': ROOT,
        'clock_epoch': EPOCH,
        'channel': 'mono',
        'source_start_frame': start_frame,
        'source_start_offset': start_offset,
        'source_end_frame': end_frame,
        'source_end_offset': end_offset,
        'rate_hz': RATE,
        'producer_revision': 'sync_vad_stt_v1',
    }
    value.update(over)
    return value


def run(first=0, last=8000, **over):
    value = {
        'capture_root': ROOT,
        'clock_epoch': EPOCH,
        'rate_hz': RATE,
        'channel': 'mono',
        'source_frame_start': first,
        'source_frame_end': last,
        'decoded_sample_start': first * SPF,
        'decoded_sample_end': last * SPF,
        'samples_per_frame': SPF,
    }
    value.update(over)
    return value


def sync_evidence(receipts, **over):
    value = {
        'version': 1,
        'capability': 'source_position',
        'coverage': 'mapped',
        'origin': 'sync_vad',
        'receipts': receipts,
    }
    value.update(over)
    return value


def live_evidence(runs=None, **over):
    value = {
        'version': 1,
        'capability': 'source_position',
        'coverage': 'mapped',
        'origin': 'live',
        'conflicts': 0,
        'runs': [run()] if runs is None else runs,
    }
    value.update(over)
    return value


def segment(segment_id, **over):
    value = {'id': segment_id, 'text': 'synthetic words', 'start': 0.0, 'end': 9.0}
    value.update(over)
    return value


def covered(incoming, sync_env=None, live_env=None):
    return capture_covered_indices(
        incoming,
        sync_evidence([receipt(s['id']) for s in incoming]) if sync_env is None else sync_env,
        live_evidence() if live_env is None else live_env,
    )


def test_valid_receipt_and_full_live_coverage_still_proves_nothing():
    """A well-formed receipt pair alone is not proof; every index stays kept."""
    incoming = [segment('s0'), segment('s1'), segment('s2')]
    assert covered(incoming) == frozenset()


def test_no_evidence_or_wrong_envelope_never_proves():
    incoming = [segment('s0')]
    assert capture_covered_indices(incoming, None, live_evidence()) == frozenset()
    assert capture_covered_indices(incoming, sync_evidence([receipt('s0')]), None) == frozenset()
    for mutation in (
        {'version': 2},
        {'version': '1'},
        {'capability': 'stable_artifact'},
        {'origin': 'live'},
        {'coverage': 'unknown'},
        {'receipts': 'not-a-list'},
    ):
        env = sync_evidence([receipt('s0')])
        env.update(mutation)
        assert covered(incoming, sync_env=env) == frozenset(), mutation


def test_wrong_live_envelope_never_proves():
    incoming = [segment('s0')]
    for mutation in (
        {'origin': 'sync_vad'},
        {'origin': None},
        {'version': 2},
        {'capability': 'unknown'},
        {'coverage': 'unknown'},
        {'conflicts': 1},
        {'conflicts': '0'},
    ):
        assert covered(incoming, live_env=live_evidence(**mutation)) == frozenset(), mutation


def test_malformed_receipts_never_prove():
    cases = [
        {'capture_root': 'not-a-uuid'},
        {'capture_root': 42},
        {'clock_epoch': -1},
        {'clock_epoch': 1.5},
        {'rate_hz': 0},
        {'rate_hz': 8000.0},
        {'source_start_frame': -1},
        {'source_end_frame': -1},
        {'channel': 'stereo'},
        {'source_start_offset': -1},
        {'source_end_offset': -1},
    ]
    for over in cases:
        bad = receipt('s0', **over)
        incoming = [segment('s0')]
        assert covered(incoming, sync_env=sync_evidence([bad])) == frozenset(), over


def test_zero_length_receipt_never_proves():
    incoming = [segment('s0')]
    bad = receipt('s0', start_frame=10, end_frame=10, start_offset=0, end_offset=0)
    assert covered(incoming, sync_env=sync_evidence([bad])) == frozenset()
    bad = receipt('s0', start_frame=10, end_frame=10, start_offset=5, end_offset=5)
    assert covered(incoming, sync_env=sync_evidence([bad])) == frozenset()


def test_unmatched_and_duplicated_receipt_ids_never_prove():
    incoming = [segment('s0')]
    assert covered(incoming, sync_env=sync_evidence([receipt('other')])) == frozenset()
    dup = [receipt('s0'), receipt('s0')]
    assert covered(incoming, sync_env=sync_evidence(dup)) == frozenset()
    incoming = [segment('s0'), segment('s0')]
    both = [receipt('s0')]
    assert covered(incoming, sync_env=sync_evidence(both)) == frozenset()


def test_segment_without_id_is_unproven():
    incoming = [{'text': 'no id', 'start': 0.0, 'end': 1.0}]
    assert covered(incoming, sync_env=sync_evidence([receipt('anything')])) == frozenset()


def test_run_identity_mismatch_never_proves():
    incoming = [segment('s0')]
    for over in (
        {'capture_root': OTHER_ROOT},
        {'clock_epoch': EPOCH + 1},
        {'rate_hz': 8000},
        {'channel': 'stereo'},
    ):
        assert covered(incoming, live_env=live_evidence([run(**over)])) == frozenset(), over


def test_partial_coverage_never_proves():
    incoming = [segment('s0')]
    assert covered(incoming, live_env=live_evidence([run(first=0, last=50)])) == frozenset()
    assert covered(incoming, live_env=live_evidence([run(first=0, last=50), run(first=60, last=200)])) == frozenset()
    assert (
        covered(
            incoming,
            live_env=live_evidence([run(first=0, last=50), run(first=50, last=200, capture_root=OTHER_ROOT)]),
        )
        == frozenset()
    )


def test_exact_exclusive_and_positive_end_offsets_stay_unproven():
    incoming = [segment('s0')]
    env = sync_evidence([receipt('s0', start_frame=0, end_frame=99, end_offset=0)])
    assert covered(incoming, sync_env=env, live_env=live_evidence([run(first=0, last=99)])) == frozenset()
    env = sync_evidence([receipt('s0', start_frame=0, end_frame=99, end_offset=1)])
    assert covered(incoming, sync_env=env, live_env=live_evidence([run(first=0, last=99)])) == frozenset()
    assert covered(incoming, sync_env=env, live_env=live_evidence([run(first=0, last=100)])) == frozenset()
    env = sync_evidence([receipt('s0', start_frame=0, end_frame=99, end_offset=SPF)])
    assert covered(incoming, sync_env=env, live_env=live_evidence([run(first=0, last=100)])) == frozenset()
    env = sync_evidence([receipt('s0', start_frame=0, end_frame=100, end_offset=1)])
    assert covered(incoming, sync_env=env, live_env=live_evidence([run(first=0, last=100)])) == frozenset()


def test_out_of_bounds_offsets_never_prove():
    incoming = [segment('s0')]
    assert covered(incoming, sync_env=sync_evidence([receipt('s0', start_offset=SPF)])) == frozenset()
    assert covered(incoming, sync_env=sync_evidence([receipt('s0', end_offset=SPF + 1)])) == frozenset()


def test_receipt_cap_and_incoming_cap_bound_the_scan():
    incoming = [segment(f's{i}') for i in range(64)]
    env = sync_evidence([receipt(s['id']) for s in incoming])
    assert covered(incoming, sync_env=env) == frozenset()
    oversized = [segment(f's{i}') for i in range(65)]
    env = sync_evidence([receipt(s['id']) for s in oversized[:64]])
    assert covered(oversized, sync_env=env) == frozenset()
    too_many = [receipt('s0')] * 65
    assert covered([segment('s0')], sync_env=sync_evidence(too_many)) == frozenset()
