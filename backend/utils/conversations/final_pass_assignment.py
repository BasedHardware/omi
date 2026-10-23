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
        seconds = entry.get('evidence_seconds')
        if (
            vector is None
            or type(seconds) not in (int, float)
            or not isfinite(seconds)
            or seconds < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
        ):
            continue
        row = {k: voice_cosine_distance(vector, v) for k, v in prints.items() if vector.shape == v.shape}
        distances[speaker] = row
        decisions[speaker] = select_speaker_match(row, threshold=VOICE_MATCH_THRESHOLD)
    return arbitrate_owner_matches(distances, decisions, owner_reserved=owner_reserved)


def skip_single_speaker(resolution):
    # Missing embeddings/partial evidence must never qualify for the cheap branch.
    return resolution is not None and resolution.coverage >= 0.9 and len(set(resolution.speaker_ids.values())) == 1


def build_turns(words, turns, *, decisions=None, scope, id_namespace, source='batch_pyannote', speaker_ids=None):
    """Build faithful transcript turns without rebasing or imputing gap voices.

    Only consecutive words of the same actual voice join, and only for gaps
    strictly below two seconds. Anonymous gap words remain explicit abstentions.
    id_namespace includes its trailing separator to preserve caller ID recipes.
    """
    from uuid import NAMESPACE_URL, uuid5

    from models.transcript_segment import TranscriptSegment
    from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL

    decisions = decisions or {}
    speaker_ids = (
        speaker_ids
        if speaker_ids is not None
        else {voice: index for index, voice in enumerate(sorted({t['speaker'] for t in turns}, key=str))}
    )
    segments = []
    for word in assign_words(words, turns):
        voice = word['speaker']
        decision = decisions.get(voice)
        identity = decision.person_id if decision is not None else None
        left, right = map(float, word['timestamp'])
        text = word.get('text', word.get('word', ''))
        if segments and voice is not None and segments[-1].speaker == str(voice) and left - segments[-1].end < 2:
            segments[-1].text += ' ' + text
            segments[-1].end = max(segments[-1].end, right)
            continue
        segments.append(
            TranscriptSegment(
                id=str(uuid5(NAMESPACE_URL, f'{id_namespace}{len(segments)}')),
                text=text,
                start=left,
                end=right,
                speaker=str(voice) if voice is not None else None,
                speaker_id=speaker_ids.get(voice, OMI_SPEAKER_ID_SENTINEL),
                speaker_id_scope=scope,
                is_user=identity == 'user',
                person_id=identity if identity not in (None, 'user') else None,
                speaker_match_source=source if voice is not None else 'batch_abstention',
                speaker_label_source='auto' if identity else None,
                speaker_identity_status=(
                    'user'
                    if identity == 'user'
                    else 'not_user' if identity else 'ambiguous' if voice is None else 'no_match'
                ),
            )
        )
    return segments
