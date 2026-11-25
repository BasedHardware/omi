"""Add value-free family attribution and reviewed labels to an ordinary-sync report."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FAMILIES = (
    'Memory source and metering',
    'Apps',
    'Goals',
    'Digest, minimum and relevance',
    'Other',
    'Firestore operation budget',
)

KNOWN_GAPS = [
    'Per-case trigger is replaced by one sync_update admission; the corpus trigger is not executed.',
    'Repeat-admission controls are not replayed; the adapter submits one admission per case.',
    'final_attempt is not applied to the workerd job.',
    'delete_before_worker_read is not applied; the stored row remains present.',
    'erase_after is not applied; erasure and queue-row deletion are not exercised.',
]

UNREADABLE_CASE = 'unreadable-ciphertext-dead-letters'
UNREADABLE_PARK_RULE = 'SCA-4178: verified unreadable retry age-park consequences; both sides retained ciphertext'
UNREADABLE_RETRY_BUG = 'python_bug:unreadable_ciphertext_retry_until_age_gate'
UNREADABLE_RETRY_ISSUE = 'SCA-4178'
# SCA-3551 groups 2 and 4, ruled on the three literal fixture differences.
RULED_SYNC_VALUE_GAPS = {
    ('transcript-whitespace', '/conversation/transcript_segments'),
    (
        'empty-capture',
        '/derived_documents/users~1replay-empty-capture~1episodes~1'
        '4a3517ab-b5a4-58fc-9d1f-7525f189b614/state_version',
    ),
    (
        'transcript-empty-text',
        '/derived_documents/users~1replay-transcript-empty-text~1episodes~1'
        '514b6b9f-53d4-5569-8092-f0cdc6a3aa25/state_version',
    ),
}
GO_COORDINATION_FIELDS = {
    'go_sync_inline_fanout_epoch',
    'go_sync_inline_fanout_revision',
    'go_empty_discard_fanout_epoch',
    'go_sync_empty_discard_home_revision',
}
REVIEWED_GO_GAP_ROWS = {
    ('empty-capture', '/derived_documents/users/<uid>/episodes/<episode-id>', 'state_version'),
    ('transcript-empty-text', '/derived_documents/users/<uid>/episodes/<episode-id>', 'state_version'),
    ('transcript-whitespace', '/conversation', 'transcript_segments'),
}
UNREADABLE_RETRY_CONSEQUENCE_PATHS = {
    '/status': 'different_value',
    '/conversation/finalization_status': 'missing_in_python',
    '/go/admitted': 'invalid_binding',
    '/python/batch_pipeline_privacy/final': 'missing_document',
    '/python/batch_pipeline_privacy/final_snapshot': 'invalid_binding',
    '/python/firestore_operations/batch_pipeline_privacy_document': 'invalid_operations',
}

PYTHON_BUG_ISSUE = re.compile(r'^[A-Z][A-Z0-9]*-[1-9][0-9]*$')
DYNAMIC_DERIVED_DOCUMENT_IDS = {
    'action_items': '<auto-id>',
    'batch_pipeline_privacy': '<uid-hash>',
    'canonical_memory_maintenance_registry': '<uid>',
    'conversations': '<cid>',
    'episode_links': '<cid>',
    'episode_segment_receipts': '<receipt-id>',
    'episodes': '<episode-id>',
    'events': '<goal-event-id>',
    'goal_history': '<day>',
    'hourly_usage': '<hour>',
    'llm_usage': '<day>',
    'memory_items': '<memory-id>',
    'monthly_usage_totals': '<month>',
    'owner_identity_availability_local': '<uid>',
    'pinecone_partition_routes': '<route>',
    'pipeline_ledger': '<cid>',
    'users': '<uid>',
}

GO_GAP_GROUPS_PATH = Path(__file__).resolve().parents[3] / 'backend-go/tools/replay/approved-go-gaps-sca-4012.csv'


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


def validate_unreadable_park(case: dict) -> bool:
    if case.get('name') != UNREADABLE_CASE:
        return False
    retry = case.get('python_retry') or {}
    pending = retry.get('callback_pending_attempts')
    if (
        case.get('python_status') != 'parked'
        or case.get('go_status') != 'failure'
        or case.get('go_ciphertext_kept') is not True
        or retry.get('outcome') != 'parked'
        or retry.get('reason') != 'age_gate_72h'
        or retry.get('ciphertext_kept') is not True
        or type(pending) is not int
        or pending < 1
        or retry.get('attempts') != pending + 1
        or not any(
            diff.get('path') == '/status' and diff.get('kind') == 'different_value'
            for diff in case.get('differences', ())
        )
    ):
        raise ValueError('SCA-4178 unreadable retry rule is stale or missing evidence')
    return True


def is_go_coordination_stamp_difference(difference: dict) -> bool:
    path = difference.get('path', '')
    return (
        path.startswith('/conversation/')
        and path.removeprefix('/conversation/') in GO_COORDINATION_FIELDS
        and difference.get('kind') == 'missing_in_python'
    )


def is_unreadable_retry_consequence(difference: dict) -> bool:
    if difference.get('unreadable_terminal_consequence') is not True:
        return False
    path = difference.get('path', '')
    kind = difference.get('kind')
    if UNREADABLE_RETRY_CONSEQUENCE_PATHS.get(path) == kind:
        return True
    if (
        path.startswith('/derived_documents/sync_reprocess_outbox~1')
        and path.count('/') == 2
        and kind == 'missing_in_go'
    ):
        return True
    if (
        path.startswith('/derived_documents/users~1')
        and '~1processing_attention_items~1' in path
        and path.count('/') == 2
        and kind == 'missing_in_python'
    ):
        return True
    if path.startswith('/python/derived_documents/batch_pipeline_privacy~1'):
        field = path.rsplit('/', 1)[-1]
        expected_kind = {'memo_token': 'invalid_binding', 'memo_schema': 'missing_evidence'}.get(field)
        return expected_kind == kind and path.count('/') == 4
    return False


def normalized_difference_location(path: str, case_name: str) -> tuple[str, str, bool]:
    side = ''
    for prefix in ('/python/derived_documents/', '/go/derived_documents/'):
        if path.startswith(prefix):
            side = prefix.split('/')[1]
            path = path[len(f'/{side}') :]
            break
    if path.startswith('/derived_documents/'):
        rest = path.removeprefix('/derived_documents/')
        key, separator, field = rest.partition('/')
        parts = key.replace('~1', '/').split('/')
        for index in range(0, len(parts) - 1, 2):
            collection, document_id = parts[index : index + 2]
            if document_id == case_name or document_id == f'replay-{case_name}':
                parts[index + 1] = '<uid>' if collection == 'users' else '<cid>'
            elif collection in DYNAMIC_DERIVED_DOCUMENT_IDS:
                parts[index + 1] = DYNAMIC_DERIVED_DOCUMENT_IDS[collection]
            elif re.fullmatch(r'[0-9a-f]{8}-[0-9a-f-]{27,}', document_id):
                parts[index + 1] = '<uuid>'
        path_prefix = f'{side}/derived_documents/' if side else '/derived_documents/'
        return (
            path_prefix + '/'.join(parts),
            field if separator else '<document>',
            bool(side),
        )
    parts = path.strip('/').split('/')
    return (
        '/' + parts[0] if parts and parts[0] else '/',
        '/'.join(parts[1:]) if len(parts) > 1 else '<value>',
        bool(side),
    )


def approved_go_gap_groups() -> list[dict[str, str]]:
    with GO_GAP_GROUPS_PATH.open(newline='', encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 48 or any(row.get('proposed_label') != 'go_gap' for row in rows):
        raise ValueError('SCA-4012 Go-gap map must contain exactly 48 approved go_gap groups')
    keys = [(row['path_pattern'], row['field']) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('SCA-4012 Go-gap map contains duplicate path/field groups')
    return rows


def pass3_go_gap_group(path: str, case_name: str, groups: list[dict[str, str]]) -> str | None:
    path_pattern, field, side_specific = normalized_difference_location(path, case_name)
    if side_specific:
        return None
    for group in groups:
        if path_pattern != group['path_pattern']:
            continue
        group_field = group['field']
        if group_field == '<document>' or field == group_field or field.startswith(group_field + '/'):
            return group['group']
    return None


def is_reviewed_go_gap_row(difference: dict, case_name: str) -> bool:
    if difference.get('kind') != 'different_value':
        return False
    path_pattern, field, side_specific = normalized_difference_location(difference.get('path', ''), case_name)
    return not side_specific and (case_name, path_pattern, field) in REVIEWED_GO_GAP_ROWS


def unlabelled_groups(cases: list[dict]) -> list[dict]:
    groups = {}
    for case in cases:
        name = case.get('name', '')
        for difference in case.get('differences', []):
            if difference.get('label') is not None:
                continue
            path = difference.get('path', '')
            path_pattern, field, _ = normalized_difference_location(path, name)
            key = (path_pattern, field)
            row = groups.setdefault(key, {'rows': 0, 'case_ids': set(), 'kinds': set()})
            row['rows'] += 1
            row['case_ids'].add(name)
            row['kinds'].add(difference.get('kind', ''))
    return [
        {
            'path_pattern': path,
            'field': field,
            'rows': row['rows'],
            'cases': len(row['case_ids']),
            'case_ids': sorted(row['case_ids']),
            'kinds': sorted(kind for kind in row['kinds'] if kind),
        }
        for (path, field), row in sorted(groups.items(), key=lambda item: (-item[1]['rows'], item[0]))
    ]


def enrich(report: dict) -> dict:
    totals = {family: {'unexplained': 0, 'allowed': 0, 'go_gap': 0, 'python_bug': 0, 'total': 0} for family in FAMILIES}
    allowed_by_rule = Counter()
    label_totals = Counter()
    pass3_groups = approved_go_gap_groups()
    pass3_rows_by_group = Counter()
    pass3_matches_by_group = Counter()
    pass3_matches_by_label = Counter()
    pass3_labels_by_group = defaultdict(Counter)
    pass3_cases_by_group = defaultdict(set)
    home_receipt_rows = 0
    home_receipt_side_traces = {}
    raw_unexplained = report.get('unexplained_differences', 0)
    failed_cases = report.get('failed_cases', 0)
    operation_table = []
    operation_overages = []
    provided_operation_rows = {row.get('case'): row for row in report.get('operation_table', [])}
    for case in report.get('cases', []):
        operation_row = provided_operation_rows.get(case.get('name'))
        if operation_row is None:
            cost = case.get('cost') or {}
            python_ops = (cost.get('python') or {}).get('firestore_operations') or {}
            go_ops = (cost.get('go') or {}).get('firestore_operations') or {}
            python_reads = python_ops.get('document_reads', 0) + python_ops.get('query_documents', 0)
            python_writes = python_ops.get('writes', 0)
            python_deletes = python_ops.get('deletes', 0)
            go_reads = go_ops.get('document_reads', 0) + go_ops.get('query_documents', 0)
            go_writes = go_ops.get('writes', 0)
            go_deletes = go_ops.get('deletes', 0)
            difference = go_reads + go_writes + go_deletes - python_reads - python_writes - python_deletes
            sources = (case.get('go') or {}).get('firestore_operation_sources') or {}
            top_sources = sorted(
                (
                    {
                        'document_path': path,
                        'reads': counts.get('reads', 0),
                        'writes': counts.get('writes', 0),
                        'deletes': counts.get('deletes', 0),
                        'operations': counts.get('reads', 0) + counts.get('writes', 0) + counts.get('deletes', 0),
                    }
                    for path, counts in sources.items()
                ),
                key=lambda source: (-source['operations'], source['document_path']),
            )[:5]
            operation_row = {
                'case': case.get('name', ''),
                'python_reads': python_reads,
                'python_writes': python_writes,
                'python_deletes': python_deletes,
                'go_reads': go_reads,
                'go_writes': go_writes,
                'go_deletes': go_deletes,
                'python_operations': python_reads + python_writes + python_deletes,
                'go_operations': go_reads + go_writes + go_deletes,
                'difference': difference,
                'label': 'go_gap:ops' if difference > 0 else None,
                'go_top_operation_sources': top_sources,
            }
        else:
            operation_row = dict(operation_row)
        operation_table.append(operation_row)
        if case.get('errors'):
            operation_row['label'] = None
        elif operation_row['difference'] > 0:
            operation_overages.append({'case': operation_row['case'], 'difference': operation_row['difference']})

        unreadable_park = not case.get('errors') and validate_unreadable_park(case)
        captured_receipt_trace = case.get('home_dirty_receipt_trace') or {}
        case['home_dirty_receipt_trace'] = {side: captured_receipt_trace.get(side, {}) for side in ('python', 'go')}
        case.pop('cost', None)
        case.pop('go_evidence', None)
        case.pop('python', None)
        case.pop('go', None)
        for difference in case.get('differences', []):
            family = family_for_path(difference.get('path', ''))
            difference['family'] = family
            pass3_group = pass3_go_gap_group(difference.get('path', ''), case.get('name', ''), pass3_groups)
            assigned_from_pass3 = False
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
            elif (
                difference.get('path')
                in {
                    '/conversation/go_finalization_notes_input_hash',
                    '/conversation/go_finalization_notes_output_hash',
                    '/conversation/finalization_job_id',
                    '/go/episode_attach_memo',
                }
                or (
                    difference.get('kind') == 'invalid_binding'
                    and difference.get('path', '').startswith('/go/derived_documents/')
                    and '~1episode_links~1' in difference.get('path', '')
                    and difference.get('path', '').endswith('/attach_memo_evidence')
                )
                or difference.get('failure_reason') == 'go_attach_memo_invalid'
                or difference.get('failure_reason')
                in {
                    'profile_refresh_proof_failed',
                    'task_vector_proof_failed',
                    'terminal_attach_memo_present',
                }
            ):
                label = 'go_gap'
            elif is_reviewed_go_gap_row(difference, case.get('name', '')):
                label = 'go_gap'
            elif is_go_coordination_stamp_difference(difference):
                label = 'by_design:go_coordination_stamp'
                difference['reason'] = 'go_coordination_stamp'
            elif unreadable_park and is_unreadable_retry_consequence(difference):
                label = UNREADABLE_RETRY_BUG
                difference['issue'] = UNREADABLE_RETRY_ISSUE
                difference['reason'] = UNREADABLE_PARK_RULE
            elif difference.get('reason'):
                label = f"by_design:{difference['reason']}"
            elif (
                difference.get('kind') == 'different_value'
                and (case['name'], difference['path']) in RULED_SYNC_VALUE_GAPS
            ):
                label = 'go_gap'
            else:
                if pass3_group is None:
                    label = None
                else:
                    label = 'go_gap'
                    assigned_from_pass3 = True
                    pass3_rows_by_group[pass3_group] += 1
            difference['label'] = label
            label_totals[label or 'unlabelled'] += 1
            if pass3_group is not None:
                pass3_matches_by_group[pass3_group] += 1
                pass3_matches_by_label[label or 'unlabelled'] += 1
                pass3_cases_by_group[pass3_group].add(case.get('name', ''))
                if not assigned_from_pass3:
                    pass3_labels_by_group[pass3_group][label or 'unlabelled'] += 1
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
    go_gap = label_totals.get('go_gap', 0)
    unexplained_gate_count = go_gap + unlabelled
    if raw_unexplained < unexplained_gate_count:
        raise ValueError('gate-counted differences exceed the comparator unexplained count')
    report['unexplained_differences'] = unexplained_gate_count
    if operation_overages:
        label_totals['go_gap:ops'] += len(operation_overages)
    totals['Firestore operation budget']['go_gap'] += len(operation_overages)
    totals['Firestore operation budget']['total'] += len(operation_overages)
    report['operation_table'] = operation_table
    report['diagnostic'] = {
        'driver': 'ordinary-sync workerd seam',
        'worker_ref': report.get('commit_sha', ''),
        'family_counts': totals,
        'label_counts': dict(sorted(label_totals.items())),
        'r7_operation_budget': {
            'rule': 'Go reads + writes + deletes <= Python reads + writes + deletes per case',
            'label': 'go_gap:ops',
            'over_budget_case_count': len(operation_overages),
            'over_budget_cases': operation_overages,
            'status': 'invalid' if failed_cases else 'blocked' if operation_overages else 'pass',
        },
        'unexplained_gate': {
            'rule': 'go_gap + unlabelled; python_bug exceptions are reported separately',
            'go_gap_rows': go_gap,
            'unlabelled_rows': unlabelled,
            'total': unexplained_gate_count,
            'python_bug_exceptions': {
                label.removeprefix('python_bug:'): count
                for label, count in label_totals.items()
                if label.startswith('python_bug:')
            },
        },
        'pass3_go_gap_labels': {
            'source_issue': 'SCA-4012',
            'source_csv': 'backend-go/tools/replay/approved-go-gaps-sca-4012.csv',
            'approved_groups': len(pass3_groups),
            'groups_with_current_unlabelled_rows': len(pass3_rows_by_group),
            'rows_labeled': sum(pass3_rows_by_group.values()),
            'current_matching_rows': sum(pass3_matches_by_group.values()),
            'current_matching_rows_by_label': dict(sorted(pass3_matches_by_label.items())),
            'by_group': [
                {
                    'group': int(group['group']),
                    'path_pattern': group['path_pattern'],
                    'field': group['field'],
                    'source_rows': int(group['rows']),
                    'source_cases': int(group['cases']),
                    'current_matching_rows': pass3_matches_by_group[group['group']],
                    'current_matching_cases': len(pass3_cases_by_group[group['group']]),
                    'rows_labeled': pass3_rows_by_group[group['group']],
                    'already_labeled': dict(sorted(pass3_labels_by_group[group['group']].items())),
                }
                for group in pass3_groups
            ],
            'groups_without_current_matching_rows': [
                int(group['group']) for group in pass3_groups if not pass3_matches_by_group[group['group']]
            ],
        },
        'cohort_gate': 'closed' if failed_cases or unexplained_gate_count or operation_overages else 'open',
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
    if sum(row['unexplained'] for row in totals.values()) != unlabelled:
        raise ValueError('family totals do not sum to the unlabelled row count')
    if sum(label_totals.values()) != sum(row['total'] for row in totals.values()):
        raise ValueError('label totals do not sum to the difference row count')
    groups = unlabelled_groups(report.get('cases', []))
    if sum(group['rows'] for group in groups) != unlabelled:
        raise ValueError('unlabelled groups do not sum to the unlabelled row count')
    report['diagnostic']['unlabelled_groups'] = groups
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
    gate = enriched['diagnostic']['unexplained_gate']
    print(
        f"Unexplained gate: {gate['total']} ({gate['go_gap_rows']} go_gap + "
        f"{gate['unlabelled_rows']} unlabelled); Python-bug exceptions: "
        + ', '.join(f'{issue}={count}' for issue, count in gate['python_bug_exceptions'].items())
    )
    pass3 = enriched['diagnostic']['pass3_go_gap_labels']
    print(
        f"SCA-4012 pass 3: {pass3['rows_labeled']} current rows labeled across "
        f"{pass3['groups_with_current_unlabelled_rows']}/{pass3['approved_groups']} approved groups"
    )
    for rule, count in enriched['diagnostic']['allowed_by_rule'].items():
        print(f"Allowed by rule ({count}): {rule}")
    print('Known gaps: trigger, repeat-admission, final attempt, deletion, erase.')
    print(
        f"R7: {enriched['diagnostic']['r7_operation_budget']['over_budget_case_count']} cases over "
        f"Go <= Python; cohort gate {enriched['diagnostic']['cohort_gate']}"
    )
    if enriched.get('failed_cases', 0):
        print('Ordinary-sync execution errors: cost comparisons are invalid.', file=sys.stderr)
        raise SystemExit(2)


if __name__ == '__main__':
    main()
