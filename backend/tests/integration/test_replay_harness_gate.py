"""Two immutable product refs in one emulator session; no pushes or installs."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from testing.replay_harness.gate import gate

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'backend/testing/replay_harness/fixtures'


@pytest.fixture(autouse=True)
def require_emulator():
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required')


def evidence_output(tmp_path, label):
    root = Path(os.environ.get('REPLAY_GATE_EVIDENCE', tmp_path))
    return root / label


@pytest.mark.parametrize('trial', [1, 2, 3])
def test_identical_refs(tmp_path, trial):
    output = evidence_output(tmp_path, f'identical-{trial}')
    assert gate(ROOT, sorted(FIXTURES.iterdir()), 'HEAD', 'HEAD', output, regression_only=True) == 0
    result = json.loads((output / 'gate.json').read_text())
    assert result['verdict'] == 'REGRESSION_ONLY'
    assert not {'fixed', 'regressed'} & {r['classification'] for r in result['cases']}
    stress = next(r for r in result['cases'] if len(r['baseline']['outcomes']) > 1)
    assert len(stress['baseline']['outcomes']) == 3
    assert len(stress['candidate']['outcomes']) == (6 if stress['candidate']['retry_start'] else 3)
    assert set(p.name for p in output.iterdir()) == {'gate.json', 'gate.md', 'identity.key'}


def git(repo, *args, data=None):
    return subprocess.check_output(['git', '-C', str(repo), *args], input=data, stderr=subprocess.DEVNULL).strip()


def test_synthetic_product_fix(tmp_path, capsys):
    # A proof-only custody bypass in an unpushed commit. It is deliberately not
    # a proposed product fix. No working-tree product files are edited.
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '--shared', '--no-checkout', '--quiet', str(ROOT), str(clone)], check=True)
    base = git(clone, 'rev-parse', 'HEAD').decode()
    git(clone, 'read-tree', base)
    path = 'backend/database/record_audio.py'
    source = git(clone, 'show', f'{base}:{path}')
    needle = b"        if row.get('record_upload_sessions'):\n            return 'producer_pending'"
    assert source.count(needle) == 1
    patched = source.replace(
        needle,
        b"        if row.get('record_upload_sessions'):\n            tx.update(ref, {'record_upload_sessions': {}, 'record_audio_closed': True})\n            return None",
    )
    blob = git(clone, 'hash-object', '-w', '--stdin', data=patched).decode()
    git(clone, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{path}')
    tree = git(clone, 'write-tree').decode()
    ref = git(
        clone,
        '-c',
        'user.name=Replay proof',
        '-c',
        'user.email=replay-proof@example.invalid',
        'commit-tree',
        tree,
        '-p',
        base,
        data=b'Synthetic gate proof only\n',
    ).decode()
    directory = tmp_path / 'private-case'
    shutil.copytree(FIXTURES / 'capture-open-upload-session', directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    # Also exercise Tier C external paths with private manifest and corpus text.
    manifest.update(tier='C', id='OWNER-PRIVATE-CANARY', scrub='PRIVATE-TEXT-CANARY', notes='PRIVATE-TEXT-CANARY')
    manifest['gate'] = {'fixed_by_ref': True}
    corpus_path = directory / 'corpus.json'
    corpus = json.loads(corpus_path.read_text())
    corpus['conversation']['transcript_segments'][0]['text'] = 'PRIVATE-TEXT-CANARY'
    corpus_path.write_text(json.dumps(corpus))
    manifest['seed_blob_sha256'] = [
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [corpus_path, *sorted((directory / 'cassettes').iterdir())]
    ]
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    output = evidence_output(tmp_path, 'synthetic-fixed')
    assert gate(clone, [directory], ref, base, output) == 0
    result = json.loads((output / 'gate.json').read_text())
    assert result['cases'][0]['classification'] == 'fixed'
    assert result['cases'][0]['fixed_by_ref']
    assert result['verdict'] == 'PASS'
    assert result['cases'][0]['identity_scheme'] == 'hmac-sha256'
    assert 'corpus_sha256' not in result['cases'][0]
    exposed = (output / 'gate.json').read_text() + (output / 'gate.md').read_text() + capsys.readouterr().out
    assert 'OWNER-PRIVATE-CANARY' not in exposed and 'PRIVATE-TEXT-CANARY' not in exposed
    assert set(p.name for p in output.iterdir()) == {'gate.json', 'gate.md', 'identity.key'}


@pytest.mark.parametrize('hard_kill', [False, True])
def test_timeout_cleans_emulator_and_scratch(tmp_path, hard_kill):
    from testing.replay_harness.gate import run_side
    from testing.replay_harness.manifest import load_case
    from testing.replay_snapshot import backend_snapshot, resolve_refs
    from urllib.error import HTTPError
    from urllib.request import Request, ProxyHandler, build_opener

    marker = tmp_path / 'observed.json'
    unwound = tmp_path / 'unwound'
    worker = tmp_path / 'timeout_worker.py'
    fixed_worker = ROOT / 'backend/testing/replay_harness/gate_worker.py'
    # Use the actual environment and write journal, but block indefinitely after
    # creating an owned namespace row, a synthetic user and local scratch.
    worker.write_text(f'''import asyncio, importlib.util, json, pathlib, signal, sys
spec = importlib.util.spec_from_file_location('worker', {str(fixed_worker)!r})
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
backend = pathlib.Path(sys.argv[sys.argv.index('--backend') + 1])
worker.configure_imports(backend)
from testing.replay_harness import runner
from testing.replay_harness.env import replay_environment
async def stuck(_):
    try:
        with replay_environment() as environment:
            user = environment.harness.seed_user('timeout-proof')
            environment.harness.replay_users = [user]
            job = environment.store.client.collection(environment.store.namespace + '_jobs').document('proof')
            job.set({{'state': 'ready'}})
            # A global row deliberately has no normal environment cleanup hook;
            # the parent must remove it from the pre-commit journal on timeout.
            global_ref = environment.store.client.collection('timeout_proof_global').document(user)
            global_ref.set({{'synthetic': True}})
            pathlib.Path({str(marker)!r}).write_text(json.dumps({{'documents': [job.path, 'users/' + user, global_ref.path], 'scratch': str(environment.storage.root)}}))
            await asyncio.Event().wait()
    finally:
        pathlib.Path({str(unwound)!r}).write_text('cooperative exit')
runner.run_cases = stuck
if {hard_kill!r}:
    async def ignore_term(request):
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, lambda: None)
        return await worker.replay(request)
    worker.cooperative_replay = ignore_term
worker.main()
''')
    output = tmp_path / 'timeout-output'
    output.mkdir(mode=0o700)
    sha = resolve_refs(ROOT, 'HEAD', 'HEAD')['candidate']
    with pytest.raises(subprocess.TimeoutExpired):
        with backend_snapshot(ROOT, sha, output, 'timeout') as backend:
            run_side(backend, [load_case(FIXTURES / 'admission-control')], 3, timeout=15, grace=2, worker=worker)
    observed = json.loads(marker.read_text())
    assert unwound.exists() is not hard_kill
    assert not Path(observed['scratch']).exists()
    assert not list(output.iterdir())
    endpoint = os.environ['FIRESTORE_EMULATOR_HOST']
    for path in observed['documents']:
        with pytest.raises(HTTPError) as error:
            build_opener(ProxyHandler({})).open(
                Request(
                    f'http://{endpoint}/v1/projects/demo-omi-isolated-tests/databases/(default)/documents/{path}',
                    headers={'Authorization': 'Bearer owner'},
                ),
                timeout=5,
            )
        assert error.value.code == 404


def test_config_only_privacy_fix_is_rendered_from_each_archive(tmp_path):
    clone = tmp_path / 'config-clone'
    subprocess.run(['git', 'clone', '--shared', '--no-checkout', '--quiet', str(ROOT), str(clone)], check=True)
    candidate = git(clone, 'rev-parse', 'HEAD').decode()
    git(clone, 'read-tree', candidate)
    path = 'backend/deploy/runtime_env/_base.yaml'
    source = git(clone, 'show', f'{candidate}:{path}')
    # Only backend's single subscription TTL differs. The generated manifest
    # stays identical, proving the archive's composition inputs are authoritative.
    start = source.index(b'      backend:\n', source.index(b'  cloud_run:\n'))
    end = source.index(b'      backend-sync:\n', start)
    needle = b"FSR_SUBSCRIPTION_TTL_SECONDS:\n            value: '55'"
    assert source[start:end].count(needle) == 1
    patched = source[:start] + source[start:end].replace(needle, needle.replace(b"'55'", b"'60'")) + source[end:]
    blob = git(clone, 'hash-object', '-w', '--stdin', data=patched).decode()
    git(clone, 'update-index', '--cacheinfo', f'100644,{blob},{path}')
    tree = git(clone, 'write-tree').decode()
    base = git(
        clone,
        '-c',
        'user.name=Replay proof',
        '-c',
        'user.email=replay@example.invalid',
        'commit-tree',
        tree,
        '-p',
        candidate,
        data=b'Config-only 60s baseline proof\n',
    ).decode()
    assert git(clone, 'diff-tree', '--no-commit-id', '--name-only', '-r', candidate, base).decode() == path
    directory = tmp_path / 'privacy-config-case'
    shutil.copytree(FIXTURES / 'privacy-transitions-smoke', directory)
    corpus = {
        'privacy_cache': {
            'transitions': [{'family': 'subscription', 'kind': 'byok_enable', 'fault': 'drop_invalidation'}]
        }
    }
    corpus_path = directory / 'corpus.json'
    corpus_path.write_text(json.dumps(corpus))
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest['stages']['privacy_cache'] = {
        'expect_stop_stage': 'privacy_cache',
        'expect_reason': 'privacy_cache:staleness_bound_exceeded',
        'min_verified_transitions': 0,
    }
    manifest['gate'] = {'fixed_by_ref': True}
    manifest['seed_blob_sha256'] = [hashlib.sha256(corpus_path.read_bytes()).hexdigest()]
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    output = tmp_path / 'config-only-gate'
    assert gate(clone, [directory], candidate, base, output, runtime_env='backend') == 0
    result = json.loads((output / 'gate.json').read_text())
    assert result['verdict'] == 'PASS' and result['cases'][0]['classification'] == 'fixed'
    row = result['cases'][0]
    before, after = row['baseline']['outcomes'][0], row['candidate']['outcomes'][0]
    assert before['runtime_env'] == after['runtime_env']  # Names only; values never reported.
    assert before['stages'][0]['details']['mismatches'] == 1
    assert after['stages'][0]['details']['mismatches'] == 0
    assert after['stages'][0]['details']['bound_margin_s_by_family']['subscription'] == 5
    assert set(output.iterdir()) == {output / name for name in ('gate.json', 'gate.md', 'identity.key')}
