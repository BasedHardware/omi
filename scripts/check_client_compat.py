#!/usr/bin/env python3
"""Validate adopted released-client fixtures; no backend imports or network."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'contracts/client-compat/catalog.json'
POLICY = 'contracts/client-compat/support-policy.json'


def load_comparator():
    spec = importlib.util.spec_from_file_location('released_openapi_comparator', ROOT / 'backend/scripts/check_app_client_openapi_compatibility.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.CompatibilityChecker


def safe_file(root, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not name.startswith('contracts/client-compat/'):
        raise ValueError(f'fixture path escapes catalog: {name}')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to((root / 'contracts/client-compat').resolve()):
        raise ValueError(f'fixture symlink escapes catalog: {name}')
    return resolved


def supported(release, policy):
    return any(policy['minimum_build'][p] is None or release['build'] >= policy['minimum_build'][p]
               for p in release['platforms'])


def compare_projection(projection, head):
    # Resolve only captured paths and their closure; unused endpoints stay unrestricted.
    def refs(document, value, pointer, seen):
        if isinstance(value, dict):
            if '$ref' in value:
                ref = value['$ref']
                if not isinstance(ref, str) or not ref.startswith('#/'):
                    raise ValueError(f'{pointer}: external/invalid $ref {ref!r}')
                if ref not in seen:
                    seen.add(ref)
                    target = document
                    try:
                        for part in ref[2:].split('/'):
                            target = target[part.replace('~1', '/').replace('~0', '~')]
                    except (KeyError, TypeError):
                        raise ValueError(f'{pointer}: unresolved $ref {ref}') from None
                    refs(document, target, ref, seen)
            for key, child in value.items():
                refs(document, child, pointer + '/' + key, seen)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                refs(document, child, pointer + '/' + str(index), seen)
    try:
        for name in projection.get('paths', {}):
            refs(projection, projection['paths'][name], name, set())
            refs(head, head.get('paths', {}).get(name, {}), name, set())
        return [str(issue) for issue in load_comparator()(projection, head).check()]
    except ValueError as exc:
        return [f'{exc}; include the transitive local reference closure when capturing the projection']


def validate_distribution(row, root):
    distribution = row['distribution']
    if distribution['kind'] != 'distributed':
        raise ValueError('build tag is not distribution proof')
    path = distribution.get('attestation')
    if not path or path not in row['files']:
        raise ValueError('distribution needs a hash-pinned owner attestation, not just receipt_url')
    raw = safe_file(root, path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['files'][path]:
        raise ValueError('distribution attestation hash mismatch')
    proof = json.loads(raw)
    for key in ('commit', 'build', 'platforms'):
        if proof.get(key) != row[key]:
            raise ValueError(f'distribution attestation {key} does not match capture')
    hosts = {'app-store-connect': 'appstoreconnect.apple.com', 'google-play': 'play.google.com',
             'codemagic': 'codemagic.io'}
    url = urlsplit(proof.get('receipt_url', ''))
    if (proof.get('version') != 1 or proof.get('provider') not in hosts or url.scheme != 'https'
            or url.hostname != hosts.get(proof.get('provider')) or url.username or url.password
            or url.port not in (None, 443) or url.path in ('', '/') or not proof.get('artifact_id')
            or distribution.get('receipt_url') != proof.get('receipt_url')):
        raise ValueError('distribution needs the provider artifact receipt URL/id')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', proof.get('reviewer', '')) or not re.fullmatch(
            r'https://github.com/BasedHardware/omi/pull/[0-9]+#pullrequestreview-[0-9]+', proof.get('review_url', '')):
        raise ValueError('distribution needs a named release owner and exact admission review')


def validate_case(case, schema):
    """Normative stdlib validation of the deliberately small initial case schema."""
    if set(case) != set(schema['required']):
        raise ValueError('case keys must match case.schema.json')
    if any(not isinstance(case[k], str) or not case[k] for k in ('id', 'decoder')):
        raise ValueError('case id/decoder must be nonempty strings')
    if case['platform'] not in schema['properties']['platform']['enum']:
        raise ValueError('unknown platform')
    if type(case['status']) is not int or not 100 <= case['status'] <= 599:
        raise ValueError('invalid HTTP status')
    if not isinstance(case['observations'], dict) or not case['observations']:
        raise ValueError('semantic observations required')
    request = case['request']
    shape = schema['properties']['request']
    if not isinstance(request, dict) or set(request) != set(shape['required']):
        raise ValueError('request keys must match case.schema.json')
    for key in ('method', 'path'):
        if request[key] not in shape['properties'][key]['enum']:
            raise ValueError(f'{key}: not an adopted initial endpoint')
    if request['body'] != '':
        raise ValueError('initial GET fixtures have an empty body')
    for key in ('query', 'headers'):
        if not isinstance(request[key], list) or any(not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(v, str) for v in pair) for pair in request[key]):
            raise ValueError(f'{key}: ordered string pairs required')
    for key, value in request['headers']:
        if key.lower() in ('authorization', 'x-device-id-hash') and value != '<synthetic>':
            raise ValueError('credentials/device identity must use the synthetic placeholder')


def validate_candidate_queries(commit, cases):
    candidates = json.loads((ROOT / 'contracts/client-compat/candidate-source.json').read_text())['candidates']
    candidate = next((row for row in candidates if row['commit'] == commit), None)
    if candidate is None:
        return  # Other builds need their own source-capture review; no HEAD-shaped assumptions.
    defaults = candidate['default_queries']
    for path in {case['request']['path'] for case in cases}:
        if path in defaults and not any(case['request']['path'] == path
                                       and case['request']['query'] == defaults[path] for case in cases):
            raise ValueError(f'{path}: missing source-pinned default request for build candidate; recapture from released source')


def validate_catalog(catalog, policy, root=ROOT, prior=None):
    errors = []
    if set(policy['minimum_build']) != {'ios', 'android'}:
        errors.append('minimum_build must explicitly name ios and android')
    minima = policy['minimum_build']
    if any(v is not None and (type(v) is not int or v < 1) for v in minima.values()):
        errors.append('minimum builds are positive integers or null (no retirement)')
    if any(v is not None for v in minima.values()):
        receipt = policy.get('enforcement_receipt')
        if not isinstance(receipt, dict) or receipt.get('minimum_build') != minima or not receipt.get('rejection_test') or not re.fullmatch(r'https://\S+', receipt.get('rollout_url', '')):
            errors.append('minimum change needs server rollout_url, rejection_test and matching platform minima; upgrader is not enforcement')
    rows = catalog['releases']
    if len({r['id'] for r in rows}) != len(rows):
        errors.append('release ids must be unique')
    if prior:
        if [r['id'] for r in rows[:len(prior['releases'])]] != [r['id'] for r in prior['releases']]:
            errors.append('release history is append-only; retirement is support-policy selection')
        current = {r['id']: r for r in rows}
        for old in prior['releases']:
            if current.get(old['id']) != old:
                errors.append(f"{old['id']}: captured release rows are immutable; archive through support policy, never rewrite/delete")
    for row in rows:
        try:
            if type(row['build']) is not int or row['build'] < 1 or not row['platforms'] or not set(row['platforms']) <= {'ios', 'android'}:
                raise ValueError('invalid build/platforms')
            if not re.fullmatch(r'[0-9a-f]{40}', row['commit']):
                raise ValueError('resolved immutable commit required')
            validate_distribution(row, root)
            for name, digest in row['files'].items():
                if hashlib.sha256(safe_file(root, name).read_bytes()).hexdigest() != digest:
                    raise ValueError(f'{name}: fixture hash mismatch; restore released bytes')
            for name in (row['projection'], row['cases'], row['decoder']):
                if name not in row['files']:
                    raise ValueError(f'{name}: unpinned replay input')
            if not row['source_files']:
                raise ValueError('released source provenance missing')
            for source, digest in row['source_files'].items():
                if Path(source).is_absolute() or '..' in Path(source).parts:
                    raise ValueError('source path escapes repository')
                blob = subprocess.run(['git', 'show', row['commit'] + ':' + source], cwd=ROOT, capture_output=True)
                if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != digest:
                    raise ValueError(f'{source}: released source hash mismatch/missing history')
            cases = json.loads(safe_file(root, row['cases']).read_text())
            if not cases:
                raise ValueError('nonempty request vectors and semantic observations required')
            schema = json.loads((ROOT / 'contracts/client-compat/case.schema.json').read_text())
            for case in cases:
                validate_case(case, schema)
            validate_candidate_queries(row['commit'], cases)
            projection = json.loads(safe_file(root, row['projection']).read_text())
            if not projection.get('paths'):
                raise ValueError('empty consumer projection')
        except (KeyError, ValueError, OSError, TypeError) as exc:
            errors.append(f"{row.get('id', '<release>')}: {exc}")
    return errors


def check_against_head(catalog, policy, root, head):
    issues = []
    for row in catalog['releases']:
        if supported(row, policy):
            projection = json.loads(safe_file(root, row['projection']).read_text())
            issues += [f"{row['id']} {issue}; preserve the used shape or version the endpoint; replay C10, never edit the old fixture" for issue in compare_projection(projection, head)]
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='origin/main')
    args = parser.parse_args()
    catalog = json.loads((ROOT / CATALOG).read_text())
    policy = json.loads((ROOT / POLICY).read_text())
    old = subprocess.run(['git', 'show', f'{args.base}:{CATALOG}'], cwd=ROOT, capture_output=True, text=True)
    errors = validate_catalog(catalog, policy, prior=json.loads(old.stdout) if old.returncode == 0 else None)
    if not errors:
        errors += check_against_head(catalog, policy, ROOT, json.loads((ROOT / 'docs/api-reference/app-client-openapi.json').read_text()))
    for error in errors:
        print(error)
    if not errors:
        active = sum(supported(row, policy) for row in catalog['releases'])
        state = ('PENDING C10 capture/replay (no historical coverage claimed)' if not catalog['releases']
                 else 'adopted projections compatible' if active
                 else 'out of scope under server minimum; no compatibility claim')
        print(f"C10: {len(catalog['releases'])} captured bundles, {active} supported; {state}")
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
