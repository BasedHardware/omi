"""Synthetic product encryption -> captured shape -> real durable titling worker."""

import asyncio
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'backend/testing/replay_harness/fixtures/titling-control'


@pytest.fixture
def encrypted_case(tmp_path):
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback emulator required')
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.decryption import quiet_product

    uid = 'synthetic-owner-' + secrets.token_hex(16)
    secret = secrets.token_hex(32)
    plaintext = 'PRIVATE-TRANSCRIPT-' + secrets.token_hex(16)
    corpus = json.loads((FIXTURE / 'corpus.json').read_text())
    corpus['conversation']['data_protection_level'] = 'enhanced'
    corpus['conversation']['transcript_segments'][0]['text'] += ' ' + plaintext
    # Real product encoder: compressed JSON then per-owner encryption.
    with quiet_product(), replay_environment(), ExitStack() as stack:
        from database import conversations
        from utils import encryption

        stack.enter_context(patch.object(encryption, 'ENCRYPTION_SECRET', secret.encode()))
        stack.enter_context(patch.object(encryption, '_DERIVED_KEY_CACHE', {}))
        corpus['conversation'] = conversations.encode_conversation_for_write(uid, corpus['conversation'], 'enhanced')
    corpus['source'] = 'firestore-owner-ciphertext'
    corpus['owner_sha256'] = hashlib.sha256(uid.encode()).hexdigest()
    directory = tmp_path / 'case'
    directory.mkdir(mode=0o700)
    (directory / 'cassettes').mkdir()
    (directory / 'corpus.json').write_text(json.dumps(corpus, default=lambda value: value.isoformat()))
    manifest = json.loads((FIXTURE / 'manifest.json').read_text())
    manifest.update(tier='C', scrub='owner-tokenized-ciphertext', seed_blob_sha256=[], notes=plaintext)
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    cassette = json.loads((FIXTURE / 'cassettes/titling.json').read_text())
    # Derived output must also stay in memory, even when the provider returns content.
    cassette.update(title=plaintext, overview=plaintext)
    (directory / 'cassettes/titling.json').write_text(json.dumps(cassette))
    files = {}
    for name, body in [('secret', secret), ('uid', uid), ('consent', corpus['owner_sha256'])]:
        path = tmp_path / name
        path.write_text(body + '\n')
        path.chmod(0o600)
        files[name + '_file'] = path
    return directory, files, [secret, uid, plaintext]


def assert_private(output, streams, canaries):
    bodies = [streams, *(p.read_bytes() for p in output.rglob('*') if p.is_file())]
    assert all(value.encode() not in body for value in canaries for body in bodies)


def run_cli(directory, output, files):
    command = [sys.executable, '-m', 'testing.replay_harness', 'run', '--case', str(directory), '--output', str(output)]
    for name, path in files.items():
        command.extend(['--' + name.replace('_', '-'), str(path)])
    return subprocess.run(command, cwd=ROOT / 'backend', capture_output=True, timeout=180)


def test_encrypted_titling_on_off_and_no_plaintext(encrypted_case, tmp_path):
    directory, files, canaries = encrypted_case
    off_output = tmp_path / 'off'
    off = run_cli(directory, off_output, {})
    off_item = json.loads((off_output / 'report.json').read_text())['items'][0]
    assert off_item['stop_reason'] == 'titling:precondition_skipped:recovery_undecoded'
    assert off_item['decryption'] == 'off'
    assert b'decryption: off' in off.stdout
    on_output = tmp_path / 'on'
    on = run_cli(directory, on_output, files)
    assert on.returncode == 0, (on.stdout + on.stderr).decode()
    item = json.loads((on_output / 'report.json').read_text())['items'][0]
    assert item['decryption'] == 'on' and item['verdict'] == 'PASS', item
    assert item['stages'][-1]['details']['llm_calls'] == 1
    assert item['stages'][-1]['details']['final_job_status'] == 'completed'
    assert_private(on_output, on.stdout + on.stderr, canaries)
    assert_private(off_output, off.stdout + off.stderr, canaries)


def test_gate_passes_paths_to_both_workers_without_copying(encrypted_case, tmp_path, capsys):
    from testing.replay_harness.gate import gate

    directory, files, canaries = encrypted_case
    output = tmp_path / 'gate'
    assert gate(ROOT, [directory], 'HEAD', 'HEAD', output, regression_only=True, **files) == 0
    result = json.loads((output / 'gate.json').read_text())
    assert result['decryption'] == 'on'
    assert result['cases'][0]['classification'] == 'unchanged_pass', result
    for side in ('baseline', 'candidate'):
        assert result['cases'][0][side]['outcomes'][0]['decryption'] == 'on'
    captured = capsys.readouterr()
    assert_private(output, (captured.out + captured.err).encode(), canaries)


def test_refusals_are_sanitized(encrypted_case, tmp_path):
    directory, files, canaries = encrypted_case
    files['uid_file'].write_text('wrong-' + secrets.token_hex(16))
    output = tmp_path / 'refused'
    refused = run_cli(directory, output, files)
    assert refused.returncode == 2
    assert not output.exists()
    assert_private(tmp_path / 'nonexistent', refused.stdout + refused.stderr, canaries)


def test_product_artifact_reader_authenticates_original_aad(encrypted_case, tmp_path):
    from dataclasses import replace
    from types import SimpleNamespace
    from testing.replay_harness.decryption import load_decryption, opaque_firestore, product_decryption, quiet_product
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.seed import seed_case

    directory, files, canaries = encrypted_case
    uid = files['uid_file'].read_text().strip()
    secret = files['secret_file'].read_text().strip().encode()
    case = load_case(directory)
    with quiet_product(), opaque_firestore(), replay_environment() as environment:
        from utils.batch_pipeline.artifact_policy import create_artifact_store
        from utils.batch_pipeline.artifacts import ProtectionContext
        from utils.batch_pipeline.contracts import WorkItem, Priority

        original = WorkItem(
            'unit-' + uid,
            uid,
            1800000000.0,
            'gs://replay-staged/audio#1',
            180,
            Priority.FRESH,
            conversation_id=case.corpus['conversation_id'],
            privacy_generation=0,
        )
        context = ProtectionContext('enhanced', 0)
        producer = create_artifact_store(
            SimpleNamespace(namespace='batch_pipeline_prod'), environment.storage, 'replay-staged', secret
        )
        body = json.dumps({'words': [], 'canary': canaries[-1]}).encode()
        sealed = producer._seal(original, 'results', context, body)
        name = producer.owner_prefix(uid) + 'results/' + original.segment_id + '/' + 'a' * 32 + '.enc'
        uri = ('gs://replay-staged/' + name + '#7').replace(uid, case.corpus['owner_token'])
        (directory / 'blobs').mkdir()
        (directory / 'blobs/result.enc').write_bytes(sealed)
        case = replace(
            case, corpus={**case.corpus, 'blob_refs': [dict(status='captured', uri=uri, path='blobs/result.enc')]}
        )
        with product_decryption(case, environment, load_decryption(**files)):
            seed_case(case, environment)
            item = replace(
                original,
                owner_id=environment.replay_uid,
                conversation_id=environment.replay_cid,
                segment_id=original.segment_id.replace(uid, case.corpus['owner_token']),
            )
            reader = create_artifact_store(environment.store, environment.storage, 'replay-staged', b'x' * 32)
            reader.authorize = lambda ignored: context
            assert reader.load_result(item, uri)['canary'] == canaries[-1]
            # The same key with different AAD must fail authentication.
            from cryptography.exceptions import InvalidTag

            with pytest.raises(InvalidTag):
                reader.load_result(replace(item, duration_seconds=181), uri)


def test_plaintext_never_reaches_firestore_wire_or_error_receipts(encrypted_case, tmp_path, monkeypatch, capfd):
    from testing.replay_harness.decryption import opaque_firestore, quiet_product
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.report import write_report
    from testing.replay_harness.stages.finalization import TitlingDriver

    directory, files, canaries = encrypted_case
    value = ' '.join(canaries)
    with quiet_product(), opaque_firestore(), replay_environment() as environment:
        api = environment.store.client._firestore_api
        original = api.commit
        requests = []

        def commit(*args, **kwargs):
            requests.append(repr(kwargs.get('request', args[0] if args else None)).encode())
            return original(*args, **kwargs)

        with patch.object(api, 'commit', commit):
            uid = environment.harness.seed_user('synthetic-wire')
            environment.harness.replay_users = [uid]
            ref = environment.store.client.collection('users').document(uid)
            ref.update({'sensitive': value, 'sensitive_bytes': value.encode()})
            assert ref.get().to_dict()['sensitive'] == value
            assert ref.get().to_dict()['sensitive_bytes'] == value.encode()
            matches = list(ref.parent.where('sensitive', '==', value).stream())
            assert [doc.id for doc in matches] == [uid]
        assert requests and all(canary.encode() not in wire for wire in requests for canary in canaries)

    async def fail(*args, **kwargs):
        import logging

        print(value)
        os.write(2, value.encode())
        logging.error(value)
        raise ValueError(value)

    monkeypatch.setattr(TitlingDriver, 'run', fail)
    items = asyncio.run(run_cases([directory], **files))
    assert items[0]['stages'][-1]['exception_type'] == 'ValueError'
    output = tmp_path / 'error-output'
    write_report(items, output)
    captured = capfd.readouterr()
    assert_private(output, (captured.out + captured.err).encode(), canaries)
