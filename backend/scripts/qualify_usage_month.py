#!/usr/bin/env python3
"""Offline monthly-reader qualification; consumes evidence, never contacts a service.

See backend/docs/monthly-usage-totals.md for the attestation format. A qualified
report is technical evidence only: enabling either lever still requires lead2.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SERVICES = ('backend', 'backend-integration', 'backend-sync-backfill')
WRITERS = ('listen', 'pusher', 'backend', 'sync', 'backfill', 'integration', 'desktop', 'operator', 'migration')
# Reuse the existing serving/allowance, invalidation and transactional proofs.
# No second implementation of usage arithmetic or equivalence lives here.
SUITES = {
    'cache': {
        'tests.unit.test_fsr_s4_caches': {
            'test_usage_month_counts_and_writer_never_undercounts': 2,
            'test_usage_month_and_launch_boundary_separate': 1,
            'test_usage_allowance_exhausts_immediately_after_write': 1,
        },
    },
    'total': {
        'tests.unit.test_monthly_usage_totals': {
            'test_one_read_replaces_month_scan_with_identical_result': 5,
            'test_free_and_paid_allowance_remain_identical_through_real_resolver': 4,
        },
        'tests.integration.test_monthly_usage_totals_firestore': {
            'test_bootstrap_late_updates_current_hour_and_month_rollover': 1,
            'test_concurrent_duplicate_receipt_and_cold_seeding': 1,
            'test_epoch_rebuild_recovers_old_writer_rollback': 1,
        },
    },
}


def junit_blockers(paths: Path | list[Path], suites: dict[str, dict[str, int]]) -> list[str]:
    """Read file-isolated proof runs; missing, skipped or failed cases block."""
    cases, errors = [], []
    for path in [paths] if isinstance(paths, Path) else paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            errors.append(f'equivalence report unreadable: {path}')
            continue
        cases.extend(root.findall('.//testcase'))
        if root.findall('.//failure') or root.findall('.//error') or root.findall('.//skipped'):
            errors.append(f'equivalence report contains failures, errors or skips: {path}')
    for suite, names in suites.items():
        for name, count in names.items():
            matches = [c for c in cases if c.get('classname') == suite and c.get('name', '').split('[')[0] == name]
            if len(matches) != count or len({c.get('name') for c in matches}) != count:
                errors.append(f'missing/incomplete existing equivalence check: {suite}.{name} (requires {count} cases)')
    return errors


def _window(record: dict, now: datetime, label: str) -> list[str]:
    try:
        start = datetime.fromisoformat(record['started_at'])
        end = datetime.fromisoformat(record['ended_at'])
        valid = datetime.fromisoformat(record['valid_until'])
        if start.tzinfo is None or end.tzinfo is None or valid.tzinfo is None:
            raise ValueError('timezone required')
        if not start < end <= now < valid:
            raise ValueError('future, expired or inverted evidence')
    except (KeyError, TypeError, ValueError):
        return [f'{label}: missing/invalid observation window or expired evidence']
    return []


def _reference(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _serving(record: dict, now: datetime, service: str) -> list[str]:
    errors = _window(record, now, service)
    sha = record.get('source_sha')
    if (
        not _reference(record.get('ref'))
        or not _reference(record.get('artifact'))
        or not isinstance(sha, str)
        or not re.fullmatch('[0-9a-f]{40}', sha)
    ):
        errors.append(f'{service}: missing serving artifact, source SHA or evidence ref')
    if record.get('traffic_verified') is not True:
        errors.append(f'{service}: actual serving traffic not attested')
    return errors


def qualify(evidence: dict, *, now: datetime, base: Path) -> dict:
    """Evaluate runbook attestations separately for each service and lever.

    Attestations must cite their owning receipts. This evaluates their declared
    contract; it does not independently authenticate external receipts/artifacts.
    """
    result = {}
    writers = evidence.get('writers', {})
    for service in SERVICES:
        record = evidence.get('services', {}).get(service, {})
        common = _serving(record, now, service)
        soak = record.get('soak', {})
        common.extend(_window(soak, now, 'synthetic/loopback soak'))
        try:
            if (
                datetime.fromisoformat(soak['ended_at']) - datetime.fromisoformat(soak['started_at'])
            ).total_seconds() < 7200:
                common.append('synthetic/loopback soak is shorter than two hours')
        except (KeyError, TypeError, ValueError):
            pass  # _window already reports malformed timestamps
        try:
            if datetime.fromisoformat(record['started_at']) > datetime.fromisoformat(
                soak['started_at']
            ) or datetime.fromisoformat(record['ended_at']) < datetime.fromisoformat(soak['ended_at']):
                common.append('soak is outside the verified serving-traffic window')
        except (KeyError, TypeError, ValueError):
            pass  # malformed windows already block qualification
        if (
            soak.get('artifact') != record.get('artifact')
            or not _reference(soak.get('artifact'))
            or not _reference(soak.get('ref'))
        ):
            common.append('soak is not bound to the serving artifact and evidence ref')
        for field in (
            'mismatches',
            'accounting_regressions',
            'free_allowance_regressions',
            'http_5xx_regressions',
            'live_p95_regressions',
            'contention_errors',
        ):
            if type(soak.get(field)) is not int or soak[field] != 0:
                common.append(f'soak: {field} must be measured and zero')
        for field in ('origins_reviewed', 'fallback_rate_reviewed'):
            if soak.get(field) is not True:
                common.append(f'soak: {field} not attested')
        modes = {}
        for mode, suites in SUITES.items():
            blockers = common.copy()
            checks = record.get('equivalence', {}).get(mode, {})
            if checks.get('source_sha') != record.get('source_sha') or not _reference(checks.get('ref')):
                blockers.append('existing equivalence checks not bound to serving source and evidence ref')
            junit = checks.get('junit')
            paths = junit if isinstance(junit, list) else [junit]
            if paths and all(isinstance(path, str) and path for path in paths):
                blockers.extend(junit_blockers([base / path for path in paths], suites))
            else:
                blockers.append(f'missing existing {mode} equivalence JUnit report')
            for writer in WRITERS:
                row = writers.get(writer, {})
                blockers.extend(_window(row, now, f'writer {writer}'))
                try:
                    if datetime.fromisoformat(row['ended_at']) > datetime.fromisoformat(soak['started_at']):
                        blockers.append(f'writer {writer}: qualification/drain evidence must precede the soak')
                except (KeyError, TypeError, ValueError):
                    pass  # malformed windows already block qualification
                contract = 'invalidates_cache' if mode == 'cache' else 'maintains_totals'
                if (
                    row.get(contract) is not True
                    or row.get('old_revisions_jobs_drained') is not True
                    or not _reference(row.get('artifact'))
                    or not _reference(row.get('ref'))
                ):
                    blockers.append(f'writer {writer}: {contract}/artifact/drain evidence incomplete')
            if mode == 'cache':
                if record.get('cache_freshness_accepted') is not True:
                    blockers.append('60-second cache freshness not accepted for this service/admission scope')
            else:
                existing = evidence.get('services', {}).get('backend-sync', {})
                blockers.extend(_serving(existing, now, 'existing reader backend-sync'))
                if existing.get('epoch') != evidence.get('common_epoch'):
                    blockers.append('existing reader backend-sync must use the same qualified common epoch')
                epoch = record.get('epoch', '')
                if (
                    not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', epoch)
                    or epoch == 'v1'
                    or epoch != evidence.get('common_epoch')
                ):
                    blockers.append('missing/invalid qualified common production epoch (v1 is not approved)')
                if evidence.get('old_writers_since_initialization') is not False:
                    previous = evidence.get('previous_epoch')
                    if (
                        not isinstance(previous, str)
                        or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', previous)
                        or previous == epoch
                    ):
                        blockers.append('old-writer history unknown/positive: a new common epoch is required')
            modes[f'usage_month_{mode}'] = {'qualified': not blockers, 'blockers': blockers}
        result[service] = modes
    return {'authorization': 'HOLD: lead2 ruling required; this report never enables levers', 'services': result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--evidence', type=Path, help='offline operator attestations; omission reports all missing gates'
    )
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(args.evidence.read_text()) if args.evidence else {}
        report = qualify(
            evidence, now=datetime.now(timezone.utc), base=args.evidence.parent if args.evidence else Path.cwd()
        )
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        parser.error(f'invalid qualification evidence: {type(exc).__name__}')
    print(json.dumps(report, indent=2))
    return 0 if all(m['qualified'] for s in report['services'].values() for m in s.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
