"""Record authorization and exact transcript fragment selection for Dream citations."""

import math
from urllib.parse import unquote


def base_ref(ref: str) -> str:
    return ref.partition('#')[0]


def canonical_collection(collection: str) -> str:
    """Legacy `memories` is the same owner collection as `memory_items`."""
    return 'memory_items' if collection == 'memories' else collection


def canonical_ref(ref: str) -> str:
    """New sessions use one memory ref spelling; stored legacy receipts still decode."""
    if ref.startswith('memories/'):
        return 'memory_items/' + ref.removeprefix('memories/')
    return ref


def has_ref(ref: str, records) -> bool:
    return base_ref(ref) in records


def _seconds(value):
    try:
        parts = str(value).split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
            if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
                return None
            result = hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 1:
            result = float(parts[0])
        else:
            return None
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def cited_value(ref: str, records):
    """A fragment selects one segment by its ID or exact start time; never widen it."""
    base, separator, fragment = ref.partition('#')
    row = records.get(base)
    if row is None or not separator:
        return row
    fragment = unquote(fragment)
    if not fragment:
        return None
    segments = row.get('transcript_segments') or []
    matches = [segment for segment in segments if fragment in {segment.get('id'), segment.get('segment_id')}]
    if not matches:
        seconds = _seconds(fragment)
        if seconds is not None:
            matches = [segment for segment in segments if _seconds(segment.get('start')) == seconds]
    return matches[0] if len(matches) == 1 else None
