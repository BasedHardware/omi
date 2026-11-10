"""Deterministic sweep for overlap activity and exclusive fallback turns."""

from collections import defaultdict


def activity_regions(turns):
    events = defaultdict(list)
    for index, turn in enumerate(turns):
        events[turn['start']].append((True, index))
        events[turn['end']].append((False, index))
    active = set()
    times = sorted(events)
    for index, left in enumerate(times[:-1]):
        for add, key in events[left]:
            if add:
                active.add(key)
            else:
                active.discard(key)
        right = times[index + 1]
        if active and right > left:
            yield left, right, [turns[key] for key in sorted(active)]


def overlap_regions(turns):
    output = []
    for left, right, active in activity_regions(turns):
        speakers = sorted({t['speaker'] for t in active})
        if len(speakers) > 1:
            if output and output[-1]['end'] == left and output[-1]['speakers'] == speakers:
                output[-1]['end'] = right
            else:
                output.append({'start': left, 'end': right, 'speakers': speakers})
    return output


def exclusive_from_activity(turns):
    """Longest active turn wins, stable label tie-break; no acoustic confidence claim.

    Used only when an adapter/cache lacks native exclusive diarization. Preserve
    overlaps separately so callers can distinguish this derived projection.
    """
    output = []
    for left, right, active in activity_regions(turns):
        winner = min(active, key=lambda t: (-(t['end'] - t['start']), t['speaker']))['speaker']
        if output and output[-1]['end'] == left and output[-1]['speaker'] == winner:
            output[-1]['end'] = right
        else:
            output.append({'start': left, 'end': right, 'speaker': winner})
    return output
