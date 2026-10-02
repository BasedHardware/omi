"""C10 loader must preserve admitted frozen vectors, not substitute HEAD defaults."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dev_harness import client_compat as compat
from .pending import pending


@pending('C10')
def test_registered_cases_equal_every_frozen_request_not_only_endpoint_names():
    root = Path(__file__).resolve().parents[4]
    rows = json.loads((root / 'contracts/client-compat/catalog.json').read_text())['releases']
    assert rows, 'real capture admission remains pending after synthetic engine acceptance'
    expected = []
    for row in rows:
        vectors = json.loads((root / row['cases']).read_text())
        assert vectors
        for vector in vectors:
            request = vector['request']
            expected.append(compat.Case(
                row['id'], vector['platform'], vector['id'],
                compat.Request(request['method'], request['path'], tuple(map(tuple, request['query'])),
                               tuple(map(tuple, request['headers'])), request['body'].encode('utf-8')),
                vector['decoder'], vector['observations'], vector['status']))
    assert list(compat.registered_cases(root, supported_only=False)) == expected
