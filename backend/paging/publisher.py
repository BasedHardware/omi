"""Authentication and normalization for the one approved publisher."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re


@dataclass(frozen=True)
class Route:
    publisher: str
    uid: str
    target: str
    route_id: str
    recipient: str
    channel: str


REDIS = Route(
    'grafana-redis', 'omi-redis-cache-conn-page', 'prod-serving-redis', 'redis-wake', 'oncall-primary', 'bark'
)
ROUTES = {(REDIS.publisher, REDIS.uid, REDIS.target): REDIS}
MAX_EVENT_AGE = timedelta(minutes=15)


def digest(*parts):
    return hashlib.sha256('\0'.join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class Event:
    route: Route
    starts_at: datetime
    status: str
    fingerprint: str
    ends_at: datetime | None = None

    @property
    def episode_id(self):
        return digest(self.route.publisher, self.route.uid, self.route.target, self.starts_at.isoformat())

    @property
    def delivery_id(self):
        return digest(self.episode_id, self.route.recipient, self.route.channel)

    @property
    def event_id(self):
        return digest(self.episode_id, self.status)


def verify_signature(secret, timestamp, signature, body, now):
    if not re.fullmatch(r'[0-9]{10}', timestamp) or not re.fullmatch(r'[0-9a-f]{64}', signature):
        return False
    if abs(now.timestamp() - int(timestamp)) > 300:
        return False
    expected = hmac.digest(secret, timestamp.encode() + b':' + body, 'sha256').hex()
    return hmac.compare_digest(expected, signature)


def parse_time(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('invalid time')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('time zone required')
    return parsed.astimezone(timezone.utc)


def parse_events(payload, now):
    alerts = payload['alerts']
    if not isinstance(alerts, list) or not 1 <= len(alerts) <= 4 or payload.get('truncatedAlerts', 0) != 0:
        raise ValueError('invalid alert group')
    events = []
    for alert in alerts:
        labels = alert['labels']
        route = ROUTES[('grafana-redis', labels['alert_identity'], labels['paging_target'])]
        status = alert['status']
        starts_at = parse_time(alert['startsAt'])
        fingerprint = alert['fingerprint']
        if status not in ('firing', 'resolved') or not re.fullmatch(r'[0-9a-f]{16}', fingerprint):
            raise ValueError('invalid alert identity')
        ends_at = parse_time(alert['endsAt']) if status == 'resolved' else None
        if starts_at > now + timedelta(seconds=30) or (
            ends_at is not None and (ends_at < starts_at or ends_at > now + timedelta(seconds=30))
        ):
            raise ValueError('invalid episode times')
        events.append(Event(route, starts_at, status, fingerprint, ends_at))
    # A grouped clear takes precedence over a firing for the same episode.
    return sorted(events, key=lambda event: event.status != 'resolved')
