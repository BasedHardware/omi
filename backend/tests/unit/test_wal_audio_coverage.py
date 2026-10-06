"""Tests for the WAL source-frame audio coverage planner and WAV splitter."""

import os
import wave

import pytest

from utils.sync.audio_coverage import (
    _validated_received_ranges,
    plan_unreceived_frames,
    validated_live_ranges,
)
from utils.sync.wal_audio_coverage import apply_wal_audio_coverage, build_sync_source_frame_maps

ROOT = '123e4567-e89b-12d3-a456-426614174000'
EPOCH = 7
RATE = 16000

CLAIM = {
    'capture_root': ROOT,
    'clock_epoch': EPOCH,
    'source_frame_start': 0,
    'frame_count': 10,
    'rate_hz': RATE,
    'codec': 'pcm16',
    'channel': 'mono',
}


def _run(
    start,
    end,
    *,
    root=ROOT,
    epoch=EPOCH,
    rate=RATE,
    channel='mono',
    samples_per_frame=16000,
    decoded_start=None,
    decoded_end=None,
):
    ds = 0 if decoded_start is None else decoded_start
    de = (end - start) * samples_per_frame if decoded_end is None else decoded_end
    return {
        'capture_root': root,
        'clock_epoch': epoch,
        'source_frame_start': start,
        'source_frame_end': end,
        'decoded_sample_start': ds,
        'decoded_sample_end': de,
        'samples_per_frame': samples_per_frame,
        'rate_hz': rate,
        'channel': channel,
    }


def _envelope(runs, *, coverage='mapped', origin='live', conflicts=0, capability='source_position', version=1):
    return {
        'version': version,
        'capability': capability,
        'coverage': coverage,
        'origin': origin,
        'conflicts': conflicts,
        'runs': runs,
    }


def _write_wav(path, frames, *, rate=RATE):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for value, count in frames:
            wav.writeframes(int(value).to_bytes(2, 'little', signed=True) * count)


def _read_wav(path):
    with wave.open(str(path), 'rb') as wav:
        return wav.getframerate(), wav.readframes(wav.getnframes())


def _frame_bytes(value, count):
    return int(value).to_bytes(2, 'little', signed=True) * count


def test_plan_tail_received_keeps_new_speech():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(0, 7)], context_seconds=0) == ((7, 10),)


def test_plan_prelive_and_missed_kept_separately():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(3, 7)], context_seconds=0) == (
        (0, 3),
        (7, 10),
    )


def test_plan_duplicate_overlapping_received_union():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(0, 5), (3, 7), (4, 6)], context_seconds=0) == ((7, 10),)


def test_plan_received_outside_domain_is_clipped():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(9, 99)], context_seconds=0) == ((0, 9),)
    assert plan_unreceived_frames(samples, [(20, 30)], context_seconds=0) == ((0, 10),)


def test_plan_rejects_negative_or_reversed_received():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(-5, 4)]) is None
    assert plan_unreceived_frames(samples, [(5, 3)]) is None
    assert plan_unreceived_frames(samples, [(4, 4)]) is None


def test_plan_all_covered_returns_empty():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(0, 10)], context_seconds=0) == ()


def test_plan_no_evidence_keeps_everything():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [], context_seconds=0) == ((0, 10),)


def test_plan_variable_frames_exact_boundaries():
    samples = [100, 16000, 50, 16000, 200] * 2
    assert plan_unreceived_frames(samples, [(0, 6)], context_seconds=0) == ((6, 10),)


def test_plan_gaps_never_collapsed():
    samples = [16000] * 12
    assert plan_unreceived_frames(samples, [(3, 9)], context_seconds=0) == (
        (0, 3),
        (9, 12),
    )


def test_plan_context_zero_when_next_frame_exceeds_budget():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(3, 7)], context_seconds=0.25) == (
        (0, 3),
        (7, 10),
    )


def test_plan_context_bounded_by_budget_inside_covered_run():
    samples = [1000] * 20
    assert plan_unreceived_frames(samples, [(5, 15)], context_seconds=0.25) == ((0, 9), (11, 20))


def test_plan_context_adds_bounded_covered_neighbors():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(3, 7)]) == ((0, 3), (7, 10))
    small = [2000] * 10
    assert plan_unreceived_frames(small, [(3, 7)], context_seconds=0.25) == ((0, 10),)


def test_plan_context_merges_when_small_hole_bridged():
    small = [2000] * 10
    assert plan_unreceived_frames(small, [(4, 5)], context_seconds=0.25) == ((0, 10),)


def test_plan_context_budget_floor_and_whole_frames():
    samples = [3000] * 10
    assert plan_unreceived_frames(samples, [(2, 8)], context_seconds=0.25) == ((0, 3), (7, 10))


def test_plan_rejects_bool_and_float_samples():
    assert plan_unreceived_frames([16000, True, 16000], [(0, 1)]) is None
    assert plan_unreceived_frames([16000.0] * 3, [(0, 1)]) is None
    assert plan_unreceived_frames([0, 16000], [(0, 1)]) is None
    assert plan_unreceived_frames([-16000, 16000], [(0, 1)]) is None
    assert plan_unreceived_frames([], [(0, 1)]) is None


def test_plan_rejects_malformed_received_ranges():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(0, True)]) is None
    assert plan_unreceived_frames(samples, [(0.5, 4)]) is None
    assert plan_unreceived_frames(samples, [(0, float('nan'))]) is None
    assert plan_unreceived_frames(samples, [('a', 'b')]) is None
    assert plan_unreceived_frames(samples, [(0,)]) is None


def test_plan_rejects_bad_scalars():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(0, 7)], frame_start=-1) is None
    assert plan_unreceived_frames(samples, [(0, 7)], frame_start=True) is None
    assert plan_unreceived_frames(samples, [(0, 7)], sample_rate=0) is None
    assert plan_unreceived_frames(samples, [(0, 7)], context_seconds=-0.1) is None
    assert plan_unreceived_frames(samples, [(0, 7)], context_seconds=0.26) is None
    assert plan_unreceived_frames(samples, [(0, 7)], context_seconds=float('nan')) is None
    assert plan_unreceived_frames(samples, [(0, 7)], context_seconds=float('inf')) is None


def test_plan_caps():
    assert plan_unreceived_frames([16000] * (360000 + 1), [(0, 1)]) is None
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(i, i + 1) for i in range(33)]) is None
    hole_samples = [16000] * 65
    received = [(i, i + 1) for i in range(1, 64, 2)]
    assert plan_unreceived_frames(hole_samples, received, context_seconds=0) is None


def test_plan_frame_start_offsets_output():
    samples = [16000] * 10
    assert plan_unreceived_frames(samples, [(5, 12)], frame_start=5, context_seconds=0) == ((12, 15),)


def test_ranges_positive_runs():
    env = _envelope([_run(0, 7)])
    assert _validated_received_ranges(CLAIM, [env]) == ((0, 7),)


def test_ranges_merges_overlapping_runs():
    env = _envelope([_run(0, 5), _run(3, 7)])
    assert _validated_received_ranges(CLAIM, [env]) == ((0, 7),)


def test_ranges_no_matching_envelope_returns_empty():
    other = '999e4567-e89b-12d3-a456-426614174999'
    env = _envelope([_run(0, 7, root=other)])
    assert _validated_received_ranges(CLAIM, [env]) == ()
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 7, epoch=EPOCH + 1)])]) == ()
    assert _validated_received_ranges(CLAIM, []) == ()


def test_ranges_unknown_envelopes_give_no_proof():
    unknown = {'version': 1, 'capability': 'unknown', 'coverage': 'unknown', 'origin': 'live', 'reason': 'legacy'}
    assert _validated_received_ranges(CLAIM, [unknown]) == ()
    assert (
        _validated_received_ranges(
            CLAIM, [{'version': 1, 'capability': 'unknown', 'coverage': 'incomplete', 'reason': 'overflow'}]
        )
        == ()
    )


def test_ranges_incomplete_coverage_still_yields_positive_runs():
    env = _envelope([_run(0, 3), _run(7, 10)], coverage='incomplete')
    assert _validated_received_ranges(CLAIM, [env]) == ((0, 3), (7, 10))


def test_ranges_matching_conflict_abstains_everything():
    conflicted = _envelope([_run(0, 7)], conflicts=1)
    clean = _envelope([_run(0, 5)])
    assert _validated_received_ranges(CLAIM, [conflicted]) is None
    assert _validated_received_ranges(CLAIM, [clean, conflicted]) is None
    assert _validated_received_ranges(CLAIM, [conflicted, clean]) is None


def test_ranges_other_root_conflict_does_not_abstain():
    other = '999e4567-e89b-12d3-a456-426614174999'
    conflicted_elsewhere = _envelope([_run(0, 7, root=other)], conflicts=3)
    clean = _envelope([_run(0, 5)])
    assert _validated_received_ranges(CLAIM, [conflicted_elsewhere, clean]) == ((0, 5),)


def test_ranges_wrong_channel_or_rate_give_no_proof():
    assert (
        _validated_received_ranges(
            CLAIM, [_envelope([_run(0, 7, rate=8000, decoded_end=7 * 16000, samples_per_frame=16000)])]
        )
        == ()
    )
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 7, channel='stereo')])]) == ()


def test_ranges_non_live_origin_gives_no_proof():
    env = _envelope([_run(0, 7)], origin='sync')
    assert _validated_received_ranges(CLAIM, [env]) == ()


def test_ranges_malformed_matching_envelope_abstains():
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 7)], capability='unknown')]) is None
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 7)], coverage='unknown')]) is None
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 7)], version=2)]) is None
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 7)], conflicts=True)]) is None


def test_ranges_malformed_matching_run_abstains():
    bad_geometry = _run(0, 7, decoded_end=9999)
    assert _validated_received_ranges(CLAIM, [_envelope([bad_geometry])]) is None
    inverted = _run(7, 0)
    inverted['decoded_sample_end'] = 0
    assert _validated_received_ranges(CLAIM, [_envelope([inverted])]) is None
    bool_run = _run(0, 7)
    bool_run['source_frame_start'] = True
    assert _validated_received_ranges(CLAIM, [_envelope([bool_run])]) is None
    float_run = _run(0, 7)
    float_run['samples_per_frame'] = 16000.0
    assert _validated_received_ranges(CLAIM, [_envelope([float_run])]) is None


def test_ranges_envelope_and_run_caps():
    assert _validated_received_ranges(CLAIM, [_envelope([_run(0, 1)] * 33)]) is None
    assert _validated_received_ranges(CLAIM, [{}] * 14) is None
    assert _validated_received_ranges(CLAIM, [{}] * 13) == ()


def test_ranges_bad_claim_abstains():
    env = _envelope([_run(0, 7)])
    assert _validated_received_ranges({'capture_root': ROOT}, [env]) is None
    assert _validated_received_ranges(None, [env]) is None
    assert _validated_received_ranges({**CLAIM, 'codec': 'aac'}, [env]) is None
    assert _validated_received_ranges({**CLAIM, 'channel': 'stereo'}, [env]) is None
    assert _validated_received_ranges({**CLAIM, 'frame_count': True}, [env]) is None


def test_public_ranges_receipt_only_envelopes_never_prove_received_audio():
    """Receipt-only coverage authorizes no suppression: () keeps everything."""
    assert validated_live_ranges(CLAIM, [_envelope([_run(0, 7)])]) == ()
    assert validated_live_ranges(CLAIM, [_envelope([_run(0, 10)])]) == ()
    assert validated_live_ranges(CLAIM, [_envelope([_run(0, 5), _run(3, 7)])]) == ()
    assert validated_live_ranges(CLAIM, [_envelope([_run(0, 3), _run(7, 10)], coverage='incomplete')]) == ()
    assert validated_live_ranges(CLAIM, []) == ()


def test_public_ranges_preserve_malformed_and_conflict_abstention():
    assert validated_live_ranges(CLAIM, [_envelope([_run(0, 7)], conflicts=1)]) is None
    assert validated_live_ranges(CLAIM, [_envelope([_run(0, 7)], coverage='unknown')]) is None
    assert validated_live_ranges(CLAIM, [{}] * 14) is None
    assert validated_live_ranges(None, [_envelope([_run(0, 7)])]) is None


def _labeled_wav(tmp_path, name='audio_1760000000.wav', frame_values=range(10), samples_per_frame=160):
    path = tmp_path / name
    _write_wav(path, [(v, samples_per_frame) for v in frame_values])
    return path, samples_per_frame


def test_split_keeps_only_new_frames(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    claim = {**CLAIM, 'frame_count': 10}
    result = apply_wal_audio_coverage(str(path), claim, [spf] * 10, [(7, 10)])
    assert result['status'] == 'split'
    assert len(result['wav_paths']) == 1
    derivative = result['wav_paths'][0]
    assert os.path.basename(os.path.dirname(derivative)) != 'audio_1760000000.coverage'
    assert os.path.basename(os.path.dirname(os.path.dirname(derivative))) == 'audio_1760000000.coverage'
    assert derivative.endswith('_1760000000.07.wav')
    rate, payload = _read_wav(derivative)
    assert rate == RATE
    assert payload == b''.join(_frame_bytes(v, spf) for v in (7, 8, 9))
    mapping = result['frame_maps'][derivative]
    assert mapping['claim']['source_frame_start'] == 7
    assert mapping['claim']['frame_count'] == 3
    assert mapping['offsets'] == [0, spf, 2 * spf, 3 * spf]
    assert mapping['incomplete'] is False
    assert result['generated_paths'] == {derivative}


def test_split_two_holes_two_files_no_gap_concatenation(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    result = apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(0, 3), (7, 10)])
    assert result['status'] == 'split'
    assert len(result['wav_paths']) == 2
    first, second = sorted(result['wav_paths'], key=lambda p: result['frame_maps'][p]['claim']['source_frame_start'])
    _, payload = _read_wav(first)
    assert payload == b''.join(_frame_bytes(v, spf) for v in (0, 1, 2))
    assert first.endswith('_1760000000.wav')
    _, payload = _read_wav(second)
    assert payload == b''.join(_frame_bytes(v, spf) for v in (7, 8, 9))
    assert second.endswith('_1760000000.07.wav')
    assert result['frame_maps'][first]['claim']['source_frame_start'] == 0
    assert result['frame_maps'][second]['claim']['source_frame_start'] == 7


def test_split_variable_frames_offsets(tmp_path):
    path = tmp_path / 'audio_1760000000.wav'
    frame_samples = [100, 1600, 50, 800, 200]
    _write_wav(path, [(i, n) for i, n in enumerate(frame_samples)])
    result = apply_wal_audio_coverage(str(path), {**CLAIM, 'frame_count': 5}, frame_samples, [(1, 4)])
    assert result['status'] == 'split'
    derivative = result['wav_paths'][0]
    _, payload = _read_wav(derivative)
    expected = _frame_bytes(1, 1600) + _frame_bytes(2, 50) + _frame_bytes(3, 800)
    assert payload == expected
    mapping = result['frame_maps'][derivative]
    assert mapping['claim']['frame_count'] == 3
    assert mapping['offsets'] == [0, 1600, 1650, 2450]
    assert derivative.endswith('_1760000000.00625.wav')


def test_abstain_keeps_original_untouched(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    before = path.read_bytes()
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, None) is None
    assert path.read_bytes() == before
    assert not (tmp_path / 'audio_1760000000.coverage').exists()


def test_all_covered_suppresses_file(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    result = apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [])
    assert result['status'] == 'suppressed'
    assert result['wav_paths'] == []
    assert result['frame_maps'] == {}
    assert path.exists()


def test_unchanged_returns_original_path_and_map(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    offsets = [i * spf for i in range(11)]
    original_map = {'claim': dict(CLAIM), 'offsets': offsets, 'incomplete': False}
    result = apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(0, 10)], frame_map=original_map)
    assert result['status'] == 'unchanged'
    assert result['wav_paths'] == [str(path)]
    assert result['frame_maps'][str(path)] is original_map
    assert result['generated_paths'] == set()
    assert not (tmp_path / 'audio_1760000000.coverage').exists()


def test_map_offsets_disagreeing_with_decoded_geometry_are_rejected(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    bad_map = {'claim': dict(CLAIM), 'offsets': list(range(11)), 'incomplete': False}
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(0, 10)], frame_map=bad_map) is None
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(0, 5)], frame_map=bad_map) is None
    assert not (tmp_path / 'audio_1760000000.coverage').exists()


def test_apply_rejects_out_of_domain_or_malformed(tmp_path):
    path, spf = _labeled_wav(tmp_path)
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(9, 11)]) is None
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(-1, 5)]) is None
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(0.5, 5)]) is None
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(7, 3)]) is None
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf] * 10, [(5, 8), (2, 4)]) is None
    assert apply_wal_audio_coverage(str(path), {'codec': 'aac'}, [spf] * 10, [(0, 10)]) is None
    assert apply_wal_audio_coverage(str(path), dict(CLAIM), [spf, 0, spf], [(0, 3)]) is None
    assert not (tmp_path / 'audio_1760000000.coverage').exists()


def test_ranges_oversized_envelope_abstains_before_scan():
    env = _envelope([_run(i, i + 1) for i in range(33)])
    assert _validated_received_ranges(dict(CLAIM), [env]) is None
    other = {**CLAIM, 'capture_root': '999e4567-e89b-12d3-a456-426614174999'}
    oversized_other_root = _envelope([_run(i, i + 1, root=other['capture_root']) for i in range(33)])
    assert _validated_received_ranges(dict(CLAIM), [oversized_other_root]) is None


def test_ranges_nonint_matching_rate_abstains():
    env = _envelope([_run(0, 5, rate=16000.0)])
    assert _validated_received_ranges(dict(CLAIM), [env]) is None
    env = _envelope([_run(0, 5, rate=True)])
    assert _validated_received_ranges(dict(CLAIM), [env]) is None


def _batch_maps(tmp_path, names, claim=None, samples_per_frame=160):
    wavs, maps, frames = [], {}, {}
    for name in names:
        path, spf = _labeled_wav(tmp_path, name=name, samples_per_frame=samples_per_frame)
        key = str(path)
        c = dict(claim or CLAIM)
        wavs.append(key)
        frames[key] = [spf] * 10
        maps[key] = {'claim': c, 'offsets': [i * spf for i in range(11)], 'incomplete': False}
    return wavs, maps, frames


def _patch_lineage(monkeypatch, rows=None, truncated=None, degraded=False):
    from utils.sync import recording_lineage

    monkeypatch.setattr(recording_lineage, 'load_lineage', lambda *a, **k: (list(rows or []), truncated, degraded))


def test_batch_first_split_second_conflict_writes_no_derivatives(tmp_path, monkeypatch):
    from utils.sync.wal_audio_coverage import apply_batch_wal_audio_coverage

    wavs, maps, frames = _batch_maps(tmp_path, ['audio_1760000000.wav', 'audio_1760000100.wav'])
    env = _envelope([_run(0, 7, samples_per_frame=160)])
    conflict = _envelope([_run(0, 3, samples_per_frame=160)], conflicts=1)
    _patch_lineage(
        monkeypatch,
        rows=[
            {
                'id': 'L1',
                'external_data': {'recording_origin_id': 'REC-1'},
                'source': 'omi',
                'client_device_id': 'pendant',
                'is_locked': False,
                'started_at': 1759999900.0,
                'finished_at': 1760000100.0,
                'capture_evidence': env,
            },
            {
                'id': 'L2',
                'external_data': {'recording_origin_id': 'REC-1'},
                'source': 'omi',
                'client_device_id': 'pendant',
                'is_locked': False,
                'started_at': 1759999900.0,
                'finished_at': 1760000100.0,
                'capture_evidence': conflict,
            },
        ],
    )
    result = apply_batch_wal_audio_coverage(
        'u',
        'REC-1',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        wav_paths=wavs,
        source_frame_maps=maps,
        decoded_frames=frames,
    )
    assert result['status'] == 'abstained'
    assert list(tmp_path.rglob('*.coverage')) == []
    for original in wavs:
        with wave.open(original, 'rb') as wav:
            assert wav.readframes(wav.getnframes()) == b''.join(_frame_bytes(v, 160) for v in range(10))


def test_flag_parse_default_on_tokens_and_typo_off(monkeypatch):
    from config.sync_audio_coverage import (
        SYNC_WAL_AUDIO_COVERAGE_ENV,
        sync_wal_audio_coverage_active_for,
        sync_wal_audio_coverage_enabled,
    )

    monkeypatch.delenv(SYNC_WAL_AUDIO_COVERAGE_ENV, raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_ENABLED', raising=False)
    assert sync_wal_audio_coverage_enabled() is True
    monkeypatch.setenv(SYNC_WAL_AUDIO_COVERAGE_ENV, '  ')
    assert sync_wal_audio_coverage_enabled() is True
    for token in ('1', 'true', 'on', 'yes', 'enabled', 'TRUE'):
        monkeypatch.setenv(SYNC_WAL_AUDIO_COVERAGE_ENV, token)
        assert sync_wal_audio_coverage_enabled() is True
    for token in ('0', 'false', 'off', 'disabled', 'treu', 'none'):
        monkeypatch.setenv(SYNC_WAL_AUDIO_COVERAGE_ENV, token)
        assert sync_wal_audio_coverage_enabled() is False
        assert sync_wal_audio_coverage_active_for('u') is False
    monkeypatch.setenv(SYNC_WAL_AUDIO_COVERAGE_ENV, 'true')
    assert sync_wal_audio_coverage_active_for('u') is True
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'other-uid')
    assert sync_wal_audio_coverage_active_for('u') is False
    assert sync_wal_audio_coverage_active_for('other-uid') is True


def test_registered_runtime_env_on_four_services_both_envs():
    import yaml
    from pathlib import Path

    manifest = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy' / 'runtime_env.yaml').read_text())
    for env_name in ('dev', 'prod'):
        services = manifest['environments'][env_name]['cloud_run']['services']
        for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
            entry = services[service]['env']['SYNC_WAL_AUDIO_COVERAGE_ENABLED']
            assert entry['value'] == 'true'
            assert entry['category'] == 'rollout'
    classification = __import__('json').loads(
        (Path(__file__).resolve().parents[2] / '..' / 'config' / 'deployment-setting-classification.json')
        .resolve()
        .read_text()
    )
    found = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            found.extend(v for v in node if isinstance(v, str))
            for value in node:
                walk(value)

    walk(classification)
    assert 'SYNC_WAL_AUDIO_COVERAGE_ENABLED' in found


def test_opus_fs320_claim_maps_320_sample_frames(monkeypatch, tmp_path):
    """An `opus` claim on an `_opus_fs320_` basename maps decoded frames to ordinals."""
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    stem = 'audio_pendant1_opus_fs320_16000_1_fs320_1700000000'
    wav_path = tmp_path / f'{stem}.wav'
    with wave.open(str(wav_path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\x00' * 320 * 2 * 3)
    claim = {**CLAIM, 'codec': 'opus', 'frame_count': 3}
    maps = build_sync_source_frame_maps(
        {f'{stem}.bin': claim},
        [str(wav_path)],
        {str(wav_path): [320, 320, 320]},
    )
    assert maps[str(wav_path)]['offsets'] == [0, 320, 640, 960]
    assert maps[str(wav_path)]['incomplete'] is False
