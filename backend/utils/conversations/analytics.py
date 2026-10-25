"""Per-conversation speaker analytics (issue #4481).

Fireflies-style stats for a single conversation: for each speaker, their talk time,
word count, and words per minute, plus the conversation totals. The aggregation is
pure (no I/O) so it is fully unit-tested; the router supplies the conversation and a
person_id -> name map.
"""

from typing import Dict, Optional

from utils.speakers.display import display_participants

from models.conversation import ConversationAnalytics, SpeakerAnalytics


def build_conversation_analytics(conversation, names: Dict[str, str]) -> ConversationAnalytics:
    """Compute per-speaker talk time, word count, and words per minute for a
    conversation, plus the conversation totals. Speakers are ordered by talk time."""
    seconds: Dict[str, float] = {}
    words: Dict[str, int] = {}
    labels: Dict[str, str] = {}
    person_ids: Dict[str, Optional[str]] = {}
    is_user_flags: Dict[str, bool] = {}

    segments = getattr(conversation, 'transcript_segments', None) or []
    display = display_participants(segments, names=names, resolution=getattr(conversation, 'speaker_resolution', None))
    for seg in segments:
        participant = display.for_segment(seg)
        person_id, is_user = getattr(seg, 'person_id', None), getattr(seg, 'is_user', False)
        key = 'user' if is_user else ('person:' + person_id if person_id else participant.key)
        label = participant.label
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

    ranked = []
    for key in seconds:
        talk = seconds[key]
        wpm = round(words[key] / (talk / 60.0), 1) if talk > 0 else 0.0
        share = round(talk / total_talk, 3) if total_talk > 0 else 0.0
        ranked.append(
            (
                talk,  # raw, unrounded duration used only for ordering
                SpeakerAnalytics(
                    speaker=labels[key],
                    person_id=person_ids[key],
                    is_user=is_user_flags[key],
                    talk_seconds=round(talk, 1),
                    word_count=words[key],
                    words_per_minute=wpm,
                    talk_share=share,
                ),
            )
        )
    # Most talk time first, ordered by the raw duration rather than the rounded display value
    # (rounding would collapse speakers whose true durations are within 0.05s and reorder them
    # by word count); word count then label break genuine ties deterministically.
    ranked.sort(key=lambda item: (-item[0], -item[1].word_count, item[1].speaker))
    speakers = [item[1] for item in ranked]

    overall_wpm = round(total_words / (total_talk / 60.0), 1) if total_talk > 0 else 0.0
    return ConversationAnalytics(
        conversation_id=getattr(conversation, 'id', '') or '',
        total_seconds=round(total_talk, 1),
        total_words=total_words,
        words_per_minute=overall_wpm,
        speaker_count=len(
            {
                (
                    "user"
                    if seg.is_user
                    else ("person:" + seg.person_id if seg.person_id else display.for_segment(seg).key)
                )
                for seg in segments
                if display.for_segment(seg).countable
            }
        ),
        speakers=speakers,
    )
