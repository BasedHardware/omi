"""Closed, counts-only retrieval and queue diagnostics shared by reports/metrics."""

from typing import TypedDict

PATHS = ('links', 'lexical', 'semantic', 'temporal')
PATH_COUNTS = ('attempted', 'found', 'added', 'failed', 'duplicate', 'unavailable', 'budget_skipped')
DIRTY_COUNTS = (
    'fetched',
    'attempted',
    'found',
    'admitted',
    'unavailable',
    'failed',
    'newer',
    'budget_deferred',
    'permanent',
    'transient',
    'permanent_acknowledged',
    'transient_expired',
)
TARGET_COUNTS = ('retrieval_seeded', 'contextless')


class DiagnosticCounts(TypedDict):
    retrieval_counts: dict[str, dict[str, int]]
    dirty_counts: dict[str, int]
    target_context_counts: dict[str, int]


def initialize(report):
    report.setdefault('retrieval_counts', {path: dict.fromkeys(PATH_COUNTS, 0) for path in PATHS})
    report.setdefault('dirty_counts', dict.fromkeys(DIRTY_COUNTS, 0))
    report.setdefault('target_context_counts', dict.fromkeys(TARGET_COUNTS, 0))
    return report


def path_count(report, path, count, amount=1):
    initialize(report)['retrieval_counts'][path][count] += amount


def counts_only(report) -> DiagnosticCounts:
    """Allowlisted names only, including when projecting a historical report."""
    return {
        'retrieval_counts': {
            path: {
                key: max(0, int(report.get('retrieval_counts', {}).get(path, {}).get(key, 0))) for key in PATH_COUNTS
            }
            for path in PATHS
        },
        'target_context_counts': {
            key: max(0, int(report.get('target_context_counts', {}).get(key, 0))) for key in TARGET_COUNTS
        },
        'dirty_counts': {key: max(0, int(report.get('dirty_counts', {}).get(key, 0))) for key in DIRTY_COUNTS},
    }
