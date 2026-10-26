"""Messaging rollout is off unless both the switch and exact uid cohort admit it."""

import json
import os

from config.rollout_cohorts import in_rollout_cohort
from config.refactor_switches import default_off as rollout_default_off
from urllib.parse import quote


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
        return any(cohort_enabled(uid, name) for name in ('telegram', 'imessage'))
    policy = channel_policy(channel)
    cohort = policy['cohort']
    return policy['enabled'] and (
        cohort == '*'
        or isinstance(cohort, list)
        and in_rollout_cohort(uid, 'messaging-' + channel, legacy_members=tuple(cohort))
    )


def channel_enabled(channel):
    return channel_policy(channel)['enabled']


def public_link_fields(channel, proof):
    """Deep link and public address from server config, keyed by the requested channel.

    ``OMI_MESSAGING_LINK_TARGETS`` is a JSON object. A channel entry may set ``address``
    and ``deep_link_template`` containing ``{proof}``. Missing or malformed config yields
    empty fields so the app can fall back to its flag payload. The proof is URL-encoded
    and never logged here.
    """
    raw = os.getenv('OMI_MESSAGING_LINK_TARGETS', '')
    try:
        targets = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None, None
    row = targets.get(channel) if isinstance(targets, dict) else None
    if not isinstance(row, dict):
        return None, None
    address = row.get('address')
    address = address.strip() if isinstance(address, str) and address.strip() else None
    template = row.get('deep_link_template')
    deep_link = None
    if isinstance(template, str) and '{proof}' in template and ' ' not in template and len(template) <= 300:
        deep_link = template.replace('{proof}', quote(proof, safe=''))
        if address and '{address}' in deep_link:
            deep_link = deep_link.replace('{address}', quote(address, safe=''))
    return deep_link, address
