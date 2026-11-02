"""Bounded, session-owned month totals; only open UTC buckets refresh each minute."""

from copy import deepcopy
from datetime import timezone
import hashlib
import time

from config.rate_card_versions import RATE_CARD_SHA256
from database.usage_units import read_usage_month, summarize_usage


def _add(left, right):
    result = deepcopy(left)
    for key, value in right.items():
        result[key] = _add(result.get(key, {}), value) if isinstance(value, dict) else result.get(key, 0) + value
    return result


class UsageUnitsSession:
    """One closed-bucket sum plus one open hour/day, never a cache per user/process.

    Full scans reconcile late/backdated writes every 900 seconds. Rollover
    closes the previous buckets with one final read before freezing their sums.
    Failed reads leave the last successful cache intact for a bounded retry.
    """

    def __init__(self):
        self.invalidate()

    def invalidate(self):
        self.full_at = None
        self.key = None
        self.entitlements = None
        self.hour = None
        self.day = None
        self.closed = {}

    def read(self, uid, period, client, entitlements):
        now = period.astimezone(timezone.utc)
        key = (uid, now.strftime('%Y-%m'))
        hour, day = now.strftime('%Y-%m-%d-%H'), now.date().isoformat()
        if (
            self.full_at is None
            or self.key != key
            or self.entitlements != entitlements
            or time.monotonic() - self.full_at >= 900
        ):
            hourly, days = read_usage_month(uid, now, client, entitlements)
            closed = summarize_usage(
                [data for name, data in hourly if name != hour],
                [(data, api) for name, data, api in days if name != day],
                entitlements,
                True,
            )
            open_hour = next((data for name, data in hourly if name == hour), {})
            open_day = next(((data, api) for name, data, api in days if name == day), ({}, {}))
            full_at = time.monotonic()
        else:
            user = client.collection('users').document(uid)
            hashed = hashlib.sha256(uid.encode()).hexdigest()[:16]
            hours = [hour] if self.hour == hour else [self.hour, hour]
            dates = [day] if self.day == day else [self.day, day]
            refs = [user.collection('hourly_usage').document(name) for name in hours]
            refs += [client.collection('llm_gateway_user_days').document(f'{date}_{hashed}') for date in dates]
            # Historical API day docs only. New requests do not write usage units.
            refs += [user.collection('ladder_v1_api_days').document(date) for date in dates]
            documents = {
                snap.id: snap.to_dict() or {}
                for snap in client.get_all(
                    refs,
                    field_paths=[
                        *[f'shadow_{version}' for version in RATE_CARD_SHA256],
                        'transcription_seconds',
                        'speech_seconds',
                        'attempts',
                        'micro_units',
                        'requests',
                    ],
                )
            }
            closed = self.closed
            if self.hour != hour or self.day != day:
                closed = _add(
                    closed,
                    summarize_usage(
                        [documents.get(self.hour, {})] if self.hour != hour else [],
                        (
                            [(documents.get(f'{self.day}_{hashed}', {}), documents.get(self.day, {}))]
                            if self.day != day
                            else []
                        ),
                        entitlements,
                        True,
                    ),
                )
            open_hour = documents.get(hour, {})
            open_day = (documents.get(f'{day}_{hashed}', {}), documents.get(day, {}))
            full_at = self.full_at
        current = summarize_usage([open_hour], [open_day], entitlements, True)
        summary = _add(closed, current)
        self.key, self.entitlements, self.full_at = key, deepcopy(entitlements), full_at
        self.hour, self.day, self.closed = hour, day, closed
        # Keep no monthly document list; even the open buckets are reduced above.
        return summary
