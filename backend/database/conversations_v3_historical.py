"""Historical source settlement and conservative outer-edge custody."""

from collections import defaultdict, deque
from datetime import datetime, timedelta
from math import isfinite

from config.conversations_v3 import HISTORICAL_SITDOWN_TIMING, SPEECH_LANDED_FIELD
from utils.conversations.v3 import Conflict


def _timestamp(value):
    return value if isinstance(value, datetime) and value.utcoffset() is not None else None


def historical_exclusions(sources, recordings, row_sources, *, since, until, now, internal_start, internal_end):
    """Return excluded source/row IDs and reasons, keeping connected claim owners together."""
    silence, lock = (timedelta(seconds=seconds) for seconds in HISTORICAL_SITDOWN_TIMING)
    related = defaultdict(set)
    missing = set()
    bounds, seeds = [], {}
    for cid, ids in row_sources.items():
        for rid in ids:
            if rid not in sources:
                missing.add(cid)
            else:
                related[cid].add(rid)
                related[rid].add(cid)
    for rid, raw in sources.items():
        origin, end = _timestamp(raw.get('started_at')), _timestamp(raw.get('finished_at'))
        if origin is None or end is None or end < origin:
            raise Conflict('rederive_live_boundary')
        start = origin
        for claim in raw.get('claims') or ():
            cid = claim.get('conversation_id') if isinstance(claim, dict) else None
            if not isinstance(cid, str) or cid not in row_sources:
                missing.add(rid)
            else:
                related[cid].add(rid)
                related[rid].add(cid)
        row = recordings.get(rid)
        if row is not None:
            for segment in row.get('transcript_segments') or ():
                if not isinstance(segment, dict):
                    raise Conflict('rederive_live_boundary')
                if not str(segment.get('text') or '').strip():
                    continue
                try:
                    left = float(segment.get('start') or 0)
                    right = float(segment.get('end') or 0)
                    if not (isfinite(left) and isfinite(right)):
                        raise ValueError
                    start = min(start, origin + timedelta(seconds=left))
                    end = max(end, origin + timedelta(seconds=max(left, right)))
                except (ValueError, TypeError, OverflowError):
                    raise Conflict('rederive_live_boundary') from None
            if SPEECH_LANDED_FIELD not in raw:
                # Firestore update_time is for the exact completed snapshot, including any later append.
                # A capture clock or a stored timestamp cannot prove that revision was already complete.
                revised = _timestamp(row.get('_v3_revision'))
                if revised is None or revised < end:
                    seeds[rid] = 'landing_unknown'
                elif now - revised < lock:
                    seeds[rid] = 'landing_unsettled'
                else:
                    row[SPEECH_LANDED_FIELD] = revised
                    row['_v3_landing_provenance'] = 'completed_snapshot_update_time'
            elif _timestamp(row.get(SPEECH_LANDED_FIELD)) is None:
                seeds[rid] = 'landing_unknown'
        if (internal_start and start < since) or (internal_end and end > until - silence):
            # A closure-only source on the other side is allowed only if a full silence
            # separates it from the partition. Its component is excluded below.
            if not (end <= since - silence or start >= until + silence):
                raise Conflict('rederive_live_boundary')
        if (not internal_start and start < since + silence) or (not internal_end and end > until - silence):
            seeds[rid] = 'outer_edge'
        elif end <= since or start >= until:
            seeds[rid] = 'outside_partition'
        bounds.append((start, end, rid))

    # Use source envelopes before deduplication or manual cuts. A whole source is indivisible
    # for custody, even when multiple parts of it would become separate planner windows.
    tail, previous = None, None
    for start, end, rid in sorted(bounds):
        if tail is not None and previous is not None and start - tail < silence:
            related[rid].add(previous)
            related[previous].add(rid)
            tail = max(tail, end)
        else:
            tail = end
        previous = rid

    excluded = {}
    # Edge reasons take priority when the same ownership component also lacks landing evidence.
    for seed, reason in sorted(seeds.items(), key=lambda item: item[1] != 'outer_edge'):
        pending = deque([seed])
        while pending:
            key = pending.popleft()
            if key in excluded:
                continue
            if reason == 'outer_edge' and key in missing:
                raise Conflict('rederive_live_edge_closure')
            excluded[key] = reason
            pending.extend(related[key] - excluded.keys())
    return excluded
