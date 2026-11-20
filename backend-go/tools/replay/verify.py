"""Check that the two emulator runs prove both parity and drift detection."""

from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import sys

# Only substitute known nondeterministic document IDs. Preserve the collection,
# nested field path, difference kind and multiplicity for each reviewed case.
DYNAMIC_DOCUMENT_IDS = {
    'action_items': (r'[A-Za-z0-9]{20}', '<auto-id>'),
    'events': (r'gpe_[0-9a-f]{32}', '<goal-event-id>'),
    'goal_history': (r'\d{4}-\d{2}-\d{2}', '<day>'),
    'hourly_usage': (r'\d{4}-\d{2}-\d{2}-\d{2}', '<hour>'),
    'llm_usage': (r'\d{4}-\d{2}-\d{2}', '<day>'),
    'monthly_usage_totals': (r'\d{4}-\d{2}', '<month>'),
}


def stable_path(path):
    prefix = '/derived_documents/'
    if not path.startswith(prefix):
        return path
    key, separator, field = path.removeprefix(prefix).partition('/')
    parts = key.split('~1')
    for index in range(0, len(parts) - 1, 2):
        replaced = DYNAMIC_DOCUMENT_IDS.get(parts[index])
        if replaced and re.fullmatch(replaced[0], parts[index + 1]):
            parts[index + 1] = replaced[1]
    return prefix + '~1'.join(parts) + separator + field


def drift_signatures(report):
    result = {}
    for case in report['cases']:
        counts = Counter(
            (stable_path(diff['path']), diff['kind']) for diff in case['differences'] if not diff.get('reason')
        )
        canonical = [[path, kind, count] for (path, kind), count in sorted(counts.items())]
        payload = json.dumps(canonical, ensure_ascii=True, separators=(',', ':')).encode()
        result[case['name']] = {'count': sum(counts.values()), 'sha256': hashlib.sha256(payload).hexdigest()}
    return result


def verify_drift(gaps):
    baseline = Path(__file__).with_name('expected-drift.json')
    expected = json.loads(baseline.read_text())
    observed = drift_signatures(gaps)
    changed = sorted(name for name in (expected.keys() | observed.keys()) if expected.get(name) != observed.get(name))
    require(not changed, 'unexpected drift signatures: ' + ', '.join(changed))


def require(condition, detail):
    if not condition:
        raise SystemExit(str(detail))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--print-drift-signatures':
        print(json.dumps(drift_signatures(json.loads(Path(sys.argv[2]).read_text())), indent=2, sort_keys=True))
        return
    parity_path, gaps_path = map(Path, sys.argv[1:])
    parity = json.loads(parity_path.read_text())
    require(parity['matched_cases'] == len(parity['cases']) >= 10, parity['matched_cases'])
    require(
        parity['unexplained_differences'] == parity['failed_cases'] == 0,
        "replay verification failed at parity['unexplained_differences'] == parity['failed_cases'] == 0",
    )
    require(
        all('python' not in case and 'go' not in case for case in parity['cases']),
        "replay verification failed at all('python' not in case and 'go' not in case for case in parity['cases'])",
    )

    gaps = json.loads(gaps_path.read_text())
    require(gaps['unexplained_differences'] > 0 and gaps['failed_cases'] == 0, gaps['failed_cases'])
    verify_drift(gaps)
    by_name = {case['name']: case for case in gaps['cases']}
    kept = by_name['kept-with-effects']
    py, candidate = kept['python'], kept['go']
    for result in (py, candidate):
        require(result['status'] == 'completed', result['status'])
        require(
            result['conversation']['structured']['title'] == 'Synthetic replay',
            "replay verification failed at result['conversation']['structured']['title'] == 'Synthetic replay'",
        )
        require(
            all(delivery['payload'] for delivery in result['webhooks']),
            "replay verification failed at all(delivery['payload'] for delivery in result['webhooks'])",
        )
        require(
            'conversation_vector' in result['effects'],
            "replay verification failed at 'conversation_vector' in result['effects']",
        )
        require(
            {'conv-structure', 'memory-l1'}.issubset(result['provider_calls']),
            "replay verification failed at {'conv-structure', 'memory-l1'}.issubset(result['provider_calls'])",
        )
    require(
        [delivery['app'] for delivery in py['webhooks']] == ['audit', 'developer-created', 'fixture'],
        "replay verification failed at [delivery['app'] for delivery in py['webhooks']] == ['audit', 'developer-created', 'f",
    )
    require(
        [delivery['app'] for delivery in candidate['webhooks']] == ['audit', 'fixture'],
        "replay verification failed at [delivery['app'] for delivery in candidate['webhooks']] == ['audit', 'fixture']",
    )
    require(
        py['conversation']['apps_results'] == [{'app_id': 'fixture', 'content': 'Synthetic app summary.'}],
        "replay verification failed at py['conversation']['apps_results'] == [{'app_id': 'fixture', 'content': 'Synthetic ap",
    )
    require(
        py['conversation']['folder_id'] == 'replay-folder',
        "replay verification failed at py['conversation']['folder_id'] == 'replay-folder'",
    )
    require(
        py['derived_documents']['users/replay-kept-with-effects/goals/replay-goal']['current_value'] == 2,
        "replay verification failed at py['derived_documents']['users/replay-kept-with-effects/goals/replay-goal']['current_",
    )
    for collection in ('action_items', 'memory_items'):
        require(any(f'/{collection}/' in path for path in py['derived_documents']), collection)
    require(
        any('/replay_memories/' in path for path in candidate['derived_documents']),
        "replay verification failed at any('/replay_memories/' in path for path in candidate['derived_documents'])",
    )
    require(
        not any(diff['kind'] == 'invalid_binding' for case in gaps['cases'] for diff in case['differences']),
        "replay verification failed at not any(diff['kind'] == 'invalid_binding' for case in gaps['cases'] for diff in case[",
    )
    for side in ('python', 'go'):
        own_key = by_name['own-key-resume'][side]
        require(own_key['admitted']['own_key'] and own_key['status'] == 'completed', side)

    require(
        'openai-embeddings' in py['provider_calls'],
        "replay verification failed at 'openai-embeddings' in py['provider_calls']",
    )
    require(
        {
            'path': '/provider_calls/openai-embeddings',
            'kind': 'missing_in_go',
        }
        in kept['differences'],
        'replay verification failed at {',
    )
    unported = {diff['path'] for diff in kept['differences'] if diff['kind'] == 'unported'}
    require(
        '/webhooks/developer-created' in unported,
        "replay verification failed at '/webhooks/developer-created' in unported",
    )
    require(
        '/conversation/apps_results' in unported,
        "replay verification failed at '/conversation/apps_results' in unported",
    )
    require(
        any('~1memory_items~1' in path for path in unported),
        "replay verification failed at any('~1memory_items~1' in path for path in unported)",
    )
    require(
        any('~1action_items~1' in path for path in unported),
        "replay verification failed at any('~1action_items~1' in path for path in unported)",
    )
    paths = {diff['path'] for diff in kept['differences'] if not diff.get('reason')}
    require(
        any(path.startswith('/conversation/') for path in paths),
        "replay verification failed at any(path.startswith('/conversation/') for path in paths)",
    )
    require(
        any(path.startswith('/derived_documents/') for path in paths),
        "replay verification failed at any(path.startswith('/derived_documents/') for path in paths)",
    )
    require(
        any(path.startswith('/webhooks/') for path in paths),
        "replay verification failed at any(path.startswith('/webhooks/') for path in paths)",
    )
    require(
        py['effects']['conversation_vector'] == candidate['effects']['conversation_vector'],
        'conversation vector receipts differ',
    )
    last = by_name['last-attempt-webhook']
    for side in ('python', 'go'):
        result = last[side]
        require(result['status'] == 'completed', (side, result['status']))
        require(
            sum(delivery['app'] == 'unavailable-fixture' for delivery in result['webhooks']) == 1,
            (side, 'last-attempt webhook should be attempted exactly once'),
        )
    word_floor = by_name['word-floor']
    require(word_floor['go_status'] == 'discarded', 'Go discarded disposition was lost')
    require(any(diff['path'] == '/status' for diff in word_floor['differences']), 'discard disposition drift was lost')
    empty = by_name['empty-capture']
    require(
        empty['python']['status'] == 'no_content',
        "replay verification failed at empty['python']['status'] == 'no_content'",
    )
    require(
        any(diff['path'] == '/status' for diff in empty['differences']),
        "replay verification failed at any(diff['path'] == '/status' for diff in empty['differences'])",
    )
    for name in ('compressed-standard', 'enhanced-compressed'):
        for side in ('python', 'go'):
            require(by_name[name][side]['status'] == 'completed', (name, side, by_name[name][side]['status']))


if __name__ == '__main__':
    main()
