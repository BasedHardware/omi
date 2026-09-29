"""Which stored voiceprints are trustworthy enough to identify a speaker."""

from typing import Any, Mapping, Optional


def usable_person_voiceprint(person: Mapping[str, Any]) -> Optional[list]:
    """The person's embedding, or None when it cannot be trusted.
    Only people with v3+ speech samples qualify (pre-v3 models carry stale embeddings, #6238).
    """
    embedding = person.get('speaker_embedding')
    v = person.get('speech_samples_version')
    if embedding and person.get('speech_samples') and isinstance(v, int) and v >= 3:
        return embedding
    return None
