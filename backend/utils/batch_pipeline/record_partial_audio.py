"""Sample-exact retained coverage: late runs recognize only new stored audio."""

from bisect import bisect_right
import hashlib
import json

from config.record_partial import MAX_SOURCES, MAX_UNITS, UNIT_REFERENCES

RATE = 16000


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()


def inventory_digest(chunks):
    if len(chunks) > MAX_SOURCES:
        raise ValueError('partial source budget exceeded')
    return digest(
        [{key: chunk.get(key) for key in ('bucket', 'path', 'generation', 'timestamp', 'span')} for chunk in chunks]
    )


def union(ranges):
    merged = []
    normalized = [(r['start'], r['end']) if isinstance(r, dict) else tuple(r) for r in ranges]
    for start, end in sorted(normalized):
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            raise ValueError('invalid partial coverage')
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if len(merged) > MAX_SOURCES:
        raise ValueError('partial coverage budget exceeded')
    # Firestore rejects arrays directly nested inside arrays.
    return [{'start': start, 'end': end} for start, end in merged]


def missing_units(units, coverage):
    """Subtract *actual reference frames*, never padded unit wall-clock spans.

    All coordinates are integer 16kHz frames, including coverage persisted
    between runs. Sources and digests stay pinned; only slice offsets change.
    """
    coverage = [(r['start'], r['end']) for r in union(coverage)]
    ends = [end for _, end in coverage]
    result, added = [], []
    for start, _, refs in units:
        origin = round(start * RATE)
        selected = []
        for ref in refs:
            left = origin + ref['start_frame']
            right = left + ref['frames']
            cursor = left
            index = bisect_right(ends, left)
            for known_start, known_end in coverage[index:]:
                if known_start >= right:
                    break
                if known_start > cursor:
                    selected.append((ref, left, cursor, min(known_start, right)))
                cursor = max(cursor, known_end)
                if cursor >= right:
                    break
            if cursor < right:
                selected.append((ref, left, cursor, right))
        if not selected:
            continue
        added.extend([left, right] for _, _, left, right in selected)
        # Subtraction can split one source into thousands of holes. Reapply
        # the worker reference bound after slicing, not only before it.
        for index in range(0, len(selected), UNIT_REFERENCES):
            group = selected[index : index + UNIT_REFERENCES]
            new_origin = group[0][2]
            sliced = [
                {
                    **ref,
                    'start_frame': left - new_origin,
                    'offset_frame': ref['offset_frame'] + left - source_left,
                    'frames': right - left,
                }
                for ref, source_left, left, right in group
            ]
            result.append((new_origin / RATE, (group[-1][3] - new_origin) / RATE, sliced))
            if len(result) > MAX_UNITS:
                raise ValueError('partial unit budget exceeded')
    return result, union([*coverage, *added])
