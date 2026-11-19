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
    py, candidate = kept['python'], kept['go']
    for result in (py, candidate):
        assert result['status'] == 'completed', result['status']
        assert result['conversation']['structured']['title'] == 'Synthetic replay'
        assert all(delivery['payload'] for delivery in result['webhooks'])
        assert 'conversation_vector' in result['effects']
        assert {'conv-structure', 'memory-l1'}.issubset(result['provider_calls'])
    assert [delivery['app'] for delivery in py['webhooks']] == ['audit', 'developer-created', 'fixture']
    assert [delivery['app'] for delivery in candidate['webhooks']] == ['audit', 'fixture']
    assert py['conversation']['apps_results'] == [{'app_id': 'fixture', 'content': 'Synthetic app summary.'}]
    assert py['conversation']['folder_id'] == 'replay-folder'
    assert py['derived_documents']['users/replay-kept-with-effects/goals/replay-goal']['current_value'] == 2
    for collection in ('action_items', 'memory_items'):
        assert any(f'/{collection}/' in path for path in py['derived_documents']), collection
    assert any('/replay_memories/' in path for path in candidate['derived_documents'])
    assert not any(diff['kind'] == 'invalid_binding' for case in gaps['cases'] for diff in case['differences'])
    for side in ('python', 'go'):
        own_key = by_name['own-key-resume'][side]
        assert own_key['admitted']['own_key'] and own_key['status'] == 'completed', side

    assert 'openai-embeddings' in py['provider_calls']
    assert {
        'path': '/provider_calls/openai-embeddings',
        'kind': 'missing_in_go',
    } in kept['differences']
    unported = {diff['path'] for diff in kept['differences'] if diff['kind'] == 'unported'}
    assert '/webhooks/developer-created' in unported
    assert '/conversation/apps_results' in unported
    assert any('~1memory_items~1' in path for path in unported)
    assert any('~1action_items~1' in path for path in unported)
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
