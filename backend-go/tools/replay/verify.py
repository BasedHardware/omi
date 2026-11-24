"""Check that the two emulator runs prove both parity and drift detection."""

import json
import os
from pathlib import Path
import re
import sys


# Public path normalization used by the merged Go port-task delta tooling.
# Only replace reviewed volatile IDs under derived documents; preserve all other path parts.
DYNAMIC_DOCUMENT_IDS = {
    'action_items': (r'[A-Za-z0-9]{20}', '<auto-id>'),
    'events': (r'gpe_[0-9a-f]{32}', '<goal-event-id>'),
    'goal_history': (r'\d{4}-\d{2}-\d{2}', '<day>'),
    'hourly_usage': (r'\d{4}-\d{2}-\d{2}-\d{2}', '<hour>'),
    'llm_usage': (r'\d{4}-\d{2}-\d{2}', '<day>'),
    'monthly_usage_totals': (r'\d{4}-\d{2}', '<month>'),
}


def stable_path(path):
    """Normalize only reviewed dynamic document IDs in a derived-document pointer."""
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


def require(condition, detail):
    if not condition:
        raise SystemExit(str(detail))


def verify_cost(report):
    cases = {case['name']: case for case in report['cases']}
    rows = report.get('cost_table', [])
    require(len(rows) == len(cases), 'cost table does not have one row per case')
    require({row['case'] for row in rows} == set(cases), 'cost table case set differs from replay report')
    for name, case in cases.items():
        cost = case['cost']
        for side in ('python', 'go'):
            measured = cost[side]
            require(measured['measured'] is True, (name, side, 'cost was not measured'))
            require(measured['token_basis'].startswith('cl100k content-token estimate'), (name, side, 'token basis'))
            tokens = measured['llm_tokens']
            require(tokens['total'] == tokens['prompt'] + tokens['completion'], (name, side, 'token totals'))
            require(measured['embedding_tokens'] >= 0, (name, side, 'embedding token count'))
            ops = measured['firestore_operations']
            require(all(type(value) is int and value >= 0 for value in ops.values()), (name, side, 'Firestore counts'))
            observation = case.get(side)
            if observation is not None:
                observed_activity = bool(observation.get('provider_calls')) or bool(
                    observation.get('derived_documents')
                ) or observation.get('updated_at_changed') is True or bool(observation.get('effects'))
                total_cost = tokens['total'] + measured['embedding_tokens'] + sum(ops.values())
                require(
                    not observed_activity or total_cost > 0,
                    (name, side, 'observed activity has an all-zero cost row'),
                )
def verify_corpus_map(parity, gaps):
    replay_dir = Path(__file__).parent
    manifest = json.loads((replay_dir / 'case-map.json').read_text())
    rules = set(manifest['oracle_drivable_rules']) | set(manifest['not_oracle_drivable_rules'])
    require(rules == {f'F{number:02d}' for number in range(1, 39)}, 'case map must name every F01-F38 rule')
    require(set(manifest['oracle_drivable_rules']) & set(manifest['not_oracle_drivable_rules']) == set(), 'rule scope overlaps')
    entries = manifest['cases']
    names = [item['name'] for item in entries]
    require(len(names) == len(set(names)), 'case map has duplicate case names')
    require(all(item['rules'] for item in entries), 'every case must map to at least one contract rule')
    corpus_names = {}
    for filename in ('admission-parity.json', 'conformance-gaps.json', 'held-out.json'):
        payload = json.loads((replay_dir / 'corpus' / filename).read_text())
        corpus_names[filename] = {item['name'] for item in payload['cases']}
    require(len(corpus_names['admission-parity.json'] | corpus_names['conformance-gaps.json']) == manifest['active_case_count'], 'active corpus count mismatch')
    require(manifest['active_case_count'] >= manifest['active_floor'] >= 50, 'active synthetic corpus is below its floor')
    require(len(corpus_names['held-out.json']) == manifest['held_out_case_count'] > 0, 'held-out corpus count mismatch')
    for filename, case_names in corpus_names.items():
        mapped = {item['name'] for item in entries if item['corpus'] == filename}
        require(mapped == case_names, (filename, 'case map does not match corpus'))
    active_entries = [item for item in entries if not item['held_out']]
    heldout_entries = [item for item in entries if item['held_out']]
    require({item['corpus'] for item in heldout_entries} == {'held-out.json'}, 'held-out cases must use the holdout file')
    require({rule for item in active_entries for rule in item['rules']} == set(manifest['oracle_drivable_rules']), 'active cases do not cover every drivable rule')
    require(not any(set(item['rules']) - set(manifest['oracle_drivable_rules']) for item in active_entries), 'active case claims an undrivable rule')
    require(all(item['rules'] for item in entries), 'held-out case has no contract mapping')
    reported = {case['name'] for report in (parity, gaps) for case in report['cases']}
    require(reported == {item['name'] for item in active_entries}, 'held-out cases must stay out of CI reports')
    require(len(gaps['cases']) == 40 and len(parity['cases']) == 10, 'expected 40 active-finalizer and 10 admission cases')
    require(parity['commit_sha'] == gaps['commit_sha'] and len(gaps['commit_sha']) == 40, 'reports must name the same commit')
    verify_cost(parity)
    verify_cost(gaps)


def verify_unexplained_count(report):
    measured = sum(
        1 for case in report['cases'] for diff in case['differences'] if not diff.get('reason')
    )
    require(
        measured == report['unexplained_differences'],
        'per-commit unexplained-difference count is inconsistent',
    )


def verify_departures(gaps):
    by_name = {case['name']: case for case in gaps['cases']}
    erase = by_name['erase-removes-owner-and-jobs']
    erase_evidence = erase['go_evidence']['erasure']
    require(erase_evidence['user_document_absent'] is True, 'Go erasure left the owner document')
    require(erase_evidence['jobs_for_uid'] == erase_evidence['tenants_for_uid'] == 0, 'Go erasure left database rows')
    require(erase['go']['conversation'] is None, 'Go erasure replay retained a conversation row')
    unreadable = by_name['unreadable-ciphertext-dead-letters']
    job = unreadable['go_evidence']['job']
    require(job['reason'] == 'transcript_unreadable', 'Go did not preserve the typed decrypt error')
    require(job['state'] == 'parked', 'Go unreadable transcript job was not parked')
    require(job['outcome'] == 'failure', 'Go unreadable transcript was not recorded as a failed job')
    require(unreadable['go']['conversation']['finalization_status'] == 'dead_letter', 'Go unreadable transcript did not dead-letter')
    require('conv-structure' not in unreadable['go']['provider_calls'], 'Go sent unreadable ciphertext to note generation')


def main():
    parity_path, gaps_path = map(Path, sys.argv[1:])
    parity = json.loads(parity_path.read_text())
    gaps = json.loads(gaps_path.read_text())
    verify_corpus_map(parity, gaps)
    require(parity['matched_cases'] == len(parity['cases']) == 10, parity['matched_cases'])
    require(
        parity['unexplained_differences'] == parity['failed_cases'] == 0,
        "replay verification failed at parity['unexplained_differences'] == parity['failed_cases'] == 0",
    )
    require(
        all('python' not in case and 'go' not in case for case in parity['cases']),
        "replay verification failed at all('python' not in case and 'go' not in case for case in parity['cases'])",
    )

    failed = [case for case in gaps['cases'] if case['errors']]
    require(not failed and gaps['failed_cases'] == 0, [(case['name'], case['errors']) for case in failed])
    require(gaps['unexplained_differences'] > 0, gaps['unexplained_differences'])
    verify_unexplained_count(gaps)
    by_name = {case['name']: case for case in gaps['cases']}
    verify_departures(gaps)
    missing_worker = by_name['worker-missing-row-fence']
    require(missing_worker['go_evidence']['job']['outcome'] == 'fenced', 'Go worker did not fence the deleted row')
    require('conv-structure' not in missing_worker['go']['provider_calls'], 'Go worker called the model after losing its row')
    for case in gaps['cases']:
        if case['name'].startswith('trigger-'):
            expected = case['name'].removeprefix('trigger-').replace('-', '_')
            require(case['go_evidence']['job']['metadata']['trigger'] == expected, (case['name'], 'trigger metadata'))
        if case['name'].startswith('end-reason-'):
            expected = case['name'].removeprefix('end-reason-').replace('-', '_')
            require(case['go_evidence']['job']['metadata']['end_reason'] == expected, (case['name'], 'end reason metadata'))
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


def write_value_free_report(report, path):
    for case in report['cases']:
        case.pop('python', None)
        case.pop('go', None)
        case.pop('go_evidence', None)
    encoded = json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2) + '\n'
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            descriptor = -1
            output.write(encoded)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def verify_task_reports(output_dir, parity_path, gaps_path):
    parity = json.loads(Path(parity_path).read_text())
    gaps = json.loads(Path(gaps_path).read_text())
    verify_corpus_map(parity, gaps)
    for report in (parity, gaps):
        failed = [case for case in report['cases'] if case['errors']]
        require(not failed and report['failed_cases'] == 0, [(case['name'], case['errors']) for case in failed])
        verify_unexplained_count(report)
    verify_departures(gaps)
    destination = Path(output_dir)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_value_free_report(parity, destination / 'parity.json')
    write_value_free_report(gaps, destination / 'gaps.json')


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--task-output':
        verify_task_reports(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main()
