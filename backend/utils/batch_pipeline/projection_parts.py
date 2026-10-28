"""Partition encrypted output with the exact legacy sync VAD grouping policy."""

from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from utils.batch_pipeline.contracts import MAX_PROJECTION_PARTS, projection_speech_spans
from utils.sync.vad_segments import merge_and_cap_vad_segments
from diarizer.batch_pipeline import validate_words


def bounded_projection_words(words, duration):
    """Intersect validated model clocks with PCM before deriving part geometry."""
    words = validate_words(words, duration)
    if not words:
        raise ValueError('successful batch result must contain words')
    # Keep every validated token, including zero-duration model words. A word
    # wholly in the allowed EOF tolerance becomes a point at EOF, not silence
    # silently removed from the transcript or an invented positive audio span.
    return [{**word, 'timestamp': [min(value, duration) for value in word['timestamp']]} for word in words]


def align_projection_words(words, payload, segment_id):
    """Preserve provider grouping while keeping point words out of voice evidence."""
    from utils.conversations.final_pass_assignment import assign_words

    aligned = words if payload.get('recovery_version') == 1 else assign_words(words, payload['diarization']['turns'])
    # Point words have text but no captured voice evidence. The legacy grouper
    # must not merge them with positive-duration neighbours in either producer.
    return [
        (
            {**word, 'speaker': f'BATCH_UNASSIGNED_{segment_id}_point_{index}'}
            if word['timestamp'][0] == word['timestamp'][1]
            else word
        )
        for index, word in enumerate(aligned)
    ]


def split_result(item, payload):
    duration = float(payload['audio_seconds'])
    if not 0 < duration <= 7200 or abs(duration - item.duration_seconds) > 0.1:
        raise ValueError('result audio duration differs from admitted capture')
    words = bounded_projection_words(payload['words'], duration)
    if 'speech_spans' in payload or item.requires_compute_admission:
        spans = projection_speech_spans(payload, duration)
    else:
        # Backward-compatible synthetic/pre-contract inputs only. Production
        # admission always requires authenticated, worker-measured VAD spans.
        spans = [{'start': word['timestamp'][0], 'end': word['timestamp'][1]} for word in words]
    groups = merge_and_cap_vad_segments(spans)
    if not 1 <= len(groups) <= MAX_PROJECTION_PARTS:
        raise ValueError('bounded projection part count required')
    if len(groups) == 1 and 'speech_spans' not in payload:
        return [(item, payload)]
    buckets: list[list[dict]] = [[] for _ in groups]
    index = 0
    for word in words:
        midpoint = sum(word['timestamp']) / 2
        while index + 1 < len(groups) and midpoint >= (groups[index]['end'] + groups[index + 1]['start']) / 2:
            index += 1
        buckets[index].append(word)
    parts = []
    for index, (group, selected) in enumerate(zip(groups, buckets)):
        start = min([group['start'], *(word['timestamp'][0] for word in selected)])
        end = max([group['end'], *(word['timestamp'][1] for word in selected)])
        part = replace(
            item,
            segment_id=uuid5(NAMESPACE_URL, f'batch-part:{item.segment_id}:{index}').hex,
            capture_at=item.capture_at + start,
            duration_seconds=end - start,
        )
        turns = [
            {**turn, 'start': max(start, turn['start']) - start, 'end': min(end, turn['end']) - start}
            for turn in payload['diarization']['turns']
            if turn['start'] < end and turn['end'] > start
        ]
        parts.append(
            (
                part,
                {
                    **payload,
                    'audio_seconds': end - start,
                    'speech_seconds': sum(max(0, min(end, span['end']) - max(start, span['start'])) for span in spans),
                    'words': [
                        {**word, 'timestamp': [value - start for value in word['timestamp']]} for word in selected
                    ],
                    'diarization': {**payload['diarization'], 'turns': turns},
                },
            )
        )
    return parts
