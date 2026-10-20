"""Synthetic population generator + profile refresh (swarm lane 4, plan F F7)."""

import math
import time

import pytest

from testing.loadgen import population as pop
from testing.loadgen import refresh_profile as rp
from utils.client_device import resolve_client_device
from utils.sync.lanes import SyncLane, classify_sync_lane

PROFILE = {
    'schema_version': 1,
    'uploads': {'accepted_per_min_mean': 200.0, 'accepted_per_min_by_utc_hour': [100.0 + h for h in range(24)]},
    'platform_mix': {'android': 0.25, 'ios': 0.75},
    'recording_age_seconds': {
        'fresh': {'le': [300.0, 1800.0, 3600.0, 21600.0], 'cdf': [0.66, 0.8, 0.88, 1.0]},
        'backfill': {'le': [3600.0, 86400.0, 259200.0, 604800.0], 'cdf': [0.3, 0.5, 0.8, 1.0]},
    },
    'assumed': {
        'files_per_upload': {'weights': {'1': 0.6, '2': 0.3, '3': 0.1}},
        'near_silence_empty_asr_rate': {'value': 0.29},
        'burst_owners': {'audio_age_days': [8, 10]},
    },
}


def _spec(**kw):
    base = dict(run_id='t1', owners=50, duration_s=7200.0, percent_of_prod=1.0, seed=7)
    base.update(kw)
    return pop.PopulationSpec(**base)


@pytest.fixture(scope='module')
def plans():
    return pop.generate(pop.synthetic_recordings(400), PROFILE, _spec())


def _end(f):
    return f.capture_offset_s + f.duration_s + f.lead_silence_s + f.trail_silence_s


def test_generation_is_deterministic(plans):
    again = pop.generate(pop.synthetic_recordings(400), PROFILE, _spec())
    assert [p.to_json() for p in again] == [p.to_json() for p in plans]
    other = pop.generate(pop.synthetic_recordings(400), PROFILE, _spec(seed=8))
    assert [p.to_json() for p in other] != [p.to_json() for p in plans]


def test_shape_allocation_is_exact(plans):
    assert pop._allocate(50, {'steady': 0.7, 'burst': 0.1, 'reverse': 0.1, 'shuffled': 0.1}).count('steady') == 35
    shapes = {}
    for p in plans:
        shapes.setdefault(p.owner_id, p.shape)
    counts = {s: list(shapes.values()).count(s) for s in set(shapes.values())}
    assert counts['burst'] == counts['reverse'] == counts['shuffled'] == 5
    assert 30 <= counts['steady'] <= 35  # a steady owner with zero Poisson arrivals has no rows


def test_backlog_share_follows_profile(plans):
    backfill = sum(1 for p in plans if p.lane_hint == 'backfill') / len(plans)
    assert 0.25 < backfill < 0.6  # profile fixture has no lane_decisions -> 0.4 default


def test_off_peak_window_keeps_backfill_share_and_hour_level():
    # Off-peak start: curve at hours 8-9 is half the peak and 2/3 of the daily mean. Before the
    # window fix the backlog was sized on the daily mean while steady arrivals were thinned, so
    # the m1p1 plan carried 57% backfill against the profile's 39%.
    curve = [50.0 if h in (8, 9) else 100.0 for h in range(24)]
    profile = dict(PROFILE, uploads={'accepted_per_min_mean': 200.0, 'accepted_per_min_by_utc_hour': curve})
    level, thinning = pop._window_weights(profile, _spec(start_utc_hour=8))
    assert thinning == pytest.approx(0.5)
    assert level == pytest.approx(50.0 / (sum(curve) / 24.0))
    plans = pop.generate(pop.synthetic_recordings(400), profile, _spec(start_utc_hour=8, percent_of_prod=5.0))
    backfill = sum(1 for p in plans if p.lane_hint == 'backfill') / len(plans)
    assert 0.3 < backfill < 0.5
    target = 200.0 * 0.05 * 120 * level
    assert abs(len(plans) - target) / target < 0.2
    assert pop._window_weights(profile, _spec()) == (1.0, 1.0)  # no start hour = flat


def test_owner_ids_are_synthetic_and_bounded():
    assert pop.owner_id('r1', 3) == 'lg-r1-o0003'
    with pytest.raises(ValueError):
        pop.owner_id('bad/run', 1)


def test_rate_tracks_percent_of_prod(plans):
    target = 200.0 * 0.01 * 120  # 1% of 200/min for 2h
    assert abs(len(plans) - target) / target < 0.35


def test_no_capture_is_ever_in_the_future(plans):
    assert all(_end(f) <= 0 for p in plans for f in p.files)


def test_fresh_uploads_classify_fresh_and_backlogs_backfill(plans):
    send = time.time() - 5  # parse_sync_filename_timestamp rejects future names
    for p in plans:
        names = [f'audio_omi_pcm16_16000_1_fs1600_{int((send + f.capture_offset_s) * 1000)}.bin' for f in p.files]
        # The device id the server derives from the X-App-Platform / X-Device-Id-Hash headers, not a prebuilt one.
        device = resolve_client_device(x_app_platform=p.platform, x_device_id_hash=p.device_hash)
        assert device.client_device_id == f'{p.platform}_{p.device_hash}', p
        decision = classify_sync_lane(names, client_device_id=device.client_device_id, now=send)
        assert decision.lane == (SyncLane.FRESH if p.lane_hint == 'fresh' else SyncLane.BACKFILL), p


def test_reverse_owner_uploads_newest_first(plans):
    reverse = [p for p in plans if p.shape == 'reverse']
    assert reverse
    by_owner = {}
    for p in reverse:
        by_owner.setdefault(p.owner_id, []).append(p)
    for uploads in by_owner.values():
        uploads.sort(key=lambda p: p.sequence)
        starts = [min(f.capture_offset_s for f in p.files) for p in uploads]
        assert starts == sorted(starts, reverse=True)
        assert len({p.at_s for p in uploads}) == 1  # one backlog, sent back to back


def test_burst_owner_audio_is_eight_to_ten_days_old(plans):
    burst = [p for p in plans if p.shape == 'burst']
    by_owner = {}
    for p in burst:
        by_owner.setdefault(p.owner_id, []).append(max(_end(f) for f in p.files))
    for ends in by_owner.values():
        assert -10 * 86400 - 1 <= max(ends) <= -8 * 86400 + 1


def test_silence_variation_present(plans):
    files = [f for p in plans for f in p.files]
    assert any(f.silent_only for f in files)
    assert any(f.lead_silence_s > 0 for f in files)


def test_owner_never_reuses_a_recording_while_pool_allows(plans):
    seen = {}
    for p in plans:
        key = (p.owner_id, p.recording_key)
        if p.shape == 'steady':
            assert key not in seen
        seen[key] = True


def test_burst_mode_is_all_burst_at_full_intensity():
    plans = pop.generate(pop.synthetic_recordings(100), PROFILE, pop.burst_spec('b1', 6, recordings_per_owner=4))
    assert {p.shape for p in plans} == {'burst'}
    assert len({p.owner_id for p in plans}) == 6
    assert all(p.lane_hint == 'backfill' for p in plans)


def test_plan_round_trip(tmp_path, plans):
    path = tmp_path / 'plan.jsonl'
    pop.write_plan(str(path), plans, _spec())
    header, again = pop.read_plan(str(path))
    assert header['summary']['uploads'] == len(plans)
    assert again == plans


def test_manifest_recordings_group_and_sort():
    manifest = {
        'objects': [
            {
                'object': 'mirror/v1/a/g1/00001-x.smenc',
                'group': 'g1',
                'source_format': 'chunk-opus-lp',
                'duration_s': 10,
                'capture_start': 20.0,
            },
            {
                'object': 'mirror/v1/a/g1/00000-y.smenc',
                'group': 'g1',
                'source_format': 'chunk-opus-lp',
                'duration_s': 10,
                'capture_start': 10.0,
            },
        ]
    }
    (rec,) = pop.recordings_from_manifest(manifest)
    assert [f.ref for f in rec.files] == ['mirror:mirror/v1/a/g1/00000-y.smenc', 'mirror:mirror/v1/a/g1/00001-x.smenc']
    assert rec.span_s == pytest.approx(20.0)


# --- refresh_profile ---------------------------------------------------------


def _fake_fetch(path, params):
    q = params.get('query', '')
    if path == '/api/v1/query_range':
        return {'result': [{'values': [[3600 * h, str(60.0 * (h + 1))] for h in range(48)]}]}
    if 'omi_sync_upload_total{outcome="accepted"}[1d]' in q:
        return {'result': [{'metric': {}, 'value': [0, str(1440 * 100.0)]}]}
    if 'omi_sync_upload_total' in q:
        rows = [
            ('ios', 'accepted', 900),
            ('android', 'accepted', 100),
            ('web', 'accepted', 5),
            ('ios', 'started', 1000),
            ('ios', 'failed', 10),
        ]
        return {'result': [{'metric': {'platform': p, 'outcome': o}, 'value': [0, str(v)]} for p, o, v in rows]}
    if 'omi_sync_lane_admissions_total' in q:
        rows = [
            ('fresh', 'legacy', 'recent_legacy_capture', 600),
            ('backfill', 'legacy', 'unbound_capture_time', 380),
            ('backfill', 'untrusted', 'invalid_capture_time', 3),
        ]
        return {
            'result': [{'metric': {'lane': l, 'trust': t, 'reason': r}, 'value': [0, str(v)]} for l, t, r, v in rows]
        }
    if 'omi_sync_recording_age_seconds_bucket' in q:
        rows = [('fresh', '300', 50), ('fresh', '1800', 60), ('fresh', '3600', 100), ('fresh', '+Inf', 100)]
        return {'result': [{'metric': {'lane': l, 'le': le}, 'value': [0, str(v)]} for l, le, v in rows]}
    if 'omi_vad_gate_audio_seconds_total' in q:
        return {
            'result': [
                {'metric': {'outcome': 'sent'}, 'value': [0, '40']},
                {'metric': {'outcome': 'skipped'}, 'value': [0, '60']},
            ]
        }
    raise AssertionError(q)


def test_build_profile_applies_k_floor_and_rate_level():
    profile = rp.build_profile(_fake_fetch, days=7, now=48 * 3600.0)
    assert profile['platform_mix'] == {'android': 0.1, 'ios': 0.9}  # web (5 < k) dropped
    assert 'backfill/untrusted/invalid_capture_time' not in profile['lane_decisions']
    assert profile['uploads']['accepted_per_min_mean'] == 100.0
    curve = profile['uploads']['accepted_per_min_by_utc_hour']
    assert sum(curve) / 24 == pytest.approx(100.0, rel=1e-3)
    assert profile['recording_age_seconds']['fresh']['le'] == [300.0, 3600.0]  # 1800 bucket adds 10 < k
    assert profile['speech_share'] == 0.4
    assert profile['uploads']['failed_share'] == 0.01


def test_committed_profile_loads_and_has_no_identifiers():
    profile = rp.load_profile()
    assert profile['k_floor'] >= 20
    assert len(profile['uploads']['accepted_per_min_by_utc_hour']) == 24
    text = rp.PROFILE_PATH.read_text()
    assert 'uid' not in text.lower().replace('no uids', '')
    assert not math.isnan(profile['uploads']['accepted_per_min_mean'])
