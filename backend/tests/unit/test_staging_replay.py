"""Staging replay driver: guards, materialization and the send loop (swarm lane 4)."""

import asyncio
import dataclasses
import json
import time
from pathlib import Path

import numpy  # noqa: F401  (imported at collection so synthetic_pcm's lazy import is not billed to a test)
import pytest
import yaml

from scripts.staging import replay as rp
from testing.loadgen import mirror_codec as mc
from testing.loadgen import population as pop
from utils.client_device import resolve_client_device
from utils.request_validation import parse_sync_filename_timestamp

PROFILE = {
    'schema_version': 1,
    'uploads': {'accepted_per_min_mean': 300.0},
    'platform_mix': {'ios': 1.0},
    'assumed': {'files_per_upload': {'weights': {'1': 0.5, '2': 0.5}}, 'near_silence_empty_asr_rate': {'value': 0.29}},
}


@pytest.mark.parametrize(
    'url',
    [
        'https://api.omi.me',
        'https://backend-sync-xyz.a.run.app',  # not staging
        'http://backend-sync-staging-abc.a.run.app',  # not https
        'https://backend-staging.based-hardware.example',
    ],
)
def test_target_guard_refuses_non_staging(url):
    with pytest.raises(rp.ReplayRefused):
        rp.check_target(url, allow_local=False)


def test_target_guard_accepts_staging_and_gated_local():
    assert rp.check_target('https://backend-sync-staging-abc123-uc.a.run.app/', allow_local=False).endswith('.run.app')
    with pytest.raises(rp.ReplayRefused):
        rp.check_target('http://127.0.0.1:8080', allow_local=False)
    assert rp.check_target('http://127.0.0.1:8080', allow_local=True) == 'http://127.0.0.1:8080'


def test_load_host_guard_never_m5():
    target = 'https://backend-staging-abc.a.run.app'
    with pytest.raises(rp.ReplayRefused):
        rp.check_load_host(target, env={})
    with pytest.raises(rp.ReplayRefused):
        rp.check_load_host(target, env={'OMI_LOADGEN_HOST': 'm5-mbp'})
    assert rp.check_load_host(target, env={'OMI_LOADGEN_HOST': 'm1-mac-studio'}) == 'm1-mac-studio'
    assert rp.check_load_host(target, env={'KUBERNETES_SERVICE_HOST': '10.0.0.1'}) == 'in-cluster'
    assert rp.check_load_host('http://127.0.0.1:1', env={}) == 'local'


def _plans(n_recordings=40, **kw):
    spec = pop.PopulationSpec(run_id='rt', owners=6, duration_s=600.0, rate_per_min=3.0, seed=3, **kw)
    return pop.generate(pop.synthetic_recordings(n_recordings, files_per_recording=2, file_seconds=5.0), PROFILE, spec)


def test_materialize_synthetic_files_parse_and_are_owner_unique():
    plans = _plans()[:8]  # fast-unit CPU budget
    now = time.time()
    seen = {}
    for p in plans:
        m = rp.materialize(p, now, None, opus_silence=None)
        assert len(m.files) == len(p.files)
        for name, body in m.files:
            assert parse_sync_filename_timestamp(name) <= now
            assert mc.wal_payloads(body)
        assert m.capture_hi <= now
        for name, body in m.files:
            seen.setdefault(body, set()).add(p.owner_id)
    assert all(len(owners) == 1 for body, owners in seen.items() if set(body) != {0} and len(body) > 4096)


class FakeBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def download_as_bytes(self, timeout=None):
        return self.store[self.name]


class FakeBucket:
    def __init__(self, store):
        self.store = store

    def blob(self, name):
        return FakeBlob(self.store, name)


def test_mirror_reader_opens_sealed_objects_and_bounds_cache():
    key = mc.derive_mirror_key('k' * 40)
    names = [f'mirror/v1/a/g/{i:05d}-x.smenc' for i in range(3)]
    store = {n: mc.seal_mirror_object(key, n, bytes([i]) * 100) for i, n in enumerate(names)}
    reader = rp.MirrorReader(FakeBucket(store), key, cache_bytes=150)
    assert reader.read('mirror:' + names[0]) == b'\x00' * 100
    assert reader.read('mirror:' + names[1]) == b'\x01' * 100
    assert reader.held <= 150 and len(reader.cache) == 1


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    """Mirrors the server's device and lane rules: the manifest route resolves the device from the
    headers (403 when none), and an upload is fresh only with a bound manifest, else backfill."""

    def __init__(self, manifest_status=200):
        self.posts = []
        self.gets = 0
        self.manifest_status = manifest_status

    async def post(self, url, **kw):
        self.posts.append((url, kw))
        headers = kw['headers']
        if url.endswith('/v2/sync-capture-manifest'):
            device = resolve_client_device(
                x_app_platform=headers.get('X-App-Platform'), x_device_id_hash=headers.get('X-Device-Id-Hash')
            )
            if device.client_device_id is None or self.manifest_status != 200:
                return FakeResponse(self.manifest_status if self.manifest_status != 200 else 403, {})
            return FakeResponse(200, {'manifest': 'signed-manifest'})
        lane = (
            'fresh'
            if headers.get('X-Omi-Sync-Capture-Manifest') and kw['params'].get('conversation_id')
            else 'backfill'
        )
        return FakeResponse(202, {'job_id': f'bp_{len(self.posts)}', 'lane': lane, 'status': 'queued'})

    async def get(self, url, **kw):
        self.gets += 1
        return FakeResponse(200, {'status': 'completed'})


class FakeSeeder:
    def __init__(self):
        self.captures = []
        self.users = set()

    def seed_user(self, uid):
        self.users.add(uid)

    def seed_capture(self, uid, conversation_id, device_id, platform, started, finished):
        assert started <= finished
        self.captures.append((uid, conversation_id, device_id))


async def _no_sleep(_):
    return None


def _run(plans, seeder=None, poll=False, client=None):
    config = rp.ReplayConfig(target='http://127.0.0.1:1', admin_key='A' * 20, poll=poll, poll_interval_s=0)
    replay = rp.Replay(config, plans, seeder=seeder, sleep=_no_sleep)
    client = client or FakeClient()
    results = asyncio.run(replay.run(client))
    return results, client


def test_replay_sends_each_owner_serially_with_impersonation():
    plans = _plans()
    results, client = _run(plans, poll=True)
    uploads = [kw for url, kw in client.posts if url.endswith('/v2/sync-local-files')]
    assert len(uploads) == len(plans) == len(results)
    for kw in uploads:
        auth = kw['headers']['Authorization']
        assert auth.startswith('Bearer ' + 'A' * 20 + 'lg-rt-o')
        assert kw['headers']['X-Device-Id-Hash'] and kw['files']
    order = {}
    for r in results:
        order.setdefault(r.owner_id, []).append(r.sequence)
    assert all(seq == sorted(seq) for seq in order.values())
    assert all(r.final_status == 'completed' for r in results)
    summary = rp.summarize_results(results)
    assert summary['accepted'] == len(plans) and summary['by_final_status'] == {'completed': len(plans)}


def test_replay_seeds_capture_and_binds_manifest_for_fresh_only():
    plans = _plans()
    seeder = FakeSeeder()
    results, client = _run(plans, seeder=seeder)
    fresh = [r for r in results if r.lane_hint == 'fresh']
    assert fresh and len(seeder.captures) == len(fresh)
    assert all(r.seeded and r.conversation_id.startswith('lg-cap-') for r in fresh)
    assert not any(r.seeded for r in results if r.lane_hint == 'backfill')
    for url, kw in client.posts:
        if url.endswith('/v2/sync-local-files') and kw['params'].get('conversation_id'):
            assert kw['headers']['X-Omi-Sync-Capture-Manifest'] == 'signed-manifest'
    record = rp.population_record(results, {'spec': {'run_id': 'rt'}})
    assert record['run'] == 'rt'
    assert sum(len(o['uploads']) for o in record['owners'].values()) == len(results)
    json.dumps(record)
    # The stub's device id is the one the server derives from the headers, so every fresh upload binds.
    assert all(device_id and device_id.split('_', 1)[1] for _, _, device_id in seeder.captures)
    summary = rp.summarize_results(results)
    assert summary['lane_hint_mismatch'] == 0 and summary['failed_checks'] == []
    assert summary['by_lane'].get('fresh') == len(fresh)


def test_refused_manifest_skips_the_fresh_upload_and_fails_the_run():
    plans = _plans()
    client = FakeClient(manifest_status=403)
    results, client = _run(plans, seeder=FakeSeeder(), client=client)
    fresh = [r for r in results if r.lane_hint == 'fresh']
    assert fresh and all(r.skipped and r.error == 'manifest_http_403' and not r.http_status for r in fresh)
    uploads = [kw for url, kw in client.posts if url.endswith('/v2/sync-local-files')]
    assert len(uploads) == len(results) - len(fresh)  # never sent as backfill
    summary = rp.summarize_results(results)
    assert summary['fresh_skipped'] == len(fresh) and 'fresh_skipped' in summary['failed_checks']


def test_fresh_admitted_as_backfill_fails_the_run():
    plans = _plans()
    results, _ = _run(plans)  # no seeding: the server admits every upload as backfill
    summary = rp.summarize_results(results)
    assert summary['lane_hint_mismatch'] == sum(1 for p in plans if p.lane_hint == 'fresh') > 0
    assert summary['failed_checks'] == ['lane_hint_mismatch']


def test_plan_check_refuses_unbindable_or_unseeded_fresh():
    plans = _plans()
    assert any(p.lane_hint == 'fresh' for p in plans)
    rp.check_plan_lanes(plans, seed_capture=True, unseeded_fresh=False)
    rp.check_plan_lanes(plans, seed_capture=False, unseeded_fresh=True)
    with pytest.raises(rp.ReplayRefused, match='--seed-capture'):
        rp.check_plan_lanes(plans, seed_capture=False, unseeded_fresh=False)
    old = [dataclasses.replace(p, device_hash=p.device_hash * 2) for p in plans]  # the 10-19 16-hex plans
    with pytest.raises(rp.ReplayRefused, match='8 hex'):
        rp.check_plan_lanes(old, seed_capture=True, unseeded_fresh=False)
    backfill_only = [p for p in old if p.lane_hint == 'backfill']
    rp.check_plan_lanes(backfill_only, seed_capture=False, unseeded_fresh=False)


def test_seeder_refuses_outside_staging(monkeypatch):
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    with pytest.raises(rp.ReplayRefused):
        rp.StagingFirestoreSeeder()


def test_seeder_maps_a_fence_breach_to_a_clean_refusal(monkeypatch):
    from utils import staging_fence

    monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
    monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
    monkeypatch.delenv('OMI_CUSTOMER_DATA_PROJECT', raising=False)
    staging_fence.reset_for_tests()
    try:
        with pytest.raises(rp.ReplayRefused, match='OMI_CUSTOMER_DATA_PROJECT'):
            rp.StagingFirestoreSeeder()
    finally:
        staging_fence.reset_for_tests()


def test_job_template_env_passes_the_staging_fence():
    from utils.staging_fence import staging_violations

    job = yaml.safe_load((Path(rp.BACKEND_DIR) / 'testing/loadgen/staging_replay_job.yaml').read_text())
    env = {e['name']: e['value'] for e in job['spec']['template']['spec']['containers'][0]['env'] if 'value' in e}
    assert staging_violations(env) == []


def test_cli_refuses_from_this_host_without_declaration(tmp_path, monkeypatch, capsys):
    plan = tmp_path / 'plan.jsonl'
    rc = rp.main(
        [
            'plan',
            '--run-id',
            'c1',
            '--owners',
            '4',
            '--hours',
            '0.1',
            '--rate-per-min',
            '2',
            '--synthetic',
            '10',
            '--out',
            str(plan),
        ]
    )
    assert rc == 0 and plan.exists()
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)
    monkeypatch.delenv('OMI_LOADGEN_HOST', raising=False)
    monkeypatch.setenv('STAGING_ADMIN_KEY', 'A' * 20)
    rc = rp.main(
        [
            'run',
            '--plan',
            str(plan),
            '--target',
            'https://backend-sync-staging-x.a.run.app',
            '--out',
            str(tmp_path / 'out'),
        ]
    )
    assert rc == 2
    assert 'replay_refused' in capsys.readouterr().err


def test_mirror_to_replay_round_trip_preserves_upload_bytes():
    """Raw pendant upload -> mirror copy -> manifest -> population -> replay body: bytes survive."""
    from scripts.staging import mirror_owner_recordings as mo

    uid = 'roundTripOwner0000000000001'
    secret = 'r' * 48
    mirror_key = mc.derive_mirror_key(secret)
    store, entries = {}, []
    originals = {}
    for job in range(3):
        for i in range(2):
            ts = 1_760_000_000 + job * 1000 + i * 60
            name = f'audio_abcdef0123456789_opus_fs320_16000_1_fs320_{ts}.123.bin'
            body = mc.wal_frame([bytes([job, i]) * 20] * 150)  # 3 s of 20 ms packets
            obj = mo.classify('syncing-local', uid, f'syncing/{uid}/job{job}/{name}', len(body), None)
            stats = mo.CopyStats()
            entry = mo.copy_object(
                obj,
                i,
                owner_label='owner-a',
                group=f'g{job}',
                read=lambda o, b=body: b,
                prod_user_key=lambda: b'',
                mirror_key=mirror_key,
                write=lambda n, sealed, meta: store.setdefault(n, sealed) is not None,
                stats=stats,
            )
            assert entry and entry['duration_s'] == pytest.approx(3.0)
            entries.append(entry)
            originals[entry['object']] = body
    recordings = pop.recordings_from_manifest({'objects': entries})
    assert len(recordings) == 3
    spec = pop.PopulationSpec(
        run_id='rtm', owners=3, duration_s=600.0, rate_per_min=1.0, seed=2, silence_pad_fraction=0.0
    )
    plans = pop.generate(recordings, PROFILE, spec)
    reader = rp.MirrorReader(FakeBucket(store), mirror_key)
    now = time.time()
    for plan in plans:
        m = rp.materialize(plan, now, reader, opus_silence=None)
        for (name, body), f in zip(m.files, plan.files):
            assert 'abcdef' not in name  # David's device hash never leaves the mirror
            if not f.silent_only:  # silent fillers fall back to pcm16 without libopus
                assert name.startswith('audio_omi_opus_fs320_16000_1_fs320_')
                assert body == originals[f.ref.removeprefix('mirror:')]


def test_secret_reader_only_reads_staging_secrets():
    class Session:
        def get(self, url, timeout):
            class R:
                status_code = 200

                def json(self):
                    import base64

                    return {'payload': {'data': base64.b64encode(b'k' * 32).decode()}}

            assert url.startswith(
                'https://secretmanager.googleapis.com/v1/projects/based-hardware-dev/secrets/staging-'
            )
            return R()

    ok = 'projects/based-hardware-dev/secrets/staging-admin-key/versions/latest'
    assert rp.read_staging_secret(ok, Session()) == 'k' * 32
    for bad in (
        'projects/based-hardware/secrets/ENCRYPTION_SECRET/versions/latest',
        'projects/based-hardware-dev/secrets/ADMIN_KEY/versions/latest',
    ):
        with pytest.raises(rp.ReplayRefused):
            rp.read_staging_secret(bad, Session())


def test_id_token_goes_in_x_serverless_authorization_and_is_cached():
    calls = []
    token = rp.CachedIdToken('https://backend-sync-staging-x.a.run.app', fetch=lambda aud: calls.append(aud) or 'tok')
    config = rp.ReplayConfig(target='http://127.0.0.1:1', admin_key='A' * 20, id_token=token)
    replay = rp.Replay(config, [])
    headers = replay._auth('lg-r-o0001')
    assert headers == {'Authorization': 'Bearer ' + 'A' * 20 + 'lg-r-o0001', 'X-Serverless-Authorization': 'Bearer tok'}
    replay._auth('lg-r-o0002')
    assert calls == ['https://backend-sync-staging-x.a.run.app']
    assert 'X-Serverless-Authorization' not in rp.Replay(rp.ReplayConfig(target='t', admin_key='A' * 20), [])._auth('o')
