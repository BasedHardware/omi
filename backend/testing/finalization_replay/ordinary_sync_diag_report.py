"""Add value-free family attribution to an ordinary-sync diagnostic report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

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


def enrich(report: dict) -> dict:
    totals = {family: {'unexplained': 0, 'allowed': 0, 'total': 0} for family in FAMILIES}
    allowed_by_rule = Counter()
    for case in report.get('cases', []):
        case.pop('cost', None)
        case.pop('go_evidence', None)
        case.pop('python', None)
        case.pop('go', None)
        for difference in case.get('differences', []):
            family = family_for_path(difference.get('path', ''))
            difference['family'] = family
            state = 'allowed' if difference.get('reason') else 'unexplained'
            totals[family][state] += 1
            totals[family]['total'] += 1
            if state == 'allowed':
                allowed_by_rule[difference['reason']] += 1
    report.pop('cost_table', None)
    report['diagnostic'] = {
        'driver': 'ordinary-sync workerd seam',
        'worker_ref': report.get('commit_sha', ''),
        'family_counts': totals,
        'allowed_by_rule': dict(sorted(allowed_by_rule.items())),
        'approved_rule_reference': 'backend-go/tools/replay/comparison-rules.md',
        'known_gaps': KNOWN_GAPS,
        'value_free': True,
        'cost_measured': False,
    }
    if sum(row['unexplained'] for row in totals.values()) != report.get('unexplained_differences'):
        raise ValueError('family totals do not sum to the unexplained-difference count')
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
        print(f"{family}: {counts['unexplained']} unexplained; {counts['allowed']} allowed")
    for rule, count in enriched['diagnostic']['allowed_by_rule'].items():
        print(f"Allowed by rule ({count}): {rule}")
    print('Known gaps: trigger, repeat-admission, final attempt, deletion, erase.')


if __name__ == '__main__':
    main()
