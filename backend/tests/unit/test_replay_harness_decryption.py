"""Import-light consent and private-input guards; no real data or keys."""

from dataclasses import replace
import hashlib
from pathlib import Path
import secrets
import time

import pytest

from testing.replay_harness.decryption import load_decryption
from testing.replay_harness.guard import CaptureRefused
from testing.replay_harness.manifest import load_case

FIXTURE = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures/titling-control'


@pytest.fixture(autouse=True)
def cpu_guard():
    started = time.process_time()
    yield
    assert time.process_time() - started < 1.00


@pytest.fixture
def inputs(tmp_path):
    uid = 'synthetic-' + secrets.token_hex(16)
    values = {'uid': uid, 'secret': secrets.token_hex(32), 'consent': hashlib.sha256(uid.encode()).hexdigest()}
    paths = {}
    for name, value in values.items():
        path = tmp_path / name
        path.write_text(value + '\n')
        path.chmod(0o600)
        paths[name + '_file'] = path
    return paths, values


def case_for(pin):
    case = load_case(FIXTURE)
    return replace(case, manifest=replace(case.manifest, tier='C'), corpus={**case.corpus, 'owner_sha256': pin})


def test_opt_in_and_case_pin(inputs):
    paths, values = inputs
    assert load_decryption() is None
    credentials = load_decryption(**paths)
    credentials.validate(case_for(values['consent']))
    assert values['uid'] not in repr(credentials) and values['secret'] not in repr(credentials)
    with pytest.raises(CaptureRefused):
        credentials.validate(case_for('0' * 64))
    with pytest.raises(CaptureRefused):
        credentials.validate(case_for(None))


@pytest.mark.parametrize('name', ['uid', 'secret', 'consent'])
@pytest.mark.parametrize('mode', [0o644, 0o400, 0o660])
def test_requires_exact_private_mode(inputs, name, mode):
    paths, _ = inputs
    paths[name + '_file'].chmod(mode)
    with pytest.raises(CaptureRefused):
        load_decryption(**paths)


@pytest.mark.parametrize('name', ['uid', 'secret', 'consent'])
def test_requires_complete_inputs(inputs, name):
    paths, _ = inputs
    paths[name + '_file'] = None
    with pytest.raises(CaptureRefused):
        load_decryption(**paths)


def test_wrong_consent_and_symlinks(inputs, tmp_path):
    paths, _ = inputs
    paths['consent_file'].write_text('0' * 64)
    with pytest.raises(CaptureRefused):
        load_decryption(**paths)
    alias = tmp_path / 'alias'
    alias.symlink_to(paths['secret_file'])
    with pytest.raises(CaptureRefused):
        load_decryption(secret_file=alias, uid_file=paths['uid_file'], consent_file=paths['consent_file'])


def test_restores_capture_bytes_for_product_decompression():
    from testing.replay_harness.seed import restore_dates
    import base64

    value = b'synthetic-compressed-field'
    assert restore_dates({'_firestore_bytes_base64': base64.b64encode(value).decode()}) == value


def test_secret_preserves_significant_spaces(inputs):
    paths, values = inputs
    body = ' ' + values['secret'] + ' '
    paths['secret_file'].write_text(body + '\n')
    assert load_decryption(**paths).secret == body.encode()


@pytest.mark.parametrize('source', ['result', 'artifact', 'blob_ref'])
def test_legacy_pin_and_conflicting_owner_are_checked(inputs, source):
    paths, values = inputs
    case = case_for(None)
    pin = values['consent']
    uri = 'gs://synthetic/batch-pipeline/batch_pipeline_prod/owners/' + pin + '/results/unit/file.enc#1'
    corpus = dict(case.corpus)
    if source == 'result':
        corpus['results'] = {'unit': {'owner_key': pin}}
    elif source == 'artifact':
        corpus['artifacts'] = {'artifact': {'uri': uri}}
    else:
        corpus['blob_refs'] = [{'uri': uri}]
    credentials = load_decryption(**paths)
    credentials.validate(replace(case, corpus=corpus))
    with pytest.raises(CaptureRefused):
        credentials.validate(replace(case, corpus={**corpus, 'owner_sha256': '0' * 64}))
