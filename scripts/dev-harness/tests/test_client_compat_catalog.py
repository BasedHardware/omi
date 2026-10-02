"""Active adopted-shape checks: ordinary uncaptured backend evolution stays free."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('client_catalog', ROOT / 'scripts/check_client_compat.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def projection():
    return {'openapi': '3.1.0', 'paths': {'/v1/conversations': {'get': {
        'parameters': [{'in': 'query', 'name': 'limit', 'required': False, 'schema': {'type': 'integer'}}],
        'responses': {'200': {'content': {'application/json': {'schema': {
            'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'string'}, 'optional': {'type': 'string'}}
        }}}}}
    }}}}


def test_only_adopted_request_and_response_shapes_constrain_head():
    old = projection()
    head = copy.deepcopy(old)
    head['paths']['/brand-new-unused'] = {'get': {}}
    schema = head['paths']['/v1/conversations']['get']['responses']['200']['content']['application/json']['schema']
    schema['properties']['additive'] = {'type': 'boolean'}
    assert catalog.compare_projection(old, head) == []
    schema['properties']['id'] = {'type': 'integer'}
    assert any('id' in issue for issue in catalog.compare_projection(old, head))
    head = copy.deepcopy(old)
    head['paths']['/v1/conversations']['get']['parameters'].append({'in': 'query', 'name': 'new_required', 'required': True, 'schema': {'type': 'string'}})
    assert catalog.compare_projection(old, head)
    assert catalog.compare_projection({'paths': {}}, head) == []


def test_no_retirement_without_server_minimum_and_both_platforms():
    policy = json.loads((ROOT / catalog.POLICY).read_text())
    release = {'build': 990, 'platforms': ['ios', 'android']}
    assert catalog.supported(release, policy)
    policy['minimum_build']['ios'] = 991
    assert catalog.supported(release, policy)
    assert catalog.validate_catalog({'releases': []}, policy)
    policy['minimum_build']['android'] = 991
    assert not catalog.supported(release, policy)
    assert catalog.validate_catalog({'releases': []}, policy), 'policy alone is not server retirement proof'


def test_captured_release_rows_cannot_be_deleted_or_rewritten():
    policy = json.loads((ROOT / catalog.POLICY).read_text())
    assert catalog.validate_catalog({'releases': []}, policy, prior={'releases': [{'id': 'old'}]})


def test_fixture_paths_cannot_escape(tmp_path):
    for path in ('../escape', '/tmp/escape', 'contracts/client-compat/../../escape'):
        try:
            catalog.safe_file(tmp_path, path)
        except ValueError:
            continue
        assert False, path


def test_candidates_are_not_mislabeled_releases():
    doc = json.loads((ROOT / 'contracts/client-compat/candidate-source.json').read_text())
    assert len(doc['candidates']) == 2
    assert all(c['distribution'] == 'unverified-build-candidate' for c in doc['candidates'])


def test_case_schema_is_executable_and_preserves_duplicates():
    schema = json.loads((ROOT / 'contracts/client-compat/case.schema.json').read_text())
    case = {'id': 'one', 'platform': 'ios', 'decoder': 'frozen', 'observations': {'id': 'synthetic'}, 'status': 200,
            'request': {'method': 'GET', 'path': '/v1/conversations', 'query': [['statuses', ''], ['statuses', 'processing']], 'headers': [], 'body': ''}}
    catalog.validate_case(case, schema)
    bads = []
    for key, value in [('path', 'https://example.invalid'), ('method', 'POST'), ('query', {}), ('headers', [['Authorization', 'real-secret']]), ('body', '{}')]:
        bad = copy.deepcopy(case)
        bad['request'][key] = value
        bads.append(bad)
    for bad in bads:
        try:
            catalog.validate_case(bad, schema)
        except ValueError:
            continue
        assert False, bad


def test_optional_removal_and_safer_response_type_pass_but_null_widening_fails():
    old = projection()
    head = copy.deepcopy(old)
    shape = head['paths']['/v1/conversations']['get']['responses']['200']['content']['application/json']['schema']
    del shape['properties']['optional']
    assert not catalog.compare_projection(old, head)
    shape['properties']['id']['type'] = ['string', 'null']
    assert catalog.compare_projection(old, head)
    assert not catalog.compare_projection(head, old)


def test_fixture_bytes_and_released_source_are_pinned(tmp_path):
    import hashlib
    import subprocess
    directory = tmp_path / 'contracts/client-compat/releases/synthetic'
    directory.mkdir(parents=True)
    files = {'projection.json': json.dumps(projection()), 'decoder.dart': 'void main() {}', 'cases.json': json.dumps([
        {'id': 'one', 'platform': 'ios', 'decoder': 'decoder.dart', 'observations': {'id': 'synthetic'}, 'status': 200,
         'request': {'method': 'GET', 'path': '/v1/conversations', 'query': [], 'headers': [], 'body': ''}}])}
    for name, body in files.items():
        (directory / name).write_text(body)
    paths = {name: str((directory / name).relative_to(tmp_path)) for name in files}
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'show', f'{sha}:AGENTS.md'], cwd=ROOT)
    row = {'id': 'synthetic', 'build': 1, 'platforms': ['ios'], 'commit': sha,
           'distribution': {'kind': 'distributed', 'receipt_url': 'https://example.invalid/synthetic'},
           'files': {paths[name]: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()},
           'source_files': {'AGENTS.md': hashlib.sha256(source).hexdigest()},
           'projection': paths['projection.json'], 'cases': paths['cases.json'], 'decoder': paths['decoder.dart']}
    proof_path = str((directory / 'distribution.json').relative_to(tmp_path))
    proof = {'version': 1, 'commit': sha, 'build': 1, 'platforms': ['ios'],
             'provider': 'codemagic', 'artifact_id': 'synthetic-unit-fixture',
             'receipt_url': 'https://codemagic.io/app/synthetic/build/unit-fixture',
             'reviewer': 'synthetic-owner',
             'review_url': 'https://github.com/BasedHardware/omi/pull/1#pullrequestreview-1'}
    raw = json.dumps(proof).encode()
    (tmp_path / proof_path).write_bytes(raw)
    row['distribution'] = {'kind': 'distributed', 'receipt_url': proof['receipt_url'], 'attestation': proof_path}
    row['files'][proof_path] = hashlib.sha256(raw).hexdigest()
    doc = {'releases': [row]}
    policy = json.loads((ROOT / catalog.POLICY).read_text())
    assert catalog.validate_catalog(doc, policy, tmp_path) == []
    for key, value in [('build', 2), ('commit', '0' * 40), ('platforms', ['android'])]:
        wrong = copy.deepcopy(doc)
        wrong['releases'][0][key] = value
        assert any('attestation' in e for e in catalog.validate_catalog(wrong, policy, tmp_path))
    wrong = copy.deepcopy(doc)
    wrong['releases'][0]['distribution'] = {'kind': 'distributed', 'receipt_url': 'https://example.invalid'}
    assert any('attestation' in e for e in catalog.validate_catalog(wrong, policy, tmp_path))
    widened = copy.deepcopy(doc)
    extra = copy.deepcopy(row)
    extra['id'] = 'synthetic-second-capture'
    widened['releases'].append(extra)
    assert catalog.validate_catalog(widened, policy, tmp_path, prior=doc) == []
    (directory / 'decoder.dart').write_text('void main() { print("fake success"); }')
    assert any('hash mismatch' in e for e in catalog.validate_catalog(doc, policy, tmp_path))
    row['files'][paths['decoder.dart']] = hashlib.sha256((directory / 'decoder.dart').read_bytes()).hexdigest()
    old = copy.deepcopy(doc)
    row['commit'] = '0' * 40
    assert catalog.validate_catalog(doc, policy, tmp_path, prior=old)


def test_retired_shapes_do_not_constrain_head_but_one_supported_platform_does(tmp_path):
    directory = tmp_path / 'contracts/client-compat'
    directory.mkdir(parents=True)
    (directory / 'projection.json').write_text(json.dumps(projection()))
    doc = {'releases': [{'id': 'captured', 'build': 990, 'platforms': ['ios', 'android'],
                         'projection': 'contracts/client-compat/projection.json'}]}
    policy = {'minimum_build': {'ios': 991, 'android': 991}}
    incompatible = {'openapi': '3.1.0', 'paths': {}}
    assert catalog.check_against_head(doc, policy, tmp_path, incompatible) == []
    policy['minimum_build']['android'] = None
    assert catalog.check_against_head(doc, policy, tmp_path, incompatible)


def test_projection_keeps_transitive_refs_and_reports_missing_closure():
    shape = projection()
    response = shape['paths']['/v1/conversations']['get']['responses']['200']['content']['application/json']
    original = response['schema']
    response['schema'] = {'$ref': '#/components/schemas/Response'}
    shape['components'] = {'schemas': {'Response': {'$ref': '#/components/schemas/Actual'}, 'Actual': original}}
    assert catalog.compare_projection(shape, copy.deepcopy(shape)) == []
    missing = copy.deepcopy(shape)
    del missing['components']['schemas']['Actual']
    errors = catalog.compare_projection(missing, shape)
    assert any('unresolved $ref #/components/schemas/Actual' in error and 'closure' in error for error in errors)
    shape['paths']['/unused'] = {'get': {'$ref': '#/missing-unused'}}
    assert catalog.compare_projection(projection(), shape) == []
