"""Fail-closed mixed-version barrier; neither env windows nor a leader imply fleet readiness.

    coalesce_capabilities/<source SHA>: this binary's immutable reader advertisement
    coalesce_capabilities/roster: rollout owner's short-lived complete fleet inventory

The roster is operational attestation, not inferred from advertisements: an old
binary cannot advertise. The owner must inventory every serving drainer AND
completion writer, including worker images, before publishing the roster. No
producer may publish/renew it. Unknown, expired or incomplete evidence uses 60s.
"""

import math
import os
import re

from config.batch_pipeline_coalescing import EXTENDED_MAX_MEMBERS

SHA = re.compile('[0-9a-f]{40}')
_ADVERTISED = set()


def advertise(store):
    release = os.getenv('OMI_BACKEND_RELEASE_SHA', '')
    if not SHA.fullmatch(release):
        return
    key = (store.namespace, release)
    if key in _ADVERTISED:
        return

    def commit(tx):
        key = ('coalesce_capabilities', release)
        current = tx.get(*key)
        if current.get('protocol') == 2 and current.get('max_members') == EXTENDED_MAX_MEMBERS:
            return
        tx.put(*key, {'protocol': 2, 'max_members': EXTENDED_MAX_MEMBERS})

    store.run(commit)
    if len(_ADVERTISED) < 64:
        _ADVERTISED.add(key)


def extended_ready(tx, now):
    roster = tx.get('coalesce_capabilities', 'roster')
    start, end = roster.get('verified_at'), roster.get('valid_until')
    releases = roster.get('reader_releases')
    if not (
        roster.get('inventory_complete') is True
        and type(start) in (int, float)
        and type(end) in (int, float)
        and math.isfinite(start)
        and math.isfinite(end)
        and start <= now < end <= start + 900
        and isinstance(releases, list)
        and 0 < len(releases) <= 64
        and all(isinstance(s, str) and SHA.fullmatch(s) for s in releases)
    ):
        return False
    for release in releases:
        ad = tx.get('coalesce_capabilities', release)
        if ad.get('protocol') != 2 or ad.get('max_members') != EXTENDED_MAX_MEMBERS:
            return False
    return True
