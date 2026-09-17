"""C10 builder oracle. Fake transport tests engine only; backend oracle is separate."""
import json
import base64
import hashlib
import os
import re
import subprocess
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dev_harness import client_compat as compat
from .pending import pending

ROOT = Path(__file__).resolve().parents[4]


def case(name='list'):
    return compat.Case('synthetic-client-1', 'ios', name,
                       compat.Request('GET', '/v1/conversations', (('statuses', ''), ('limit', '50')),
                                      (('X-App-Version', '1.0.543'),), b''),
                       'frozen-v1', {'id': 'synthetic-conversation'})


def decode(decoder, response):
    assert decoder == 'frozen-v1'
    value = json.loads(response.body)
    if not isinstance(value.get('id'), str):
        raise ValueError('/id: required string')
    return {'id': value['id']}


@pending("C10")
def test_exact_request_and_current_response_reach_frozen_decoder_once():
    sent, decoded = [], []
    c = case()
    def send(request):
        sent.append(request)
        return compat.Response(200, {'content-type': 'application/json'}, b'{"id":"synthetic-conversation","new_optional":true}')
    def observe(key, response):
        decoded.append(response.body)
        return decode(key, response)
    result = compat.replay([c], send=send, decode=observe)
    assert result == compat.ReplayResult(1, ())
    assert sent == [c.request]
    assert decoded == [b'{"id":"synthetic-conversation","new_optional":true}']


@pending("C10")
@pytest.mark.parametrize('body', [b'{}', b'{"id":null}', b'{"id":42}', b'{"id":"wrong-sentinel"}', b'', b'not-json'])
def test_nonempty_semantic_observations_not_just_decodability(body):
    result = compat.replay([case()], send=lambda _: compat.Response(200, {'content-type': 'application/json'}, body), decode=decode)
    assert result.executed == 1
    assert len(result.issues) == 1
    assert result.issues[0].release == 'synthetic-client-1'
    assert result.issues[0].platform == 'ios'
    assert result.issues[0].case == 'list'
    assert result.issues[0].pointer


@pending("C10")
def test_failure_does_not_retry_or_hide_remaining_cases():
    sent = []
    def send(request):
        sent.append(request)
        return compat.Response(503 if len(sent) == 1 else 200, {'content-type': 'application/json'}, b'{"id":"synthetic-conversation"}')
    result = compat.replay([case('one'), case('two')], send=send, decode=decode)
    assert len(sent) == result.executed == 2
    assert [i.case for i in result.issues] == ['one']


@pending("C10")
def test_no_execution_cannot_report_compatibility():
    result = compat.replay([], send=lambda _: pytest.fail('no case to send'), decode=decode)
    assert result.executed == 0
    assert result.issues


@pending("C10")
def test_two_confirmed_releases_cover_first_four_endpoint_families():
    catalog = json.loads((ROOT / 'contracts/client-compat/catalog.json').read_text())
    assert len(catalog['releases']) >= 2, 'C10: build tags are not confirmed distributed fixtures'
    assert len({row['build'] for row in catalog['releases'][:2]}) == 2, 'two captures of one build are not two releases'
    cases = compat.registered_cases(ROOT, supported_only=False)
    for row in catalog['releases'][:2]:
        assert row['distribution']['kind'] == 'distributed'
        for platform in row['platforms']:
            paths = {c.request.path for c in cases if c.release == row['id'] and c.platform == platform}
            assert paths >= {'/v1/conversations', '/v3/memories', '/v2/messages', '/v1/action-items'}
            assert all(c.observations for c in cases if c.release == row['id'])


@pending("C10")
def test_ci_release_wiring_selects_fixture_only_changes(tmp_path):
    # Execute the existing job's actual scope shell with a read-only Git stub.
    workflow = (ROOT / '.github/workflows/backend-hermetic-e2e.yml').read_text()
    block = next(block for block in re.findall(r'        run: \|\n((?:          .*\n|\n)+)', workflow)
                 if 'changed_files=' in block)
    script = '\n'.join(line[10:] for line in block.splitlines())
    git = tmp_path / 'git'
    git.write_text('#!/bin/sh\ncase "$1" in\ncat-file) exit 0;;\ndiff) printf "%s\\n" "$CASE_PATH";;\n*) exit 2;;\nesac\n')
    git.chmod(0o755)
    for path, expected in [('contracts/client-compat/catalog.json', 'true'),
                           ('scripts/dev-harness/dev_harness/client_compat.py', 'true'),
                           ('backend/routers/conversations.py', 'true'), ('README.md', 'false')]:
        output = tmp_path / 'output'
        output.write_text('')
        env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'],
                   EVENT_NAME='pull_request', PR_BASE_REF='origin/main', GITHUB_OUTPUT=str(output), CASE_PATH=path)
        result = subprocess.run(['bash', '-c', script], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert output.read_text().strip() == 'applies=' + expected, path


@pending("C10")
def test_unproven_minimum_cannot_silently_select_no_supported_clients(tmp_path):
    directory = tmp_path / 'contracts/client-compat'
    directory.mkdir(parents=True)
    (directory / 'catalog.json').write_text('{"version":1,"releases":[]}')
    (directory / 'support-policy.json').write_text(json.dumps({
        'version': 1, 'minimum_build': {'ios': 999999, 'android': 999999}, 'enforcement_receipt': None}))
    with pytest.raises(ValueError, match='enforcement|rollout|minimum'):
        compat.registered_cases(tmp_path)


def decoder_fixture(root):
    path = 'contracts/client-compat/releases/synthetic/decoder.dart'
    file = root / path
    file.parent.mkdir(parents=True)
    file.write_text('// synthetic frozen decoder fixture\nvoid main() {}\n')
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    (root / 'contracts/client-compat/catalog.json').write_text(json.dumps({'releases': [
        {'id': 'synthetic', 'decoder': path, 'files': {path: digest}}]}))
    return path


@pending("C10")
def test_frozen_decoder_process_receives_current_bytes_and_owns_observations(tmp_path):
    path = decoder_fixture(tmp_path)
    response = compat.Response(200, {'content-type': 'application/json'}, b'{"id":"synthetic"}')
    calls = []
    def execute(argv, stdin):
        calls.append((argv, stdin))
        assert str((tmp_path / path).resolve()) in argv
        assert json.loads(stdin) == {'status': 200, 'headers': dict(response.headers),
                                    'body_base64': base64.b64encode(response.body).decode()}
        return b'{"id":"decoder-owned-sentinel","legacy_default":17}'
    assert compat.decode_released(tmp_path, path, response, execute=execute) == {
        'id': 'decoder-owned-sentinel', 'legacy_default': 17}
    assert len(calls) == 1


@pending("C10")
def test_tampered_decoder_never_executes(tmp_path):
    path = decoder_fixture(tmp_path)
    (tmp_path / path).write_text('void main() { print("forged"); }')
    calls = []
    with pytest.raises(ValueError, match='hash|digest|tamper'):
        compat.decode_released(tmp_path, path, compat.Response(200, {}, b'{}'),
                               execute=lambda *args: calls.append(args))
    assert calls == []


@pending("C10")
@pytest.mark.parametrize('output', [b'[]', b'not-json'])
def test_decoder_process_failure_cannot_mean_empty_account(tmp_path, output):
    path = decoder_fixture(tmp_path)
    with pytest.raises(ValueError):
        compat.decode_released(tmp_path, path, compat.Response(200, {}, b'{}'), execute=lambda *args: output)


@pending("C10")
def test_transport_timeout_is_reported_once_not_retried():
    calls = []
    def send(request):
        calls.append(request)
        raise TimeoutError('synthetic timeout')
    result = compat.replay([case()], send=send, decode=lambda *args: pytest.fail('no response to decode'))
    assert result.executed == len(calls) == 1
    assert len(result.issues) == 1
    assert result.issues[0].case == 'list'
