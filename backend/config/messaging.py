"""Messaging rollout is off unless both the switch and exact uid cohort admit it."""

import json
import os
from dataclasses import dataclass
from datetime import date

from config.rollout_cohorts import in_rollout_cohort
from config.refactor_switches import default_off as rollout_default_off
from urllib.parse import quote

# Every channel a messaging adapter can serve. Each stays off until its policy enables it.
MESSAGING_CHANNELS = ('telegram', 'imessage', 'whatsapp')


def channel_policy(channel):
    """New config is authoritative; malformed policies fail closed. Legacy is unchanged."""
    raw = os.getenv('OMI_MESSAGING_CHANNEL_POLICY')
    if raw is None:
        return {
            'enabled': rollout_default_off(
                'OMI_MESSAGING_CHANNELS', os.getenv('OMI_MESSAGING_CHANNELS', 'off').lower() == 'on'
            ),
            'cohort': [v.strip() for v in os.getenv('OMI_MESSAGING_CHANNELS_UIDS', '').split(',') if v.strip()],
        }
    try:
        policies = json.loads(raw)
        row = policies.get(channel, {})
        cohort = row.get('cohort', [])
        plans = row.get(
            'plans',
            None if row.get('seat_cap') == 'off' else ['operator', 'architect'] if channel == 'imessage' else None,
        )
        cap = row.get('seat_cap', 180 if channel == 'imessage' else None)
        if cap == 'off':
            cap = None
        if channel == 'imessage' and (row.get('seat_cap') != 'off' and (plans is None or cap is None)):
            raise ValueError('iMessage requires a plan set and seat cap')
        if not isinstance(row.get('enabled'), bool) or not (
            cohort == '*' or isinstance(cohort, list) and all(isinstance(v, str) for v in cohort)
        ):
            raise ValueError('Invalid policy')
        if channel == 'imessage' and 'plans' in row and plans is None:
            raise ValueError('Invalid plans')
        if plans is not None and (not isinstance(plans, list) or not all(isinstance(v, str) for v in plans)):
            raise ValueError('Invalid plans')
        if cap is not None and (type(cap) is not int or cap < 0):
            raise ValueError('Invalid cap')
        return dict(row, cohort=cohort, plans=plans, seat_cap=cap)
    except (ValueError, TypeError, AttributeError):
        return {'enabled': False, 'cohort': []}


def cohort_enabled(uid, channel=None):
    if channel is None:
        return any(cohort_enabled(uid, name) for name in MESSAGING_CHANNELS)
    policy = channel_policy(channel)
    cohort = policy['cohort']
    return policy['enabled'] and (
        cohort == '*'
        or isinstance(cohort, list)
        and in_rollout_cohort(uid, 'messaging-' + channel, legacy_members=tuple(cohort))
    )


def channel_enabled(channel):
    return channel_policy(channel)['enabled']


@dataclass(frozen=True)
class ChannelLine:
    """One phone line that takes new links. Defaults are 80% of Keiki's per-line guidance."""

    address: str
    max_users: int = 400
    new_per_day: int = 40
    started: date | None = None

    def new_limit(self, today):
        """A line grows gradually: 10 new people a day in its first week, 10 more each week after."""
        if self.started is None:
            return self.new_per_day
        return min(self.new_per_day, 10 * ((today - self.started).days // 7 + 1))


def _parse_line(row):
    address = row['address']
    if not isinstance(address, str) or not address.strip() or '/' in address:
        raise ValueError('Invalid line address')
    max_users, new_per_day = row.get('max_users', 400), row.get('new_per_day', 40)
    if type(max_users) is not int or type(new_per_day) is not int or max_users < 0 or new_per_day < 0:
        raise ValueError('Invalid line limits')
    started = date.fromisoformat(row['started']) if 'started' in row else None
    return ChannelLine(address.strip(), max_users, new_per_day, started)


def channel_lines(channel):
    """The lines taking new links, or None when the channel does not use lines.

    A line with `"enabled": false` takes no new links and keeps the people already on it. An
    empty result means no line has room. A malformed `lines` value closes linking rather than
    lifting the limits, the same way a malformed channel policy fails closed.
    """
    try:
        row = json.loads(os.getenv('OMI_MESSAGING_LINK_TARGETS', ''))[channel]
    except (ValueError, TypeError, KeyError):
        return None
    if not isinstance(row, dict) or 'lines' not in row:
        return None
    try:
        rows = row['lines']
        if not isinstance(rows, list) or any(not isinstance(item.get('enabled', True), bool) for item in rows):
            raise ValueError('Invalid lines')
        lines = tuple(_parse_line(item) for item in rows if item.get('enabled', True))
    except (ValueError, TypeError, KeyError, AttributeError):
        return ()
    return lines if len({line.address for line in lines}) == len(lines) else ()


def public_link_fields(channel, proof, *, address=None):
    """Deep link and public address from server config, keyed by the requested channel.

    ``OMI_MESSAGING_LINK_TARGETS`` is a JSON object. A channel entry may set ``address``
    and ``deep_link_template`` containing ``{proof}``. Missing or malformed config yields
    empty fields so the app can fall back to its flag payload. The proof is URL-encoded
    and never logged here. ``address`` is the line assigned to this link, when there is one.
    """
    raw = os.getenv('OMI_MESSAGING_LINK_TARGETS', '')
    try:
        targets = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None, None
    row = targets.get(channel) if isinstance(targets, dict) else None
    if not isinstance(row, dict):
        return None, None
    address = address or row.get('address')
    address = address.strip() if isinstance(address, str) and address.strip() else None
    template = row.get('deep_link_template')
    deep_link = None
    if isinstance(template, str) and '{proof}' in template and ' ' not in template and len(template) <= 300:
        deep_link = template.replace('{proof}', quote(proof, safe=''))
        if address and '{address}' in deep_link:
            deep_link = deep_link.replace('{address}', quote(address, safe=''))
    return deep_link, address
