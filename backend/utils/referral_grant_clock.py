"""Promotional obligation accounting independent of billing delivery order.

Availability records time access was actually scheduled; gaps after an expired
schedule never consume the reward. Paid coverage is a union of intervals, not
an end watermark: a late earlier period can restore previously hidden time.
"""

from datetime import datetime
from typing import Any, Mapping

MAX_CLOCK_INTERVALS = 256


class GrantClockCapacityError(ValueError):
    pass


def merge_intervals(intervals: list[dict[str, int]]) -> list[dict[str, int]]:
    merged: list[dict[str, int]] = []
    for interval in sorted(intervals, key=lambda item: item['start']):
        start, end = interval['start'], interval['end']
        if type(start) is not int or type(end) is not int or end <= start:
            raise ValueError('invalid grant clock interval')
        if merged and start <= merged[-1]['end']:
            merged[-1]['end'] = max(merged[-1]['end'], end)
        else:
            merged.append({'start': start, 'end': end})
    if len(merged) > MAX_CLOCK_INTERVALS:
        raise GrantClockCapacityError('grant clock interval capacity requires reconciliation')
    return merged


def _accounting(grant: Mapping[str, Any]) -> dict[str, Any]:
    if grant.get('paid_coverage_end') is not None:
        # The dormant watermark prototype cannot reconstruct which earlier
        # intervals it skipped. Never invent credited time from that scalar.
        raise ValueError('prototype grant requires billing reconciliation')
    return {
        'clock_version': 2,
        'budget_seconds': grant.get('budget_seconds', grant['ends_at'] - grant['starts_at']),
        'availability': merge_intervals(
            grant.get('availability', [{'start': grant['starts_at'], 'end': grant['ends_at']}])
        ),
        'paid_coverage': merge_intervals(grant.get('paid_coverage', [])),
    }


def extend_grant_clock(prior: Mapping[str, Any], grant: dict[str, Any], *, extension_start: int) -> dict[str, Any]:
    previous: dict[str, Any] = (
        _accounting(prior) if prior else {'budget_seconds': 0, 'availability': [], 'paid_coverage': []}
    )
    return {
        **grant,
        'budget_seconds': previous['budget_seconds'] + grant['ends_at'] - extension_start,
        'availability': merge_intervals(
            [*previous['availability'], {'start': extension_start, 'end': grant['ends_at']}]
        ),
        'paid_coverage': previous['paid_coverage'],
        'clock_version': 2,
    }


def _consumed_seconds(availability, coverage, epoch):
    consumed, paid_index = 0, 0
    for window in availability:
        start, end = window['start'], min(window['end'], epoch)
        if end <= start:
            continue
        seconds = end - start
        while paid_index < len(coverage) and coverage[paid_index]['end'] <= start:
            paid_index += 1
        index = paid_index
        while index < len(coverage) and coverage[index]['start'] < end:
            paid = coverage[index]
            seconds -= max(0, min(end, paid['end']) - max(start, paid['start']))
            if paid['end'] >= end:
                break
            index += 1
        paid_index = index
        consumed += seconds
    return consumed


def _schedule(epoch, remaining, coverage):
    start, cursor = epoch, epoch
    for paid in coverage:
        if paid['end'] <= cursor:
            continue
        if paid['start'] > cursor:
            gap = paid['start'] - cursor
            if remaining <= gap:
                return start, cursor + remaining
            remaining -= gap
            cursor = paid['start']
        if cursor == start:
            start = paid['end']
        cursor = max(cursor, paid['end'])
    return start, cursor + remaining


def requeue_for_paid_period(
    grant: Mapping[str, Any], subscription: Mapping[str, Any], *, now: datetime
) -> dict[str, Any]:
    clock = _accounting(grant)
    end = subscription.get('current_period_end')
    if type(end) is not int or end <= 0:
        raise ValueError('paid period requires an authoritative end')
    start = subscription.get('current_period_start')
    start = start if type(start) is int else clock['availability'][0]['start']
    coverage = merge_intervals([*clock['paid_coverage'], {'start': start, 'end': end}])
    if coverage == clock['paid_coverage']:
        return dict(grant)
    epoch = max(int(now.timestamp()), clock['availability'][0]['start'])
    remaining = max(0, clock['budget_seconds'] - _consumed_seconds(clock['availability'], coverage, epoch))
    result = {**grant, **clock, 'paid_coverage': coverage}
    if remaining:
        access_start, access_end = _schedule(epoch, remaining, coverage)
        result.update(starts_at=access_start, ends_at=access_end)
        result['availability'] = merge_intervals([*clock['availability'], {'start': access_start, 'end': access_end}])
    return result
