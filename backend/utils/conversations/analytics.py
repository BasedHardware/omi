"""Per-conversation speaker analytics (issue #4481).

Fireflies-style stats for a single conversation: for each speaker, their talk time,
word count, and words per minute, plus the conversation totals. The aggregation is
pure (no I/O) so it is fully unit-tested; the router supplies the conversation and a
person_id -> name map.
"""

from typing import Dict, Optional, Tuple

from models.conversation import ConversationAnalytics, SpeakerAnalytics


def _speaker_identity(seg, names: Dict[str, str]) -> Tuple[str, str, Optional[str], bool]:
    """Return (grouping key, display label, person_id, is_user) for a segment.

    The account owner's segments group under "You"; identified people group by their
    person_id (resolved to a name); everyone else groups by the diarization speaker
    label as "Speaker N".
    """
    if getattr(seg, 'is_user', False):
        return ('user', 'You', None, True)
    person_id = getattr(seg, 'person_id', None)
    if person_id:
        return (f'person:{person_id}', names.get(person_id) or 'Unknown', person_id, False)
    speaker_id = getattr(seg, 'speaker_id', None)
    if speaker_id is not None:
        return (f'speaker:{speaker_id}', f'Speaker {speaker_id}', None, False)
    speaker = getattr(seg, 'speaker', None) or 'SPEAKER_00'
    return (f'speaker:{speaker}', str(speaker), None, False)


def build_conversation_analytics(conversation, names: Dict[str, str]) -> ConversationAnalytics:
    """Compute per-speaker talk time, word count, and words per minute for a
    conversation, plus the conversation totals. Speakers are ordered by talk time."""
    seconds: Dict[str, float] = {}
    words: Dict[str, int] = {}
    labels: Dict[str, str] = {}
    person_ids: Dict[str, Optional[str]] = {}
    is_user_flags: Dict[str, bool] = {}

    for seg in getattr(conversation, 'transcript_segments', None) or []:
        key, label, person_id, is_user = _speaker_identity(seg, names)
        start = getattr(seg, 'start', 0) or 0
        end = getattr(seg, 'end', 0) or 0
        text = getattr(seg, 'text', '') or ''
        seconds[key] = seconds.get(key, 0.0) + max(0.0, float(end) - float(start))
        words[key] = words.get(key, 0) + len(text.split())
        labels[key] = label
        person_ids[key] = person_id
        is_user_flags[key] = is_user

    total_talk = sum(seconds.values())
    total_words = sum(words.values())

    speakers = []
    for key in seconds:
        talk = seconds[key]
        wpm = round(words[key] / (talk / 60.0), 1) if talk > 0 else 0.0
        share = round(talk / total_talk, 3) if total_talk > 0 else 0.0
        speakers.append(
            SpeakerAnalytics(
                speaker=labels[key],
                person_id=person_ids[key],
                is_user=is_user_flags[key],
                talk_seconds=round(talk, 1),
                word_count=words[key],
                words_per_minute=wpm,
                talk_share=share,
            )
        )
    # Most talk time first; word count then label break ties deterministically.
    speakers.sort(key=lambda s: (-s.talk_seconds, -s.word_count, s.speaker))

    overall_wpm = round(total_words / (total_talk / 60.0), 1) if total_talk > 0 else 0.0
    return ConversationAnalytics(
        conversation_id=getattr(conversation, 'id', '') or '',
        total_seconds=round(total_talk, 1),
        total_words=total_words,
        words_per_minute=overall_wpm,
        speaker_count=len(speakers),
        speakers=speakers,
    )
