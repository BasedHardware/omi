#!/usr/bin/env python3
# LIFECYCLE: permanent
"""SCA-2195 allowance parking migration. Dry-run is count-only and the default."""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

from google.api_core import exceptions as api_exceptions

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.batch_pipeline_allowance_migration import MigrationOwnerChanged, RowRateLimiter, apply_page, counts
from database.firestore_transaction_retry import FirestoreContentionExhausted, is_transaction_contention
from database.batch_pipeline_store import FirestoreStore
from utils.executors import shutdown_executors

# Transient Firestore/RPC classes. A page that fails with one of these is safe to
# replay: the failed page is never checkpointed and state-CAS makes re-parking a no-op.
RETRYABLE = (
    api_exceptions.Aborted,
    api_exceptions.DeadlineExceeded,
    api_exceptions.InternalServerError,
    api_exceptions.ResourceExhausted,
    api_exceptions.ServiceUnavailable,
    FirestoreContentionExhausted,
    MigrationOwnerChanged,
)


def _type_name(error: BaseException) -> str:
    kind = type(error)
    return f'{kind.__module__}.{kind.__qualname__}'


def _chain(error: BaseException) -> list[BaseException]:
    links, seen, current = [], set(), error
    while current is not None and id(current) not in seen:
        links.append(current)
        seen.add(id(current))
        # Explicit causes only. google.api_core.RetryError keeps its last error on
        # ``.cause`` rather than ``__cause__``; implicit context is incidental.
        cause = current.__cause__
        if cause is None and isinstance(current, api_exceptions.RetryError):
            cause = current.cause
        current = cause
    return links


def _qualifies(link: BaseException) -> bool:
    return isinstance(link, RETRYABLE) or is_transaction_contention(link)


def _retryable(error: BaseException) -> bool:
    # Retry only when some link is a safe replay and no link is a fatal RPC
    # status (for example DeadlineExceeded caused by PermissionDenied). Generic
    # wrappers such as RuntimeError or RetryError neither qualify nor veto.
    links = _chain(error)
    fatal = any(isinstance(link, api_exceptions.GoogleAPICallError) and not _qualifies(link) for link in links)
    return not fatal and any(_qualifies(link) for link in links)


def error_report(error: BaseException) -> dict:
    """Classify a stop without printing any message, which can name documents.

    Retryable only when the stop and every concurrent owner group's failure are
    transient or a safe page replay.
    """
    siblings = tuple(getattr(error, 'migration_sibling_errors', ()))
    links = _chain(error)
    report = {
        'errors': 1 + len(siblings),
        'error_type': _type_name(error),
        'retryable': all(_retryable(failure) for failure in (error, *siblings)),
    }
    if len(links) > 1:
        report['cause_types'] = [_type_name(link) for link in links[1:]]
    if siblings:
        report['sibling_types'] = sorted({_type_name(failure) for failure in siblings})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prod', 'dev'), required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-reviewed-rollout-go', action='store_true')
    parser.add_argument('--max-pages', type=int, default=1)
    parser.add_argument('--concurrency', type=int, default=1, help='concurrent owners, 1..32 (default: sequential)')
    parser.add_argument('--max-rows-per-second', type=float, help='shared transaction-attempt rate, including retries')
    args = parser.parse_args()
    if args.apply and (args.dry_run or not args.confirm_reviewed_rollout_go):
        parser.error('apply requires reviewed migration and rollout go; cannot combine with dry-run')
    if not 1 <= args.max_pages <= 10000:
        parser.error('max-pages must be 1..10000')
    if not 1 <= args.concurrency <= 32:
        parser.error('concurrency must be 1..32')
    try:
        limiter = RowRateLimiter(args.max_rows_per_second)
    except ValueError as error:
        parser.error(str(error))
    if args.stage == 'prod' and (
        os.getenv('FIRESTORE_EMULATOR_HOST')
        or os.getenv('GCP_AGENT_TIER') != ('prod-operator' if args.apply else 'ro-prod')
    ):
        parser.error('wrong identity for production operation')
    logging.disable(logging.CRITICAL)
    os.environ['OMI_ENV_STAGE'] = args.stage
    store = FirestoreStore(f'batch_pipeline_{args.stage}')
    if not args.apply:
        print(json.dumps(counts(store)))
        return
    try:
        for _ in range(args.max_pages):
            report = apply_page(store, time.time(), concurrency=args.concurrency, rate_limiter=limiter)
            print(json.dumps(report), flush=True)
            if report['complete']:
                break
    finally:
        if args.concurrency > 1:
            shutdown_executors()


def run() -> int:
    try:
        main()
    except Exception as error:
        print(json.dumps(error_report(error)), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(run())
