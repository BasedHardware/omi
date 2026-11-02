"""Deterministic daily-summary metrics and explicit legacy coverage."""

from datetime import datetime, timezone

from utils.mcp_data import action_item_source


def union_interval_minutes(intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> int:
    """Elapsed minutes in the clipped union, including overlap across devices."""
    clipped = sorted((max(a, start), min(b, end)) for a, b in intervals if b > start and a < end and b > a)
    seconds = 0.0
    tail = None
    for a, b in clipped:
        if tail is None or a > tail:
            seconds += (b - a).total_seconds()
        elif b > tail:
            seconds += (b - tail).total_seconds()
        tail = max(tail, b) if tail is not None else b
    return min(1440, max(0, int(round(seconds / 60))))


def screen_observation_minutes(rows: list[dict], start: datetime, end: datetime) -> int:
    """Union bounded gaps between captures per device, not inferred screen usage."""
    previous = {}
    intervals = []
    for row in rows:
        try:
            stamp = datetime.fromisoformat(str(row.get('timestamp')).replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        device = row.get('clientDeviceId') or row.get('deviceName') or 'unknown'
        last = previous.get(device)
        if last is not None and 0 <= (stamp - last).total_seconds() <= 300:
            intervals.append((last, stamp))
        previous[device] = stamp
    return union_interval_minutes(intervals, start, end)


def summary_read_payload(row: dict) -> dict:
    """Keep stored totals while declaring review/subset coverage on legacy rows."""
    result = dict(row)
    stats = dict(row.get('stats') or {})
    learned = list(row.get('memories_learned') or [])
    actions = list(row.get('action_items') or [])
    result['status'] = row.get('status') or 'generated'
    # V4 persists stubs as real rows. Their creation time is not a successful
    # generation time; only legacy successful rows lack this field entirely.
    result['generated_at'] = row.get('generated_at', row.get('created_at')) if result['status'] == 'generated' else None
    result['memories_learned_count'] = len(learned)
    result['memories_learned_coverage'] = row.get('memories_learned_coverage') or (
        'legacy_review_selection; coverage_unknown; not all stored memories'
        if 'memories_learned' in row
        else 'not_recorded_by_legacy_producer; creations_not_reconstructed'
    )
    stats['memories_learned_count'] = len(learned)
    stats['memory_count_basis'] = 'storage_created_in_window; may include memories ineligible for review'
    if row.get('read_contract_version') != 2:
        if 'action_items_created' in stats:
            stats['stored_action_items_created'] = stats.get('action_items_created')
        result['action_items_coverage'] = 'legacy_conversation_subset; created-in-window items may be omitted'
    else:
        result['action_items_coverage'] = row.get('action_items_coverage') or 'created_in_window'
    stats['action_items_created'] = len(actions)
    stats['action_items_count'] = len(actions)
    result['action_items'] = [
        {
            **item,
            'source': action_item_source(
                {**item, 'conversation_id': item.get('conversation_id') or item.get('source_conversation_id')}
            ),
        }
        for item in actions
    ]
    if row.get('read_contract_version') != 2:
        stats['reported_device_watching_minutes'] = stats.get('watching_minutes')
        stats['watching_minutes'] = min(1440, max(0, stats.get('watching_minutes') or 0))
        stats['watching_minutes_basis'] = 'legacy_device_counter_sum_clamped; interval union unavailable'
        stats['watching_coverage'] = 'unknown'
    stats['watching_minutes_unit'] = 'minutes'
    result['stats'] = stats
    return result
