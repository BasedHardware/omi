"""Closed, counts-only retrieval and queue diagnostics shared by reports/metrics."""

from typing import TypedDict

PATHS = ('links', 'lexical', 'semantic', 'temporal')
PATH_COUNTS = ('attempted', 'found', 'added', 'failed', 'duplicate', 'unavailable', 'budget_skipped', 'query_empty')
# Fixed class names only: never messages, module paths, IDs, or arbitrary labels.
# Unknown/custom exceptions collapse to the actual base class Exception.
FAILURE_CLASSES = frozenset(
    {
        'Exception',
        'TypeError',
        'AttributeError',
        'ImportError',
        'ModuleNotFoundError',
        'ValueError',
        'ValidationError',
        'RuntimeError',
        'TimeoutError',
        'HTTPException',
        'PermissionDenied',
        'Unauthenticated',
        'ServiceUnavailable',
        'NotFound',
        'DeadlineExceeded',
        'FailedPrecondition',
        'InvalidArgument',
        'ResourceExhausted',
        'Aborted',
        'RetryError',
        'ReadError',
        'ReadTimeout',
        'ConnectError',
        'ConnectTimeout',
        'ConnectionError',
        'Timeout',
        'HTTPStatusError',
        'APIError',
        'APIConnectionError',
        'APITimeoutError',
        'RateLimitError',
        'AuthenticationError',
        'BadRequestError',
        'ObjectNotFound',
        'RequestMalformed',
        'ServerError',
        'ConversationSearchUnavailableError',
        'DreamTranscriptReadError',
    }
)
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
INPUT_CONTENT_COUNTS = (
    'conversations',
    'with_title',
    'with_overview',
    'with_sections_text',
    'with_transcript_text',
    'empty_transcript',
    'missing_transcript',
    'query_content_empty',
    'transcript_decode_failed',
)
CONTEXT_BUDGET_COUNTS = (
    'supplied_targets',
    'targets_deferred',
    'reserved_triage_bytes',
    'target_triage_limit_bytes',
    'visible_found',
    'reservation_kept',
    'slice_reclaimed',
    'triage_input_bytes',
    'target_excerpt_bytes',
    'context_excerpt_bytes',
)


class DiagnosticCounts(TypedDict):
    retrieval_counts: dict[str, dict[str, int]]
    retrieval_failure_counts: dict[str, dict[str, int]]
    dirty_counts: dict[str, int]
    target_context_counts: dict[str, int]
    input_content_counts: dict[str, int]
    context_budget_counts: dict[str, int]


def initialize(report):
    report.setdefault('retrieval_counts', {path: dict.fromkeys(PATH_COUNTS, 0) for path in PATHS})
    report.setdefault('retrieval_failure_counts', {path: {} for path in PATHS})
    report.setdefault('dirty_counts', dict.fromkeys(DIRTY_COUNTS, 0))
    report.setdefault('target_context_counts', dict.fromkeys(TARGET_COUNTS, 0))
    report.setdefault('input_content_counts', dict.fromkeys(INPUT_CONTENT_COUNTS, 0))
    report.setdefault('context_budget_counts', dict.fromkeys(CONTEXT_BUDGET_COUNTS, 0))
    return report


def path_count(report, path, count, amount=1):
    initialize(report)['retrieval_counts'][path][count] += amount


def path_failure(report, path, exc):
    path_count(report, path, 'failed')
    name = type(exc).__name__
    name = name if name in FAILURE_CLASSES else 'Exception'
    counts = report['retrieval_failure_counts'][path]
    counts[name] = counts.get(name, 0) + 1


def counts_only(report) -> DiagnosticCounts:
    """Allowlisted names only, including when projecting a historical report."""
    return {
        'retrieval_failure_counts': {
            path: {
                name: max(0, int(count))
                for name, count in report.get('retrieval_failure_counts', {}).get(path, {}).items()
                if name in FAILURE_CLASSES
            }
            for path in PATHS
        },
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
        'input_content_counts': {
            key: max(0, int(report.get('input_content_counts', {}).get(key, 0))) for key in INPUT_CONTENT_COUNTS
        },
        'context_budget_counts': {
            key: max(0, int(report.get('context_budget_counts', {}).get(key, 0))) for key in CONTEXT_BUDGET_COUNTS
        },
    }
