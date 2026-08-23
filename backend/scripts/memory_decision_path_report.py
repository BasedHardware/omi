#!/usr/bin/env python3
"""Measure canonical-memory capture and promotion decisions from Cloud Logging.

The production emitter writes ``canonical_memory_decision_path.v1`` as a
text-free JSON object inside a normal Python log message. This script can read
those entries directly with ``gcloud logging read`` or consume a saved JSON /
JSONL fixture. Aggregation is deliberately pure after ingestion so fixture and
live runs exercise the same code.

Rates are reported twice:

* event weighted, with a Wilson 95% interval and an explicit numerator and
  denominator;
* as the mean of per-user rates, with a user-clustered normal-approximation 95%
  interval. This keeps one high-volume account from becoming the population.

Owner-speaker health (owner-silent, single-owner, multi-owner) is measured only for
events carrying ``owner_speaker_ids``; older events are reported as ``absent``,
which is a statement about the telemetry and not about the conversation. Clean vs
degraded diarization remains unlabelled, so the report names its measured outcome
``attribution_disagreed`` and never treats it as a diarization-health label.

Examples:
    python scripts/memory_decision_path_report.py --input events.json --format human
    python scripts/memory_decision_path_report.py --input events.json --format json
    python scripts/memory_decision_path_report.py --days 7 --json-output report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

EVENT_NAME = 'canonical_memory_decision_path.v1'
REPORT_SCHEMA = 'canonical_memory_decision_path_analysis.v1'
DEFAULT_PROJECT = 'based-hardware'
DEFAULT_DAYS = 7
DEFAULT_LIMIT = 100_000
Z_95 = 1.959963984540054
SPEAKER_BUCKETS = ('0', '1-3', '4-6', '7-10', '11-15', '16+')
# An account has exactly one owner, so 'multi_owner' is impossible by construction
# and reads as shattered speaker clustering. 'absent' is telemetry emitted before
# owner_speaker_ids shipped; it is kept visible rather than folded into a real state.
OWNER_HEALTH_BUCKETS = ('owner_silent', 'single_owner', 'multi_owner', 'absent')

Event = dict[str, Any]
Rate = dict[str, Any]


def _parse_utc(value: str) -> datetime:
    normalized = value[:-1] + '+00:00' if value.endswith('Z') else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f'timestamp must include a UTC offset: {value!r}')
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_logging_filter(start: datetime, end: datetime) -> str:
    """Return the bounded filter for both plain and structured log messages."""
    return (
        f'timestamp>="{_utc_text(start)}" AND timestamp<"{_utc_text(end)}" AND '
        f'(textPayload:"{EVENT_NAME}" OR jsonPayload.message:"{EVENT_NAME}")'
    )


def fetch_cloud_logging_entries(
    *,
    project: str,
    start: datetime,
    end: datetime,
    limit: int,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[Any]:
    """Read a bounded Cloud Logging window without adding an SDK dependency."""
    command = [
        'gcloud',
        'logging',
        'read',
        build_logging_filter(start, end),
        f'--project={project}',
        f'--limit={limit}',
        '--order=asc',
        '--format=json',
    ]
    completed = run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or 'unknown gcloud error').strip().splitlines()[-1]
        raise RuntimeError(f'gcloud logging read failed: {detail}')
    try:
        decoded = json.loads(completed.stdout or '[]')
    except json.JSONDecodeError as exc:
        raise RuntimeError('gcloud logging read returned invalid JSON') from exc
    if not isinstance(decoded, list):
        raise RuntimeError('gcloud logging read did not return a JSON array')
    return decoded


def load_entries(path: str) -> tuple[list[Any], int]:
    """Read a JSON array/object or JSONL file. Returns entries and syntax errors."""
    text = sys.stdin.read() if path == '-' else Path(path).read_text(encoding='utf-8')
    if not text.strip():
        return [], 0
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        entries: list[Any] = []
        errors = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                errors += 1
        return entries, errors
    return (decoded if isinstance(decoded, list) else [decoded]), 0


def _event_message(entry: Mapping[str, Any]) -> str | None:
    text_payload = entry.get('textPayload')
    if isinstance(text_payload, str):
        return text_payload
    json_payload = entry.get('jsonPayload')
    if isinstance(json_payload, Mapping):
        message = json_payload.get('message')
        if isinstance(message, str):
            return message
    return None


def _decode_event(entry: Any, ordinal: int) -> tuple[Event | None, str | None]:
    if not isinstance(entry, Mapping):
        return None, 'entry_not_object'

    if entry.get('stage') in {'capture', 'promotion'}:
        event = dict(entry)
        timestamp = event.pop('timestamp', None)
    else:
        message = _event_message(entry)
        if message is None:
            return None, 'event_marker_missing'
        marker = f'{EVENT_NAME} '
        marker_index = message.find(marker)
        if marker_index < 0:
            return None, 'event_marker_missing'
        tail = message[marker_index + len(marker) :].lstrip()
        try:
            decoded, _ = json.JSONDecoder().raw_decode(tail)
        except json.JSONDecodeError:
            return None, 'event_json_invalid'
        if not isinstance(decoded, Mapping):
            return None, 'event_not_object'
        event = dict(decoded)
        timestamp = entry.get('timestamp')

    event['_ordinal'] = ordinal
    event['_timestamp'] = timestamp if isinstance(timestamp, str) else ''
    error = _validate_event(event)
    return (None, error) if error else (event, None)


def _nonempty_string(event: Mapping[str, Any], field: str) -> bool:
    return isinstance(event.get(field), str) and bool(str(event[field]).strip())


def _validate_event(event: Mapping[str, Any]) -> str | None:
    stage = event.get('stage')
    if stage not in {'capture', 'promotion'}:
        return 'stage_invalid'
    for field in ('uid', 'memory_id'):
        if not _nonempty_string(event, field):
            return f'{stage}_{field}_invalid'
    if stage == 'capture':
        for field in ('conversation_id', 'capture_regime', 'subject_attribution', 'model_about'):
            if not _nonempty_string(event, field):
                return f'capture_{field}_invalid'
        if not isinstance(event.get('attribution_disagreed'), bool):
            return 'capture_attribution_disagreed_invalid'
        speaker_count = event.get('distinct_speaker_ids')
        if isinstance(speaker_count, bool) or not isinstance(speaker_count, int) or speaker_count < 0:
            return 'capture_distinct_speaker_ids_invalid'
        # Optional: events emitted before the field shipped are valid, not invalid.
        owner_count = event.get('owner_speaker_ids')
        if owner_count is not None and (
            isinstance(owner_count, bool) or not isinstance(owner_count, int) or owner_count < 0
        ):
            return 'capture_owner_speaker_ids_invalid'
    else:
        for field in ('route', 'status', 'reason_code'):
            if not _nonempty_string(event, field):
                return f'promotion_{field}_invalid'
    return None


def parse_events(entries: Iterable[Any], *, syntax_errors: int = 0) -> tuple[list[Event], Counter[str]]:
    errors: Counter[str] = Counter()
    if syntax_errors:
        errors['input_json_invalid'] = syntax_errors
    events: list[Event] = []
    for ordinal, entry in enumerate(entries):
        event, error = _decode_event(entry, ordinal)
        if error:
            errors[error] += 1
        elif event is not None:
            events.append(event)
    return events, errors


def _event_order(event: Mapping[str, Any]) -> tuple[str, int]:
    return str(event.get('_timestamp', '')), int(event.get('_ordinal', 0))


def _latest_by(events: Iterable[Event], key: Callable[[Event], tuple[str, ...]]) -> list[Event]:
    latest: dict[tuple[str, ...], Event] = {}
    for event in events:
        identity = key(event)
        if identity not in latest or _event_order(event) >= _event_order(latest[identity]):
            latest[identity] = event
    return sorted(latest.values(), key=_event_order)


def speaker_bucket(value: int) -> str:
    if value == 0:
        return '0'
    if value <= 3:
        return '1-3'
    if value <= 6:
        return '4-6'
    if value <= 10:
        return '7-10'
    if value <= 15:
        return '11-15'
    return '16+'


def owner_health_bucket(value: Any) -> str:
    """Classify how many speakers diarization flagged as the account owner.

    ``absent`` means the event predates the owner_speaker_ids field, not that the
    conversation had no owner. The two are different claims and must not merge.
    """
    if value is None:
        return 'absent'
    if value == 0:
        return 'owner_silent'
    if value == 1:
        return 'single_owner'
    return 'multi_owner'


def _wilson_interval(numerator: int, denominator: int) -> dict[str, float] | None:
    if denominator <= 0:
        return None
    proportion = numerator / denominator
    z2 = Z_95**2
    scale = 1 + z2 / denominator
    center = (proportion + z2 / (2 * denominator)) / scale
    margin = Z_95 * math.sqrt(proportion * (1 - proportion) / denominator + z2 / (4 * denominator**2)) / scale
    return {'lower': max(0.0, center - margin), 'upper': min(1.0, center + margin)}


def _cluster_interval(user_rates: Sequence[float]) -> dict[str, float] | None:
    if len(user_rates) < 2:
        return None
    mean = statistics.fmean(user_rates)
    margin = Z_95 * statistics.stdev(user_rates) / math.sqrt(len(user_rates))
    return {'lower': max(0.0, mean - margin), 'upper': min(1.0, mean + margin)}


def _rate(
    numerator: int,
    denominator: int,
    user_numerators: Mapping[str, int],
    user_denominators: Mapping[str, int],
    *,
    unit: str,
) -> Rate:
    eligible_users = sorted(uid for uid, count in user_denominators.items() if count > 0)
    user_rates = [user_numerators.get(uid, 0) / user_denominators[uid] for uid in eligible_users]
    return {
        'unit': unit,
        'event_weighted': {
            'numerator': numerator,
            'denominator': denominator,
            'rate': numerator / denominator if denominator else None,
            'ci95': _wilson_interval(numerator, denominator),
            'ci_method': 'wilson',
        },
        'user_macro': {
            'rate': statistics.fmean(user_rates) if user_rates else None,
            'denominator_users': len(eligible_users),
            'ci95': _cluster_interval(user_rates),
            'ci_method': 'normal_approximation_clustered_by_user',
        },
    }


def _distribution(
    records: Sequence[Mapping[str, Any]], category: Callable[[Mapping[str, Any]], str], *, unit: str
) -> dict[str, Rate]:
    denominator = len(records)
    totals = Counter(category(record) for record in records)
    user_denominators = Counter(str(record['uid']) for record in records)
    user_category: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        user_category[str(record['uid'])][category(record)] += 1
    return {
        value: _rate(
            count,
            denominator,
            {uid: counts[value] for uid, counts in user_category.items()},
            user_denominators,
            unit=unit,
        )
        for value, count in sorted(totals.items())
    }


def _outcome_by_group(
    records: Sequence[Mapping[str, Any]],
    group: Callable[[Mapping[str, Any]], str],
    outcome: Callable[[Mapping[str, Any]], bool],
    *,
    unit: str,
) -> dict[str, Rate]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[group(record)].append(record)
    result: dict[str, Rate] = {}
    for value, rows in sorted(grouped.items()):
        numerator = sum(1 for row in rows if outcome(row))
        user_denominators = Counter(str(row['uid']) for row in rows)
        user_numerators = Counter(str(row['uid']) for row in rows if outcome(row))
        result[value] = _rate(
            numerator,
            len(rows),
            user_numerators,
            user_denominators,
            unit=unit,
        )
    return result


def _conversation_rows(capture_events: Sequence[Event]) -> tuple[list[Event], int]:
    grouped: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in capture_events:
        grouped[(event['uid'], event['conversation_id'])].append(event)
    rows: list[Event] = []
    inconsistent = 0
    for events in grouped.values():
        ordered = sorted(events, key=_event_order)
        latest = dict(ordered[-1])
        latest['attribution_disagreed'] = any(bool(event['attribution_disagreed']) for event in events)
        if (
            len(
                {
                    (event['capture_regime'], event['distinct_speaker_ids'], event.get('owner_speaker_ids'))
                    for event in events
                }
            )
            > 1
        ):
            inconsistent += 1
        rows.append(latest)
    return sorted(rows, key=_event_order), inconsistent


def build_report(
    events: Sequence[Event],
    *,
    source: Mapping[str, Any],
    input_entries: int,
    invalid_entries: Mapping[str, int],
    query_limit: int | None = None,
) -> dict[str, Any]:
    capture_raw = [event for event in events if event['stage'] == 'capture']
    promotion_raw = [event for event in events if event['stage'] == 'promotion']
    captures = _latest_by(capture_raw, lambda event: (event['uid'], event['memory_id']))
    conversations, inconsistent_conversations = _conversation_rows(captures)
    applied = _latest_by(
        [event for event in promotion_raw if event['status'] == 'applied'],
        lambda event: (event['uid'], event['memory_id']),
    )
    failures = [event for event in promotion_raw if event['status'] != 'applied']
    truncated = query_limit is not None and input_entries >= query_limit
    invalid_total = sum(invalid_entries.values())

    status = 'incomplete' if truncated or invalid_total else 'empty' if not events else 'complete'
    disagreement_by_speakers = _outcome_by_group(
        captures,
        lambda event: speaker_bucket(int(event['distinct_speaker_ids'])),
        lambda event: bool(event['attribution_disagreed']),
        unit='memories',
    )
    conversation_disagreement_by_speakers = _outcome_by_group(
        conversations,
        lambda event: speaker_bucket(int(event['distinct_speaker_ids'])),
        lambda event: bool(event['attribution_disagreed']),
        unit='conversations',
    )
    # Owner health is a property of the conversation, and only conversations whose
    # telemetry actually carries the field can contribute a denominator.
    owner_known = [event for event in conversations if event.get('owner_speaker_ids') is not None]
    owner_health_share = _distribution(
        conversations, lambda event: owner_health_bucket(event.get('owner_speaker_ids')), unit='conversations'
    )
    disagreement_by_owner_health = _outcome_by_group(
        captures,
        lambda event: owner_health_bucket(event.get('owner_speaker_ids')),
        lambda event: bool(event['attribution_disagreed']),
        unit='memories',
    )
    owner_silent_by_regime = _outcome_by_group(
        owner_known,
        lambda event: str(event['capture_regime']),
        lambda event: int(event['owner_speaker_ids']) == 0,
        unit='conversations with owner counts',
    )
    multi_owner_by_regime = _outcome_by_group(
        owner_known,
        lambda event: str(event['capture_regime']),
        lambda event: int(event['owner_speaker_ids']) > 1,
        unit='conversations with owner counts',
    )
    report = {
        'schema': REPORT_SCHEMA,
        'status': status,
        'source': dict(source),
        'limitations': [
            (
                'No owner-silent or multi-owner metric is derivable: no capture event carried owner_speaker_ids.'
                if not owner_known
                else (
                    f'Owner-health rates cover {len(owner_known)}/{len(conversations)} conversations; '
                    'the rest predate owner_speaker_ids and are reported as absent, not as a health state.'
                )
            ),
            'Clean/degraded diarization is still not a labelled outcome; speaker counts are not a health label.',
            'Capture disagreement is a per-memory comparison of model_about with resolved subject_attribution.',
            'Promotion failures are attempts, not rejection decisions; repeated retries can appear more than once.',
        ],
        'quality': {
            'input_entries': input_entries,
            'valid_telemetry_events': len(events),
            'invalid_entries': invalid_total,
            'invalid_entries_by_reason': dict(sorted(invalid_entries.items())),
            'query_limit': query_limit,
            'query_truncated': truncated,
            'duplicate_capture_events_removed': len(capture_raw) - len(captures),
            'duplicate_applied_promotion_events_removed': sum(
                1 for event in promotion_raw if event['status'] == 'applied'
            )
            - len(applied),
            'inconsistent_capture_conversations': inconsistent_conversations,
        },
        'totals': {
            'capture_memories': len(captures),
            'capture_conversations': len(conversations),
            'capture_conversations_with_owner_counts': len(owner_known),
            'capture_users': len({event['uid'] for event in captures}),
            'promotion_applied_decisions': len(applied),
            'promotion_failure_attempts': len(failures),
            'promotion_users': len({event['uid'] for event in promotion_raw}),
        },
        'capture': {
            'regime_memory_share': _distribution(captures, lambda event: str(event['capture_regime']), unit='memories'),
            'regime_conversation_share': _distribution(
                conversations, lambda event: str(event['capture_regime']), unit='conversations'
            ),
            'attribution_disagreed': _distribution(
                captures, lambda event: str(bool(event['attribution_disagreed'])).lower(), unit='memories'
            ),
            'subject_attribution': _distribution(
                captures, lambda event: str(event['subject_attribution']), unit='memories'
            ),
            'disagreement_by_regime': _outcome_by_group(
                captures,
                lambda event: str(event['capture_regime']),
                lambda event: bool(event['attribution_disagreed']),
                unit='memories',
            ),
            'disagreement_by_distinct_speaker_ids': {
                bucket: disagreement_by_speakers[bucket]
                for bucket in SPEAKER_BUCKETS
                if bucket in disagreement_by_speakers
            },
            'conversation_any_disagreement_by_distinct_speaker_ids': {
                bucket: conversation_disagreement_by_speakers[bucket]
                for bucket in SPEAKER_BUCKETS
                if bucket in conversation_disagreement_by_speakers
            },
            'owner_health_conversation_share': {
                bucket: owner_health_share[bucket] for bucket in OWNER_HEALTH_BUCKETS if bucket in owner_health_share
            },
            'disagreement_by_owner_health': {
                bucket: disagreement_by_owner_health[bucket]
                for bucket in OWNER_HEALTH_BUCKETS
                if bucket in disagreement_by_owner_health
            },
            'owner_silent_by_regime': owner_silent_by_regime,
            'multi_owner_by_regime': multi_owner_by_regime,
        },
        'promotion': {
            'applied_routes': _distribution(applied, lambda event: str(event['route']), unit='applied decisions'),
            'applied_reason_codes': _distribution(
                applied, lambda event: str(event['reason_code']), unit='applied decisions'
            ),
            'rejection_reason_codes': _distribution(
                [event for event in applied if event['route'] == 'reject'],
                lambda event: str(event['reason_code']),
                unit='applied rejection decisions',
            ),
            'failure_statuses': _distribution(failures, lambda event: str(event['status']), unit='failure attempts'),
            'failure_reason_codes': _distribution(
                failures, lambda event: str(event['reason_code']), unit='failure attempts'
            ),
        },
    }
    return report


def _percent(value: float | None) -> str:
    return 'n/a' if value is None else f'{value * 100:.1f}%'


def _format_rate(metric: Mapping[str, Any]) -> str:
    event = metric['event_weighted']
    event_ci = event['ci95']
    event_ci_text = f"95% CI {_percent(event_ci['lower'])}..{_percent(event_ci['upper'])}" if event_ci else '95% CI n/a'
    user = metric['user_macro']
    user_ci = user['ci95']
    user_ci_text = (
        f"95% CI {_percent(user_ci['lower'])}..{_percent(user_ci['upper'])}" if user_ci else '95% CI n/a (<2 users)'
    )
    return (
        f"{_percent(event['rate'])} ({event['numerator']}/{event['denominator']} {metric['unit']}; {event_ci_text}); "
        f"user mean {_percent(user['rate'])} across {user['denominator_users']} users ({user_ci_text})"
    )


def _render_section(lines: list[str], title: str, values: Mapping[str, Any]) -> None:
    lines.append('')
    lines.append(title)
    if not values:
        lines.append('  no eligible observations (denominator 0)')
        return
    for key, metric in values.items():
        lines.append(f'  {key}: {_format_rate(metric)}')


def render_human(report: Mapping[str, Any]) -> str:
    quality = report['quality']
    totals = report['totals']
    lines = [
        'Canonical memory decision-path measurement',
        f"status: {report['status']}",
        f"source: {json.dumps(report['source'], sort_keys=True)}",
        (
            f"input: {quality['valid_telemetry_events']}/{quality['input_entries']} valid telemetry entries; "
            f"{quality['invalid_entries']}/{quality['input_entries']} invalid"
        ),
    ]
    if quality['query_truncated']:
        lines.append(
            f"INCOMPLETE: query returned {quality['input_entries']}/{quality['query_limit']} allowed entries; shorten the window."
        )
    if quality['invalid_entries_by_reason']:
        lines.append(f"invalid reasons: {json.dumps(quality['invalid_entries_by_reason'], sort_keys=True)}")
    if quality['valid_telemetry_events'] == 0:
        lines.append('No telemetry events found; no rates were computed (every denominator is 0).')
    lines.append(
        f"capture: {totals['capture_memories']} memories / {totals['capture_conversations']} conversations / "
        f"{totals['capture_users']} users"
    )
    lines.append(
        f"promotion: {totals['promotion_applied_decisions']} applied decisions / "
        f"{totals['promotion_failure_attempts']} failure attempts / {totals['promotion_users']} users"
    )
    lines.append('Rates show event-weighted numerator/denominator and the mean per-user rate.')

    capture = report['capture']
    _render_section(lines, 'Capture regime share (conversation grain)', capture['regime_conversation_share'])
    _render_section(lines, 'Capture regime share (memory grain)', capture['regime_memory_share'])
    _render_section(lines, 'Attribution disagreement', capture['attribution_disagreed'])
    _render_section(lines, 'Subject attribution', capture['subject_attribution'])
    _render_section(lines, 'Disagreement rate by capture regime', capture['disagreement_by_regime'])
    _render_section(
        lines,
        'Disagreement rate by distinct speaker-ID bucket (memory grain)',
        capture['disagreement_by_distinct_speaker_ids'],
    )
    _render_section(
        lines,
        'Any disagreement by distinct speaker-ID bucket (conversation grain)',
        capture['conversation_any_disagreement_by_distinct_speaker_ids'],
    )
    _render_section(lines, 'Owner-speaker health (conversation grain)', capture['owner_health_conversation_share'])
    _render_section(
        lines, 'Disagreement rate by owner-speaker health (memory grain)', capture['disagreement_by_owner_health']
    )
    _render_section(lines, 'Owner-silent rate by capture regime', capture['owner_silent_by_regime'])
    _render_section(lines, 'Multi-owner rate by capture regime', capture['multi_owner_by_regime'])

    promotion = report['promotion']
    _render_section(lines, 'Applied promotion routes', promotion['applied_routes'])
    _render_section(lines, 'Applied promotion reason codes', promotion['applied_reason_codes'])
    _render_section(lines, 'Applied rejection reason codes', promotion['rejection_reason_codes'])
    _render_section(lines, 'Operational failure statuses (attempt grain)', promotion['failure_statuses'])
    _render_section(lines, 'Operational failure reason codes (attempt grain)', promotion['failure_reason_codes'])
    lines.append('')
    owner_covered = totals['capture_conversations_with_owner_counts']
    if owner_covered:
        lines.append(
            f'Owner-health rates cover {owner_covered}/{totals["capture_conversations"]} conversations; '
            'clean/degraded diarization is still not a labelled outcome and speaker counts are not a proxy label.'
        )
    else:
        lines.append(
            'Not measured here: owner-silent, multi-owner, or clean/degraded diarization; no event carried '
            'owner_speaker_ids and distinct speaker count is not a proxy label.'
        )
    return '\n'.join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', help='JSON/JSONL file from gcloud; use - for stdin. Omit to query Cloud Logging.')
    parser.add_argument('--project', default=os.environ.get('GOOGLE_CLOUD_PROJECT', DEFAULT_PROJECT))
    parser.add_argument(
        '--days', type=int, default=DEFAULT_DAYS, help=f'UTC days ending at --end (default {DEFAULT_DAYS})'
    )
    parser.add_argument('--start', help='inclusive ISO-8601 timestamp; overrides --days')
    parser.add_argument('--end', help='exclusive ISO-8601 timestamp (default now, UTC)')
    parser.add_argument(
        '--limit', type=int, default=DEFAULT_LIMIT, help=f'fail-closed query cap (default {DEFAULT_LIMIT})'
    )
    parser.add_argument('--format', choices=('human', 'json'), default='human')
    parser.add_argument('--json-output', help='also write canonical JSON to this path')
    return parser.parse_args(argv)


def _window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    end = _parse_utc(args.end) if args.end else datetime.now(timezone.utc)
    if args.start:
        start = _parse_utc(args.start)
    else:
        if args.days < 1:
            raise ValueError('--days must be at least 1')
        start = end - timedelta(days=args.days)
    if start >= end:
        raise ValueError('--start must be earlier than --end')
    return start, end


def main(
    argv: Sequence[str] | None = None,
    *,
    fetcher: Callable[..., list[Any]] = fetch_cloud_logging_entries,
) -> int:
    args = parse_args(argv)
    if args.limit < 1:
        print('error: --limit must be at least 1', file=sys.stderr)
        return 2
    syntax_errors = 0
    query_limit: int | None = None
    try:
        if args.input:
            entries, syntax_errors = load_entries(args.input)
            source: dict[str, Any] = {'kind': 'file', 'path': args.input}
        else:
            start, end = _window(args)
            entries = fetcher(project=args.project, start=start, end=end, limit=args.limit)
            query_limit = args.limit
            source = {
                'kind': 'cloud_logging',
                'project': args.project,
                'start': _utc_text(start),
                'end': _utc_text(end),
            }
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    events, invalid = parse_events(entries, syntax_errors=syntax_errors)
    report = build_report(
        events,
        source=source,
        input_entries=len(entries) + syntax_errors,
        invalid_entries=invalid,
        query_limit=query_limit,
    )
    canonical_json = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.json_output:
        try:
            Path(args.json_output).write_text(canonical_json, encoding='utf-8')
        except OSError as exc:
            print(f'error: could not write --json-output: {exc}', file=sys.stderr)
            return 2
    print(canonical_json, end='') if args.format == 'json' else print(render_human(report))
    return 3 if report['status'] == 'incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
