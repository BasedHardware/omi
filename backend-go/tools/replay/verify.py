"""Check that the two emulator runs prove both parity and drift detection."""

import json
from pathlib import Path
import sys


def main():
    parity_path, gaps_path = map(Path, sys.argv[1:])
    parity = json.loads(parity_path.read_text())
    assert parity['matched_cases'] == len(parity['cases']) >= 10, parity['matched_cases']
    assert parity['unexplained_differences'] == parity['failed_cases'] == 0
    assert all('python' not in case and 'go' not in case for case in parity['cases'])

    gaps = json.loads(gaps_path.read_text())
    assert gaps['unexplained_differences'] > 0 and gaps['failed_cases'] == 0, gaps['failed_cases']
    by_name = {case['name']: case for case in gaps['cases']}
    kept = by_name['kept-with-effects']
    for side in ('python', 'go'):
        result = kept[side]
        assert result['status'] == 'completed', (side, result['status'])
        assert result['conversation']['structured']['title'] == 'Synthetic replay'
        assert [delivery['app'] for delivery in result['webhooks']] == ['audit', 'fixture'], side
        assert all(delivery['idempotency_key'] and delivery['payload'] for delivery in result['webhooks']), side
        assert any('/replay_vectors/' in path for path in result['derived_documents']), side
        assert any('/replay_memories/' in path for path in result['derived_documents']), side

    paths = {diff['path'] for diff in kept['differences'] if not diff.get('reason')}
    assert any(path.startswith('/conversation/') for path in paths)
    assert any(path.startswith('/derived_documents/') for path in paths)
    assert any(path.startswith('/webhooks/') for path in paths)
    empty = by_name['empty-capture']
    assert empty['python']['status'] == 'no_content'
    assert any(diff['path'] == '/status' for diff in empty['differences'])
    for name in ('compressed-standard', 'enhanced-compressed'):
        for side in ('python', 'go'):
            assert by_name[name][side]['status'] == 'completed', (name, side, by_name[name][side]['status'])


if __name__ == '__main__':
    main()
