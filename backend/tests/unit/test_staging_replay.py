"""Staging replay driver: guards, materialization and the send loop (swarm lane 4)."""

import asyncio
import json
import time

import numpy  # noqa: F401  (imported at collection so synthetic_pcm's lazy import is not billed to a test)
import pytest

from scripts.staging import replay as rp
from testing.loadgen import mirror_codec as mc
from testing.loadgen import population as pop
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
    def __init__(self):
        self.posts = []
        self.gets = 0

    async def post(self, url, **kw):
        self.posts.append((url, kw))
        if url.endswith('/v2/sync-capture-manifest'):
            return FakeResponse(200, {'manifest': 'signed-manifest'})
        return FakeResponse(202, {'job_id': f'bp_{len(self.posts)}', 'lane': 'fresh', 'status': 'queued'})

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


def _run(plans, seeder=None, poll=False):
    config = rp.ReplayConfig(target='http://127.0.0.1:1', admin_key='A' * 20, poll=poll, poll_interval_s=0)
    replay = rp.Replay(config, plans, seeder=seeder, sleep=_no_sleep)
    client = FakeClient()
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


def test_seeder_refuses_outside_staging(monkeypatch):
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    with pytest.raises(rp.ReplayRefused):
        rp.StagingFirestoreSeeder()


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
