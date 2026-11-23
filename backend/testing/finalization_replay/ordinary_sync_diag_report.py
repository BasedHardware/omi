"""Add value-free family attribution and reviewed labels to an ordinary-sync report."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

FAMILIES = (
    'Memory source and metering',
    'Apps',
    'Goals',
    'Digest, minimum and relevance',
    'Other',
)

KNOWN_GAPS = [
    'Per-case trigger is replaced by one sync_update admission; the corpus trigger is not executed.',
    'Repeat-admission controls are not replayed; the adapter submits one admission per case.',
    'final_attempt is not applied to the workerd job.',
    'delete_before_worker_read is not applied; the stored row remains present.',
    'erase_after is not applied; erasure and queue-row deletion are not exercised.',
]

PYTHON_BUG_EXCEPTIONS = {
    'unreadable-ciphertext-dead-letters': {
        'issue': 'SCA-3874',
        'python_status': 'discarded',
        'go_status': 'failure',
        'sentinels': {
            '/status': 'different_value',
            '/conversation/discarded': 'missing_in_go',
            '/conversation/transcript_segments': 'different_value',
        },
    },
}

PYTHON_BUG_ISSUE = re.compile(r'^[A-Z][A-Z0-9]*-[1-9][0-9]*$')


def family_for_path(path: str) -> str:
    value = path.lower().replace('~1', '/')
    if any(marker in value for marker in ('/goals/', '/goal_history/', '/goal_progress/')) or value.endswith('/goals'):
        return 'Goals'
    if any(
        marker in value
        for marker in (
            'notes_llm_',
            'memories_llm_input_hash',
        )
    ):
        return 'Other'
    if any(
        marker in value
        for marker in (
            'apps_results',
            'suggested_summarization_apps',
            'plugins_results',
            'developer-created',
            '/webhooks/',
            '/app_id',
            '/provider_calls/conv-app-result',
        )
    ):
        return 'Apps'
    if any(
        marker in value
        for marker in (
            'memory',
            'memories',
            'embedding',
            'vector',
            '/llm_usage/',
            'usage_history',
            'metering',
        )
    ):
        return 'Memory source and metering'
    if any(
        marker in value
        for marker in (
            'digest',
            'minimum',
            'min_words',
            'relevance',
            'discard',
            'summary',
            '/structured/',
            '/provider_calls/conv-structure',
            '/provider_calls/conv-discard',
        )
    ):
        return 'Digest, minimum and relevance'
    return 'Other'


def validate_label(label: object, approved_reason: object = None) -> str:
    if label == 'go_gap':
        return label
    if isinstance(label, str) and label.startswith('python_bug:'):
        issue = label.removeprefix('python_bug:')
        if PYTHON_BUG_ISSUE.fullmatch(issue):
            return label
    if isinstance(label, str) and label.startswith('by_design:'):
        rule = label.removeprefix('by_design:')
        if rule.strip() and rule == approved_reason:
            return label
    raise ValueError(f'invalid difference label: {label!r}')


def validate_python_bug_exception(case: dict) -> str | None:
    exception = PYTHON_BUG_EXCEPTIONS.get(case.get('name'))
    if exception is None:
        return None
    if case.get('python_status') != exception['python_status'] or case.get('go_status') != exception['go_status']:
        raise ValueError(f"{exception['issue']} exception is stale or changed; review and remove it")
    differences = {difference.get('path'): difference.get('kind') for difference in case.get('differences', [])}
    if any(differences.get(path) != kind for path, kind in exception['sentinels'].items()):
        raise ValueError(f"{exception['issue']} exception no longer matches its expected difference rows")
    return exception['issue']


def enrich(report: dict) -> dict:
    totals = {family: {'unexplained': 0, 'allowed': 0, 'go_gap': 0, 'python_bug': 0, 'total': 0} for family in FAMILIES}
    allowed_by_rule = Counter()
    label_totals = Counter()
    home_receipt_rows = 0
    home_receipt_side_traces = {}
    raw_unexplained = report.get('unexplained_differences', 0)
    for case in report.get('cases', []):
        python_bug_issue = validate_python_bug_exception(case)
        captured_receipt_trace = case.get('home_dirty_receipt_trace') or {}
        case['home_dirty_receipt_trace'] = {side: captured_receipt_trace.get(side, {}) for side in ('python', 'go')}
        case.pop('cost', None)
        case.pop('go_evidence', None)
        case.pop('python', None)
        case.pop('go', None)
        for difference in case.get('differences', []):
            family = family_for_path(difference.get('path', ''))
            difference['family'] = family
            if difference.get('failure_reason') == 'home_dirty_receipt_missing':
                label = None
                home_receipt_rows += 1
                side = difference.get('path', '').split('/', 1)[0]
                if side in {'python', 'go'}:
                    home_receipt_side_traces[(case.get('name'), side)] = case['home_dirty_receipt_trace'][side]
            elif difference.get('label'):
                label = validate_label(difference['label'], difference.get('reason'))
                if label.startswith('python_bug:'):
                    raise ValueError('python_bug labels require a matching approved case-specific exception')
            elif difference.get('path') == '/conversation/finalization_job_id' and python_bug_issue:
                label = f'python_bug:{python_bug_issue}'
            elif difference.get('path') in {
                '/conversation/go_finalization_notes_input_hash',
                '/conversation/go_finalization_notes_output_hash',
                '/conversation/finalization_job_id',
            }:
                label = 'go_gap'
            elif difference.get('reason'):
                label = f"by_design:{difference['reason']}"
            elif python_bug_issue:
                label = f'python_bug:{python_bug_issue}'
            else:
                label = None
            difference['label'] = label
            label_totals[label or 'unlabelled'] += 1
            if label is None:
                state = 'unexplained'
            elif label == 'go_gap':
                state = 'go_gap'
            elif label.startswith('python_bug:'):
                state = 'python_bug'
            else:
                state = 'allowed'
            totals[family][state] += 1
            totals[family]['total'] += 1
            if label and label.startswith('by_design:'):
                allowed_by_rule[label.removeprefix('by_design:')] += 1
    report.pop('cost_table', None)
    unlabelled = label_totals.get('unlabelled', 0)
    if raw_unexplained < unlabelled:
        raise ValueError('unlabelled differences exceed the comparator unexplained count')
    report['unexplained_differences'] = unlabelled
    report['diagnostic'] = {
        'driver': 'ordinary-sync workerd seam',
        'worker_ref': report.get('commit_sha', ''),
        'family_counts': totals,
        'label_counts': dict(sorted(label_totals.items())),
        'raw_unexplained_differences': raw_unexplained,
        'allowed_by_rule': dict(sorted(allowed_by_rule.items())),
        'approved_rule_reference': 'backend-go/tools/replay/comparison-rules.md',
        'known_gaps': KNOWN_GAPS,
        'home_dirty_receipt_missing': {
            'rows': home_receipt_rows,
            'observed_case_sides': len(home_receipt_side_traces),
            'writes_set_true': sum(trace.get('set_true', 0) for trace in home_receipt_side_traces.values()),
            'writes_set_false': sum(trace.get('set_false', 0) for trace in home_receipt_side_traces.values()),
            'deletes': sum(trace.get('deleted', 0) for trace in home_receipt_side_traces.values()),
            'other_writes': sum(trace.get('other_write', 0) for trace in home_receipt_side_traces.values()),
            'by_side': {
                side: {
                    key: sum(
                        trace.get(key, 0)
                        for (_case_name, trace_side), trace in home_receipt_side_traces.items()
                        if trace_side == side
                    )
                    for key in ('set_true', 'set_false', 'deleted', 'other_write')
                }
                for side in ('python', 'go')
            },
            'label': 'unlabelled',
        },
        'value_free': True,
        'cost_measured': False,
    }
    if sum(row['unexplained'] for row in totals.values()) != report.get('unexplained_differences'):
        raise ValueError('family totals do not sum to the unexplained-difference count')
    if sum(label_totals.values()) != sum(row['total'] for row in totals.values()):
        raise ValueError('label totals do not sum to the difference row count')
    return report


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: ordinary_sync_diag_report.py REPORT.json')
    path = Path(sys.argv[1])
    report = json.loads(path.read_text(encoding='utf-8'))
    enriched = enrich(report)
    temporary = path.with_name(f'.{path.name}.tmp')
    temporary.write_text(json.dumps(enriched, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)
    for family, counts in enriched['diagnostic']['family_counts'].items():
        print(
            f"{family}: {counts['unexplained']} unlabelled; {counts['allowed']} by design; "
            f"{counts['python_bug']} Python bugs; {counts['go_gap']} Go gaps"
        )
    for label, count in enriched['diagnostic']['label_counts'].items():
        print(f"Label ({count}): {label}")
    for rule, count in enriched['diagnostic']['allowed_by_rule'].items():
        print(f"Allowed by rule ({count}): {rule}")
    print('Known gaps: trigger, repeat-admission, final attempt, deletion, erase.')


if __name__ == '__main__':
    main()
