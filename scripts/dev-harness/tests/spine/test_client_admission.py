"""C10 admission oracles: declared provenance is binding, not a URL-shaped badge."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('c10_admission', ROOT / 'scripts/check_client_compat.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def test_distribution_attestation_binds_identity_and_review(tmp_path):
    path = 'contracts/client-compat/synthetic-receipt.json'
    file = tmp_path / path
    file.parent.mkdir(parents=True)
    proof = {'version': 1, 'commit': '1' * 40, 'build': 992, 'platforms': ['ios'],
             'provider': 'codemagic', 'artifact_id': 'synthetic-test-only',
             'receipt_url': 'https://codemagic.io/app/synthetic/build/test',
             'reviewer': 'synthetic-owner',
             'review_url': 'https://github.com/BasedHardware/omi/pull/1#pullrequestreview-1'}
    row = {'commit': proof['commit'], 'build': 992, 'platforms': ['ios'],
           'distribution': {'kind': 'distributed', 'receipt_url': proof['receipt_url'], 'attestation': path}}
    def write(value):
        raw = json.dumps(value).encode()
        file.write_bytes(raw)
        row['files'] = {path: hashlib.sha256(raw).hexdigest()}
    write(proof)
    catalog.validate_distribution(row, tmp_path)
    for key, value in [('build', 990), ('commit', '2' * 40), ('platforms', ['android']),
                       ('reviewer', ''), ('review_url', 'https://example.invalid/review'),
                       ('receipt_url', 'https://example.invalid/distributed'), ('artifact_id', '')]:
        bad = copy.deepcopy(proof)
        bad[key] = value
        write(bad)
        with pytest.raises(ValueError):
            catalog.validate_distribution(row, tmp_path)
    write(proof)
    file.write_text('{}')
    with pytest.raises(ValueError, match='hash'):
        catalog.validate_distribution(row, tmp_path)
    write(proof)
    del row['distribution']['attestation']
    with pytest.raises(ValueError, match='attestation'):
        catalog.validate_distribution(row, tmp_path)


@pytest.mark.parametrize('commit', ['820379296f5a7ad98c8ab873f18aba9b522785ac', '09d9cae314f39fbd9e0f972a2465af754148b052'])
def test_source_pinned_candidate_queries_not_just_four_path_strings(commit):
    expected = {
        '/v1/conversations': [['include_discarded', 'true'], ['limit', '50'], ['offset', '0'], ['statuses', '']],
        '/v3/memories': [['limit', '100'], ['offset', '0']],
        '/v2/messages': [['app_id', ''], ['dropdown_selected', 'false']],
        '/v1/action-items': [['limit', '50'], ['offset', '0']],
    }
    cases = [{'request': {'path': path, 'query': query}} for path, query in expected.items()]
    catalog.validate_candidate_queries(commit, cases)
    for index in range(len(cases)):
        bad = copy.deepcopy(cases)
        bad[index]['request']['query'] = [['limit', '50'], ['offset', '9']]
        with pytest.raises(ValueError, match='source-pinned'):
            catalog.validate_candidate_queries(commit, bad)
    bad = copy.deepcopy(cases)
    bad[2]['request']['query'].extend([['limit', '50'], ['offset', '0']])
    with pytest.raises(ValueError, match='source-pinned'):
        catalog.validate_candidate_queries(commit, bad)
