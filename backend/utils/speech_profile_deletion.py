from typing import Optional


def teaching_segment_ids_for_deleted_sample(person: Optional[dict], conversation_id: str) -> list[str]:
    """Segment ids whose teaching profile should be dropped with this sample.

    Deleting the audio blob alone leaves the stored embedding in place, so the
    next tagged segment never replaces the profile (#5084).
    """
    if not person or not conversation_id:
        return []
    if person.get('person_voice_confirmations') is not None:
        entries = [
            *person['person_voice_confirmations'],
            {'source': (person.get('person_voice_base') or {}).get('source') or {}},
        ]
        return [
            str(sid)
            for entry in entries
            if entry.get('source', {}).get('conversation_id') == conversation_id
            for sid in entry['source'].get('segment_ids') or []
            if sid
        ]
    source = person.get('speech_sample_source') or {}
    if source.get('conversation_id') != conversation_id:
        return []
    return [str(segment_id) for segment_id in source.get('segment_ids') or [] if segment_id]
