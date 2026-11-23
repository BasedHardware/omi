"""Export only outcome, transport status and costs from synthetic replay observations."""

import json
from pathlib import Path
import sys


def evidence(cases, comparator, worker):
    rows = []
    for case in cases:
        go = case.get('go', {})
        worker_evidence = go.get('go_evidence', {})
        rows.append(
            {
                'case': case['name'],
                'errors': case.get('errors', {}),
                'python_status': case.get('python', {}).get('status'),
                'go_status': go.get('status'),
                'go_job': worker_evidence.get('job', {}),
                'go_firestore_rpc_failures': worker_evidence.get('firestore_rpc_failures', {}),
                **{
                    engine: {
                        'cost': case.get(engine, {}).get('cost', {}),
                        'provider_token_calls': case.get(engine, {}).get('provider_token_calls', []),
                    }
                    for engine in ('python', 'go')
                },
            }
        )
    return {'comparator': comparator, 'worker': worker, 'cases': rows}


if __name__ == '__main__':
    source, output, comparator, worker = sys.argv[1:]
    result = evidence(json.loads(Path(source).read_text()), comparator, worker)
    with Path(output).open('x', encoding='utf-8') as report:
        json.dump(result, report, indent=2)
        report.write('\n')
