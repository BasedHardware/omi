#!/usr/bin/env python3
"""Legacy-dark soak checks (contract (h)), run every 30 minutes by the sentinel.

    soak_check.py --env prod --draining-since 2026-10-21T14:00:00Z --dark-since 2026-10-21T15:10:00Z \\
        --fleet-output fleet.txt [--evidence soak_evidence.json] [--collect] \\
        [--history-dir <run-dir>/soak-reads] --output soak_report.json

The soak is evidence-based with a 6h floor (David, 2026-10-20), replacing the 12h clock. One read
judges the ten checks below; ``--history-dir`` keeps every read and judges the WINDOW, which is what
authorizes deletion. ``evaluate_window`` passes only when ALL of:
  * the last read is at least 6h after ``dark`` (MIN_SOAK_SECONDS);
  * every read since ``dark`` is SOAK_PASS (all ten checks green), with no gap over 45 minutes
    between ``dark``, consecutive reads and now, so the window has no unobserved stretch;
  * the last read carries a fresh final lost-recordings census (check 5, census ``until`` within
    ``lost_recordings.GRACE_SECONDS`` + 15 minutes of that read);
  * the window saw traffic (WINDOW_FLOORS): the last read's fleet gate, run from ``dark``, counts at
    least ``batch_completions`` batch units completed, and the census counted at least
    ``uploads_accepted`` more accepted content ids at the last read than at the first read after ``dark``.
Any FAIL read fails the window. Anything else short (a PENDING read, a gap, a stale census, a floor
not met, a field missing) is PENDING, never PASS.

Checks (all must hold continuously):
  1  fleet_gate          fleet gate PASS at 100%                   (--fleet-output: captured fleet_gate.sh stdout)
  2  legacy_admissions   legacy admissions = 0 since draining      (PromQL omi_legacy_sync_admissions_total)
  3  legacy_queues       sync-jobs, sync-jobs-fresh, sync-backfill, sync-backfill-fresh depth = 0
  4  task_target_errors  zero task-target 5xx, 429 or 503 since dark
  5  lost_recordings     every content_id accepted since DRAINING (not dark) has a projection receipt
                         or terminal disposition; no content_id has both a legacy job and a batch unit
  6  provider_stt        BYOK and non-Parakeet uploads served by provider_stt, or zero traffic
  7  cap_hold            cap-hold redrives served by batch
  8  first_summary       first-summary dispatch contract (120s), no breach
  9  upload_2xx          upload 2xx rate per app_build within 1pp of the pre-dark 24h baseline
 10  reason_unknown      omi:reason_unknown_ratio < 2% on every family

``--collect`` fills checks 2, 3, 4 and 10 from live reads on the read-only tier
for ``--env`` (ro-prod / ro-dev); the caller sources gcp-agent-env.sh. Checks
5, 6, 7 and 9 come from ``--evidence`` (lane 10's drain census, lane 8's
provider-STT and cap-hold counters, the upload census). Anything unmeasured is
PENDING, never PASS.

Exit: 0 SOAK_PASS, 1 SOAK_FAIL <check>, 3 SOAK_PENDING <check>; with ``--history-dir`` the exit and
the last line (``SOAK_WINDOW_<STATUS> <reason>``) are the window's. A FAIL on
checks 2 or 5 sets ``data_loss=true``: the lead's one rollback is
``legacy_sync -> on``. Output holds counts and fixed tokens only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.parity import fleet_sample  # noqa: E402
from scripts.parity.report_schema import THRESHOLDS  # noqa: E402

SCHEMA_VERSION = 1
PASS, FAIL, PENDING = 'PASS', 'FAIL', 'PENDING'
EXIT = {PASS: 0, FAIL: 1, PENDING: 3}
CHECKS = (
    'fleet_gate',
    'legacy_admissions',
    'legacy_queues',
    'task_target_errors',
    'lost_recordings',
    'provider_stt',
    'cap_hold',
    'first_summary',
    'upload_2xx',
    'reason_unknown',
)
DATA_LOSS_CHECKS = frozenset({'legacy_admissions', 'lost_recordings'})
UPLOAD_2XX_MAX_DROP = 0.01
UPLOAD_2XX_MIN_REQUESTS = 50
REASON_UNKNOWN_MAX = 0.02

# Window (David, 2026-10-20: evidence-based soak with a 6h floor, replacing the 12h clock).
MIN_SOAK_SECONDS = 6 * 3600
READ_MAX_GAP_SECONDS = 45 * 60  # reads run every 30 minutes; one late read is tolerated, a missed one is not
CENSUS_GRACE_SECONDS = 3600  # scripts/legacy_dark/lost_recordings.py GRACE_SECONDS
FINAL_CENSUS_MAX_AGE_SECONDS = CENSUS_GRACE_SECONDS + 15 * 60
# Minimum traffic the window must have seen. Prod at 5% completed ~225-430 batch units an hour in daytime,
# so 100% completes thousands an hour; the floors sit far below a 6h night so that a dead or empty
# pipeline cannot pass on silence. Staging carries only rehearsal traffic.
WINDOW_FLOORS = {
    'prod': {'batch_completions': 2000, 'uploads_accepted': 1000},
    'staging': {'batch_completions': 20, 'uploads_accepted': 20},
}

ENVS = {
    'prod': {
        'project': 'based-hardware',
        'tier': 'ro-prod',
        'queues': ('sync-jobs', 'sync-jobs-fresh', 'sync-backfill', 'sync-backfill-fresh'),
    },
    'staging': {
        'project': 'based-hardware-dev',
        'tier': 'ro-dev',
        'queues': (
            'staging-sync-jobs',
            'staging-sync-jobs-fresh',
            'staging-sync-backfill',
            'staging-sync-backfill-fresh',
        ),
    },
}
REGION = 'us-central1'


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _cnt(mapping: Mapping[str, Any] | None, key: str) -> int | None:
    value = _num((mapping or {}).get(key))
    if value is None or value < 0 or value != int(value):
        return None
    return int(value)


def _check(name, status, reason, measured=None):
    return {'check': name, 'status': status, 'reason': reason, 'measured': measured or {}}


# --- pure evaluators --------------------------------------------------------------------------


def check_fleet_gate(gate: Mapping[str, Any] | None):
    if not gate or not gate.get('status'):
        return _check('fleet_gate', PENDING, 'input_missing')
    sample = gate.get('sample') or {}
    measured = {
        'status': gate['status'],
        'reason': gate.get('reason'),
        'percent': gate.get('percent'),
        # Since the gate's T0 (`dark` in the soak): the window's batch-completion volume.
        'admissions': _cnt(sample, 'admissions'),
        'completed': _cnt(sample, 'completed'),
    }
    if gate['status'] == 'FAIL':
        token = gate.get('reason') or 'unknown'
        return _check('fleet_gate', FAIL, 'gate_fail_' + token, measured)
    if gate['status'] != 'PASS':
        return _check('fleet_gate', PENDING, 'gate_' + str(gate['status']).lower(), measured)
    if _num(gate.get('percent')) != 100.0:
        return _check('fleet_gate', FAIL, 'gate_not_at_100', measured)
    return _check('fleet_gate', PASS, 'pass', measured)


def check_legacy_admissions(ev):
    value = _num((ev or {}).get('legacy_admissions_since_draining'))
    if value is None:
        return _check('legacy_admissions', PENDING, 'input_missing')
    measured = {'legacy_admissions_since_draining': value}
    # increase() on a counter can return small fractions; any visible increase is a creation.
    if value >= 0.5:
        return _check('legacy_admissions', FAIL, 'legacy_admission_in_dark', measured)
    return _check('legacy_admissions', PASS, 'pass', measured)


def check_legacy_queues(ev, required: tuple[str, ...]):
    depths = (ev or {}).get('legacy_queue_depths') or {}
    measured = {q: depths.get(q) for q in required}
    missing = [q for q in required if _cnt(depths, q) is None]
    nonzero = [q for q in required if (_cnt(depths, q) or 0) > 0]
    if nonzero:
        return _check('legacy_queues', FAIL, 'legacy_queue_not_empty', measured)
    if missing:
        return _check('legacy_queues', PENDING, 'queue_depth_unmeasured', measured)
    return _check('legacy_queues', PASS, 'pass', measured)


def check_task_target_errors(ev):
    errors = (ev or {}).get('task_target_errors')
    if not isinstance(errors, Mapping):
        return _check('task_target_errors', PENDING, 'input_missing')
    counts = {k: _cnt(errors, k) for k in ('5xx', '429', '503')}
    if any(v is None for v in counts.values()):
        return _check('task_target_errors', PENDING, 'input_invalid', counts)
    if any(counts.values()):
        return _check('task_target_errors', FAIL, 'task_target_retryable_error_status', counts)
    return _check('task_target_errors', PASS, 'pass', counts)


def check_lost_recordings(ev, draining_since: float):
    lost = (ev or {}).get('lost_recordings')
    if not isinstance(lost, Mapping):
        return _check('lost_recordings', PENDING, 'input_missing')
    since = lost.get('since')
    accepted, accounted = _cnt(lost, 'accepted_content_ids'), _cnt(lost, 'receipted_or_terminal_content_ids')
    missing, double = _cnt(lost, 'lost_content_ids'), _cnt(lost, 'legacy_and_batch_content_ids')
    measured = {
        'accepted': accepted,
        'accounted': accounted,
        'lost': missing,
        'legacy_and_batch': double,
        'since': since,
        'until': lost.get('until'),
    }
    try:
        since_epoch = parse_iso(since)
    except ValueError:
        return _check('lost_recordings', PENDING, 'census_window_invalid', measured)
    if since_epoch > draining_since:
        # The census must start at `draining`, not `dark` (contract (h) check 5).
        return _check('lost_recordings', PENDING, 'census_starts_after_draining', measured)
    if None in (accepted, accounted, missing, double) or missing != accepted - accounted or accounted > accepted:
        return _check('lost_recordings', PENDING, 'input_invalid', measured)
    if missing:
        return _check('lost_recordings', FAIL, 'lost_recordings', measured)
    if double:
        return _check('lost_recordings', FAIL, 'double_processed_content_id', measured)
    return _check('lost_recordings', PASS, 'pass', measured)


def check_provider_stt(ev):
    stt = (ev or {}).get('provider_stt')
    if not isinstance(stt, Mapping):
        return _check('provider_stt', PENDING, 'input_missing')
    byok, lang = _cnt(stt, 'byok_uploads'), _cnt(stt, 'unsupported_language_uploads')
    served = _cnt(stt, 'served_by_provider_stt')
    measured = {'byok_uploads': byok, 'unsupported_language_uploads': lang, 'served_by_provider_stt': served}
    if byok is None or lang is None:
        return _check('provider_stt', PENDING, 'input_invalid', measured)
    if byok + lang == 0:
        return _check('provider_stt', PASS, 'zero_traffic', measured)
    if served is None:
        return _check('provider_stt', PENDING, 'input_invalid', measured)
    if served < byok + lang:
        return _check('provider_stt', FAIL, 'provider_stt_not_serving', measured)
    return _check('provider_stt', PASS, 'pass', measured)


def check_cap_hold(ev):
    cap = (ev or {}).get('cap_hold')
    if not isinstance(cap, Mapping):
        return _check('cap_hold', PENDING, 'input_missing')
    total, batch = _cnt(cap, 'redrives_total'), _cnt(cap, 'redrives_served_by_batch')
    measured = {'redrives_total': total, 'redrives_served_by_batch': batch}
    if total is None or batch is None:
        return _check('cap_hold', PENDING, 'input_invalid', measured)
    if batch < total:
        return _check('cap_hold', FAIL, 'cap_hold_redrive_not_batch', measured)
    return _check('cap_hold', PASS, 'pass' if total else 'zero_traffic', measured)


def check_first_summary(sample: Mapping[str, Any] | None):
    if not sample:
        return _check('first_summary', PENDING, 'input_missing')
    breaches = _cnt(sample, 'first_summary_dispatch_breaches')
    measured_count = _cnt(sample, 'first_summary_dispatch_measured_count')
    max_seconds = _num(sample.get('first_summary_dispatch_max_seconds'))
    measured = {
        'dispatch_breaches': breaches,
        'dispatch_measured': measured_count,
        'dispatch_max_seconds': max_seconds,
        'status': sample.get('first_summary_status'),
    }
    if breaches is None or measured_count is None or (measured_count and max_seconds is None):
        # Without the measured max the strict 121s limit cannot be checked.
        return _check('first_summary', PENDING, 'input_invalid', measured)
    # The gate's breach counter allows 120s + 5s; the contract's limit is strict 121s (parity row 3).
    strict = fleet_sample.row3_aggregates(sample, None)['first_summary_dispatch_breaches_over_121s']
    measured['dispatch_breaches_over_121s'] = strict
    if strict or sample.get('first_summary_status') == 'FAIL':
        return _check('first_summary', FAIL, 'first_summary_dispatch_contract', measured)
    if measured_count < THRESHOLDS.first_summary_min_dispatches:
        # A zero breach count over too few measured dispatches is not evidence of the contract.
        return _check('first_summary', PENDING, 'sample_below_minimum', measured)
    return _check('first_summary', PASS, 'pass', measured)


def check_upload_2xx(ev):
    """Per app_build: a 2xx-rate DROP of more than 1pp against the pre-dark 24h baseline fails.

    Builds with fewer than 50 requests in the window are reported, not judged.
    """
    builds = (ev or {}).get('upload_2xx_by_build')
    if not isinstance(builds, Mapping) or not builds:
        return _check('upload_2xx', PENDING, 'input_missing')
    worst, judged, failing = 0.0, 0, 0
    for row in builds.values():
        current, baseline, n = _num(row.get('rate')), _num(row.get('baseline_rate')), _cnt(row, 'requests')
        if current is None or baseline is None or n is None:
            return _check('upload_2xx', PENDING, 'input_invalid')
        if n < UPLOAD_2XX_MIN_REQUESTS:
            continue
        judged += 1
        drop = baseline - current
        worst = max(worst, drop)
        failing += drop > UPLOAD_2XX_MAX_DROP
    measured = {
        'builds': len(builds),
        'judged_builds': judged,
        'failing_builds': failing,
        'worst_drop_pp': round(worst * 100, 3),
    }
    if failing:
        return _check('upload_2xx', FAIL, 'upload_2xx_drop_over_1pp', measured)
    if not judged:
        return _check('upload_2xx', PENDING, 'sample_below_minimum', measured)
    return _check('upload_2xx', PASS, 'pass', measured)


def check_reason_unknown(ev):
    ratios = (ev or {}).get('reason_unknown_ratio')
    if not isinstance(ratios, Mapping) or not ratios:
        return _check('reason_unknown', PENDING, 'input_missing')
    values = {k: _num(v) for k, v in ratios.items()}
    if any(v is None for v in values.values()):
        return _check('reason_unknown', PENDING, 'input_invalid', values)
    over = sorted(k for k, v in values.items() if v >= REASON_UNKNOWN_MAX)
    measured = {'families': len(values), 'over_limit_families': over, 'max': max(values.values())}
    if over:
        return _check('reason_unknown', FAIL, 'reason_unknown_over_2pct', measured)
    return _check('reason_unknown', PASS, 'pass', measured)


def evaluate(
    env: str, evidence: Mapping[str, Any], gate: Mapping[str, Any] | None, *, draining_since: float, dark_since: float
) -> dict[str, Any]:
    sample = (gate or {}).get('sample')
    checks = [
        check_fleet_gate(gate),
        check_legacy_admissions(evidence),
        check_legacy_queues(evidence, ENVS[env]['queues']),
        check_task_target_errors(evidence),
        check_lost_recordings(evidence, draining_since),
        check_provider_stt(evidence),
        check_cap_hold(evidence),
        check_first_summary(sample),
        check_upload_2xx(evidence),
        check_reason_unknown(evidence),
    ]
    failed = [c for c in checks if c['status'] == FAIL]
    pending = [c for c in checks if c['status'] == PENDING]
    data_loss = any(c['check'] in DATA_LOSS_CHECKS for c in failed) or any(
        c['check'] == 'fleet_gate' and fleet_sample.is_data_loss_token((gate or {}).get('reason')) for c in failed
    )
    if failed:
        loss_first = [c for c in failed if c['check'] in DATA_LOSS_CHECKS]
        status, first = FAIL, (loss_first or failed)[0]
    elif pending:
        status, first = PENDING, pending[0]
    else:
        status, first = PASS, None
    return {
        'schema_version': SCHEMA_VERSION,
        'env': env,
        'status': status,
        'failing_check': None if first is None else first['check'],
        'reason': 'pass' if first is None else first['reason'],
        'data_loss': data_loss,
        'draining_since': iso(draining_since),
        'dark_since': iso(dark_since),
        'soak_elapsed_seconds': None,
        'checks': checks,
    }


def verdict_line(report: Mapping[str, Any]) -> str:
    if report['status'] == PASS:
        return 'SOAK_PASS'
    return f"SOAK_{report['status']} {report['failing_check']}:{report['reason']}"


def _measured(report: Mapping[str, Any], check: str) -> Mapping[str, Any]:
    for item in report.get('checks') or []:
        if isinstance(item, Mapping) and item.get('check') == check:
            return item.get('measured') or {}
    return {}


def _read_time(report: Mapping[str, Any]) -> float | None:
    try:
        return parse_iso(report.get('observed_at'))
    except ValueError:
        return None


def evaluate_window(env: str, reads: list[Mapping[str, Any]], *, dark_since: float, now: float) -> dict[str, Any]:
    """Judge the whole soak from every read since ``dark`` (module docstring). Fail closed: PENDING
    whenever evidence is missing; FAIL only on a FAIL read."""
    floors = WINDOW_FLOORS[env]
    out: dict[str, Any] = {
        'status': PENDING,
        'reason': None,
        'reads': len(reads),
        'dark_since': iso(dark_since),
        'min_soak_seconds': MIN_SOAK_SECONDS,
        'elapsed_seconds': None,
        'max_gap_seconds': None,
        'batch_completions': None,
        'uploads_accepted': None,
        'floors': dict(floors),
        'failing_read': None,
        'data_loss': False,
    }

    def verdict(status: str, reason: str, read: Mapping[str, Any] | None = None) -> dict[str, Any]:
        out.update(status=status, reason=reason)
        if read is not None:
            out['failing_read'] = read.get('observed_at')
        return out

    timed = []
    for read in reads:
        at = _read_time(read)
        if (
            read.get('schema_version') != SCHEMA_VERSION
            or read.get('env') != env
            or read.get('dark_since') != iso(dark_since)
            or read.get('status') not in EXIT
            or at is None
            or at < dark_since
        ):
            return verdict(PENDING, 'read_from_other_window', read)
        timed.append((at, read))
    if not timed:
        return verdict(PENDING, 'no_reads')
    timed.sort(key=lambda pair: pair[0])
    failed = [read for _, read in timed if read['status'] == FAIL]
    if failed:
        first = next((r for r in failed if r.get('data_loss')), failed[0])
        out['data_loss'] = any(bool(r.get('data_loss')) for r in failed)
        return verdict(FAIL, f"read_failed:{first.get('failing_check')}:{first.get('reason')}", first)
    not_green = next((read for _, read in timed if read['status'] != PASS), None)
    if not_green is not None:
        return verdict(PENDING, f"read_not_green:{not_green.get('failing_check')}:{not_green.get('reason')}", not_green)

    first_at, first = timed[0]
    last_at, last = timed[-1]
    out['elapsed_seconds'] = round(last_at - dark_since, 1)
    edges = [dark_since, *(at for at, _ in timed), max(now, last_at)]
    out['max_gap_seconds'] = round(max(b - a for a, b in zip(edges, edges[1:])), 1)
    if out['max_gap_seconds'] > READ_MAX_GAP_SECONDS:
        return verdict(PENDING, 'read_gap')
    if last_at - dark_since < MIN_SOAK_SECONDS:
        return verdict(PENDING, 'soak_under_6h')

    # Check 5's final census: taken at the last read, not carried over from an earlier one.
    census = _measured(last, 'lost_recordings')
    try:
        until = parse_iso(census.get('until'))
    except ValueError:
        return verdict(PENDING, 'final_census_window_missing', last)
    if until < last_at - FINAL_CENSUS_MAX_AGE_SECONDS:
        return verdict(PENDING, 'final_census_stale', last)

    completions = _cnt(_measured(last, 'fleet_gate'), 'completed')
    accepted_first = _cnt(_measured(first, 'lost_recordings'), 'accepted')
    accepted_last = _cnt(census, 'accepted')
    out['batch_completions'] = completions
    if accepted_first is not None and accepted_last is not None:
        out['uploads_accepted'] = accepted_last - accepted_first
    if completions is None or out['uploads_accepted'] is None:
        return verdict(PENDING, 'window_volume_unmeasured')
    if completions < floors['batch_completions']:
        return verdict(PENDING, 'batch_completions_below_floor')
    if out['uploads_accepted'] < floors['uploads_accepted']:
        return verdict(PENDING, 'uploads_accepted_below_floor')
    return verdict(PASS, 'pass')


def window_line(window: Mapping[str, Any]) -> str:
    return f"SOAK_WINDOW_{window['status']} {window['reason']}"


def load_reads(directory: Path) -> list[dict[str, Any]] | None:
    """Every ``read-*.json`` in the history dir; None if any is unreadable (the window is then PENDING)."""
    reads = []
    for path in sorted(directory.glob('read-*.json')):
        try:
            value = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        reads.append(value)
    return reads


# --- time helpers -----------------------------------------------------------------------------


def parse_iso(value: Any) -> float:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('timestamp must be ISO UTC with Z')
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace('+00:00', 'Z')


# --- live collectors (read-only tier) ----------------------------------------------------------


class CollectError(Exception):
    """Fixed, content-free collector errors only."""


def _token() -> str:
    try:
        out = subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        raise CollectError('token_unavailable') from None
    if out.returncode or not out.stdout.strip():
        raise CollectError('token_unavailable')
    return out.stdout.strip()


def _get_json(url: str, token: str, opener: Callable = urllib.request.urlopen) -> Any:
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        with opener(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise CollectError('read_denied' if error.code in (401, 403) else 'read_failed') from None
    except (urllib.error.URLError, OSError, ValueError):
        raise CollectError('read_failed') from None


def queue_depths(project: str, queues: tuple[str, ...], token: str, opener: Callable = urllib.request.urlopen):
    """Cloud Tasks v2beta3 GetQueue with readMask=stats; ``tasksCount`` per queue (None if unreadable)."""
    out: dict[str, int | None] = {}
    for queue in queues:
        url = (
            f'https://cloudtasks.googleapis.com/v2beta3/projects/{project}/locations/{REGION}/queues/{queue}'
            '?readMask=stats'
        )
        try:
            body = _get_json(url, token, opener)
            out[queue] = int((body.get('stats') or {}).get('tasksCount', 0))
        except (CollectError, TypeError, ValueError):
            out[queue] = None
    return out


def promql(project: str, query: str, token: str, opener: Callable = urllib.request.urlopen) -> list[dict]:
    url = (
        f'https://monitoring.googleapis.com/v1/projects/{project}/location/global/prometheus/api/v1/query?'
        + urllib.parse.urlencode({'query': query})
    )
    body = _get_json(url, token, opener)
    if body.get('status') != 'success':
        raise CollectError('promql_failed')
    return body.get('data', {}).get('result', [])


def legacy_admissions_since(project: str, seconds: int, token: str, opener=urllib.request.urlopen) -> float | None:
    result = promql(project, f'sum(increase(omi_legacy_sync_admissions_total[{max(60, seconds)}s]))', token, opener)
    if not result:
        return None  # the series does not exist yet: unmeasured, never zero
    return float(result[0]['value'][1])


def reason_unknown_ratios(project: str, token: str, opener=urllib.request.urlopen) -> dict[str, float]:
    result = promql(project, 'max by (family) (omi:reason_unknown_ratio:rate30m)', token, opener)
    return {r['metric'].get('family', 'unknown'): float(r['value'][1]) for r in result}


def task_target_errors(project: str, since: float, *, runner=subprocess.run) -> dict[str, int]:
    """Cloud Tasks deliveries (User-Agent Google-Cloud-Tasks) answered 5xx or 429 since ``since``."""
    base = (
        'resource.type="cloud_run_revision" AND httpRequest.userAgent:"Google-Cloud-Tasks" '
        f'AND timestamp>="{iso(since)}" AND '
    )
    counts = {}
    for key, clause in (
        ('5xx', 'httpRequest.status>=500'),
        ('429', 'httpRequest.status=429'),
        ('503', 'httpRequest.status=503'),
    ):
        try:
            out = runner(
                [
                    'gcloud',
                    'logging',
                    'read',
                    base + clause,
                    '--project=' + project,
                    '--limit=1000',
                    '--format=value(insertId)',
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise CollectError('task_target_logs_unavailable') from None
        if out.returncode:
            raise CollectError('task_target_logs_unavailable')
        counts[key] = len([line for line in out.stdout.splitlines() if line.strip()])
    return counts


def collect(env: str, draining_since: float, dark_since: float, now: float) -> dict[str, Any]:
    cfg = ENVS[env]
    token = _token()
    evidence: dict[str, Any] = {'legacy_queue_depths': queue_depths(cfg['project'], cfg['queues'], token)}
    for key, fn in (
        (
            'legacy_admissions_since_draining',
            lambda: legacy_admissions_since(cfg['project'], int(now - draining_since), token),
        ),
        ('reason_unknown_ratio', lambda: reason_unknown_ratios(cfg['project'], token)),
        ('task_target_errors', lambda: task_target_errors(cfg['project'], dark_since)),
    ):
        try:
            evidence[key] = fn()
        except CollectError:
            evidence[key] = None
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Legacy-dark soak checks and the 6h-floor window (contract (h)).')
    parser.add_argument('--env', choices=sorted(ENVS), default='prod')
    parser.add_argument('--draining-since', required=True)
    parser.add_argument('--dark-since', required=True)
    parser.add_argument('--fleet-output', type=Path, help='captured fleet_gate.sh stdout (run at percent 100)')
    parser.add_argument('--evidence', type=Path, help='census JSON for checks 5, 6, 7, 9 (and overrides)')
    parser.add_argument('--collect', action='store_true', help='live read-only collection for checks 2, 3, 4, 10')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument(
        '--history-dir',
        type=Path,
        help='keep this read as read-<time>.json here and judge the whole window (one dir per dark write)',
    )
    args = parser.parse_args(argv)
    try:
        draining, dark = parse_iso(args.draining_since), parse_iso(args.dark_since)
    except ValueError:
        print('SOAK_PENDING arguments:timestamp_invalid', flush=True)
        return EXIT[PENDING]
    if dark < draining:
        print('SOAK_PENDING arguments:dark_before_draining', flush=True)
        return EXIT[PENDING]
    now = time.time()
    evidence: dict[str, Any] = {}
    if args.collect:
        try:
            evidence.update(collect(args.env, draining, dark, now))
        except CollectError as error:
            evidence['collect_error'] = str(error)
    if args.evidence is not None:
        try:
            evidence.update(json.loads(args.evidence.read_text()))
        except (OSError, ValueError):
            print('SOAK_PENDING evidence:unreadable', flush=True)
            return EXIT[PENDING]
    gate = None
    if args.fleet_output is not None:
        try:
            sample, status, reason = fleet_sample.parse_gate_output(args.fleet_output.read_text().splitlines())
        except OSError:
            sample, status, reason = None, None, None
        gate = {'status': status, 'reason': reason, 'sample': sample, 'percent': (sample or {}).get('percent')}
    report = evaluate(args.env, evidence, gate, draining_since=draining, dark_since=dark)
    report['soak_elapsed_seconds'] = round(max(0.0, now - dark), 1)
    report['observed_at'] = iso(now)
    report['collect_error'] = evidence.get('collect_error')
    window = None
    if args.history_dir is not None:
        try:
            args.history_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            (args.history_dir / f'read-{stamp}.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
            reads = load_reads(args.history_dir)
        except OSError:
            reads = None
        if reads is None:
            window = {'status': PENDING, 'reason': 'history_unreadable'}
        else:
            window = evaluate_window(args.env, reads, dark_since=dark, now=now)
        report['window'] = window
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    for check in report['checks']:
        print(f"{check['check']:<20} {check['status']:<7} {check['reason']}", flush=True)
    print(verdict_line(report), flush=True)
    if window is not None:
        print(window_line(window), flush=True)
        return EXIT[window['status']]
    return EXIT[report['status']]


if __name__ == '__main__':
    sys.exit(main())
