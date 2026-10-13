"""Pure word alignment and calibrated Omi voiceprint naming."""

from bisect import bisect_right
from math import isfinite

from utils.stt.conversation_speakers import VOICE_MATCH_THRESHOLD, unit_voice_vector, voice_cosine_distance
from utils.stt.speaker_match import (
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    arbitrate_owner_matches,
    select_speaker_match,
)


def assign_words(words, turns):
    ordered = sorted(turns, key=lambda t: (t['start'], t['end'], t['speaker']))
    if any(not isfinite(float(t[k])) for t in ordered for k in ('start', 'end')):
        raise ValueError('invalid turn')
    if any(t['end'] <= t['start'] for t in ordered):
        raise ValueError('invalid turn')
    if any(a['end'] > b['start'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('turns must be exclusive')
    starts = [t['start'] for t in ordered]
    result = []
    for word in words:
        left, right = map(float, word['timestamp'])
        if not isfinite(left) or not isfinite(right) or right < left:
            raise ValueError('invalid word clock')
        index = max(0, bisect_right(starts, left) - 1)
        candidates = []
        while index < len(ordered) and ordered[index]['start'] <= right:
            turn = ordered[index]
            overlap = min(right, turn['end']) - max(left, turn['start'])
            midpoint = (left + right) / 2
            if overlap > 0 or (left == right and turn['start'] <= left < turn['end']):
                candidates.append((overlap, turn['start'] <= midpoint < turn['end'], -index, turn))
            index += 1
        selected = max(candidates, key=lambda x: x[:3])[-1] if candidates else None
        # Gaps abstain; never make a silence-gap word the owner's voice.
        result.append({**word, 'speaker': selected['speaker'] if selected else None})
    return result


def name_centroids(centroids, voiceprints, *, owner_reserved=False):
    prints = {k: unit_voice_vector(v) for k, v in voiceprints.items()}
    prints = {k: v for k, v in prints.items() if v is not None}
    distances, decisions = {}, {}
    for speaker, entry in centroids.items():
        vector = unit_voice_vector(entry['embedding'])
        if vector is None or entry['evidence_seconds'] < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
            continue
        row = {k: voice_cosine_distance(vector, v) for k, v in prints.items() if vector.shape == v.shape}
        distances[speaker] = row
        decisions[speaker] = select_speaker_match(row, threshold=VOICE_MATCH_THRESHOLD)
    return arbitrate_owner_matches(distances, decisions, owner_reserved=owner_reserved)


def skip_single_speaker(resolution):
    # Missing embeddings/partial evidence must never qualify for the cheap branch.
    return resolution is not None and resolution.coverage >= 0.9 and len(set(resolution.speaker_ids.values())) == 1
