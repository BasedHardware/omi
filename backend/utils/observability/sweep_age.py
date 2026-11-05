"""Count ancient sweep candidates without changing their durable rows."""

from datetime import datetime, timezone
import math

from prometheus_client import Counter

from config.policy import sweep_age

SKIPPED = Counter(
    'omi_batch_pipeline_sweep_skipped_total',
    'Durable rows left unchanged instead of re-enqueued by maintenance sweeps',
    ['queue', 'reason'],
)


def skip_ancient(row, queue: str, *, now: float) -> bool:
    if not sweep_age.enabled():
        return False
    fields = ('created_at',) if queue == 'provider-stt' else ('first_pending_at', 'latest_pending_at')
    timestamps = []
    for field in fields:
        if field == 'latest_pending_at' and field not in row:
            continue  # Existing rows retain their original acceptance clock until a new mark.
        value = row.get(field)
        try:
            if isinstance(value, str):
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if isinstance(value, datetime):
                value = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
            # Unknown metadata cannot prove that an obligation is ancient.
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                return False
            timestamps.append(value)
        except (ValueError, OverflowError):
            return False
    expired = now - max(timestamps) > sweep_age.max_age_seconds(queue)
    if expired:
        SKIPPED.labels(queue=queue, reason='max_age').inc()
    return expired
