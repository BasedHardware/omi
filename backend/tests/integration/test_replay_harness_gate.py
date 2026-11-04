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


def test_identical_refs(tmp_path):
    output = evidence_output(tmp_path, 'identical')
    assert gate(ROOT, sorted(FIXTURES.iterdir()), 'HEAD', 'HEAD', output) == 0
    result = json.loads((output / 'gate.json').read_text())
    assert result['verdict'] == 'PASS'
    assert not {'fixed', 'regressed'} & {r['classification'] for r in result['cases']}
    stress = next(r for r in result['cases'] if len(r['baseline']['outcomes']) > 1)
    assert len(stress['baseline']['outcomes']) == len(stress['candidate']['outcomes']) == 3
    assert set(p.name for p in output.iterdir()) == {'gate.json', 'gate.md'}


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
    exposed = (output / 'gate.json').read_text() + (output / 'gate.md').read_text() + capsys.readouterr().out
    assert 'OWNER-PRIVATE-CANARY' not in exposed and 'PRIVATE-TEXT-CANARY' not in exposed
    assert set(p.name for p in output.iterdir()) == {'gate.json', 'gate.md'}
