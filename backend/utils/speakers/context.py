"""Context supplies hypotheses and counts, never name-only identity labels."""

import re
import logging
from typing import Mapping, Sequence

from config.refactor_modes import serving_for, shadow_or_serve
from prometheus_client import Counter

logger = logging.getLogger(__name__)
NAME_LINKS = Counter('omi_speaker_evidence_name_link_total', 'Uncorroborated name links', ['outcome'])


def name_only_allowed(uid: str) -> bool:
    """Gate shared by sync and the live introduction hook; no identity guessing."""
    if shadow_or_serve('SPEAKER_EVIDENCE_MODE'):
        logger.info('event=refactor_shadow lane=L2 check=name_only_link outcome=disagree')
        NAME_LINKS.labels(outcome='blocked' if serving_for('SPEAKER_EVIDENCE_MODE', uid) else 'shadow').inc()
    return not serving_for('SPEAKER_EVIDENCE_MODE', uid)


def unique_roster(roster: Sequence[Mapping]) -> list[dict]:
    # Names are not keys: two attendees named John remain competing hypotheses.
    result, seen = [], set()
    for row in roster:
        identity = row.get('person_id') or row.get('email')
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        result.append(dict(row))
    return result


def participant_hint(roster: Sequence[Mapping], segments: Sequence) -> int | None:
    count = len(unique_roster(roster))
    hints = [max(2, count)] if count else []
    # Explicit inclusive count cues only. Speaker-id count is never evidence of
    # participant count. A cue cannot lower a larger observed roster.
    words = {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}
    for segment in segments:
        text = segment.get('text', '') if isinstance(segment, Mapping) else getattr(segment, 'text', '')
        for cue in re.findall(r'\b(?:the|just) (two|three|four|five|six) of us\b', text or '', re.I):
            hints.append(words[cue.lower()])
    return min(256, max(hints)) if hints else None
