"""Which stored voiceprints are trustworthy enough to identify a speaker."""

from typing import Any, Mapping, Optional


def usable_person_voiceprint(person: Mapping[str, Any]) -> Optional[list]:
    """The person's embedding, or None when it cannot be trusted.

    Only people with v3+ speech samples qualify: contacts without samples may
    carry stale embeddings from a pre-v3 model (#6238).
    """
    embedding = person.get('speaker_embedding')
    if embedding and person.get('speech_samples') and person.get('speech_samples_version', 1) >= 3:
        return embedding
    return None
