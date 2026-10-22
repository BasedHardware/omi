"""Render the identity policy's bands and probabilities, without re-thresholding them."""

from __future__ import annotations

import json
from typing import Any
from models.speaker_evidence import SpeakerEvidence

SPEAKER_RULES = '''SPEAKER ATTRIBUTION
- Speaker keys identify voice clusters, never people by themselves.
- Use names only for the best candidate in the confident band. For the likely band, hedge as "likely X".
- For the unknown band say "a speaker". Never attribute personal stories to a named person without evidence.
- When candidates compete, prefer the higher probability; a listing or contact spelling alone never identifies a voice.
- Never infer the owner from a speaker number, a first-person story, the calendar, or an account profile.
- With unavailable speaker resolution, retain only supported existing labels; unresolved voices stay "a speaker".
- Contact spellings correct close sound-alikes, not identities: "Nick" may be spelled "Nik Shevchenko" when that
  contact corroborates the spoken name, but a contact entry alone does not establish that they spoke.
- If more than one contact could match a spoken name, keep the transcript spelling and do not pick one.
  Never merge two people because they share a first name; list competing contacts without choosing an identity.'''


def candidate_name(candidate: Any, people: list[dict[str, Any]]) -> str | None:
    names = {str(person.get('id')): str(person.get('name') or '').strip() for person in people}
    return (candidate.name or names.get(candidate.person_id) or '').strip() or None


def render_speaker_evidence(evidence: SpeakerEvidence | None, people: list[dict[str, Any]]) -> str:
    """List every candidate, best first, and every policy-selected notable similarity."""
    if evidence is None or evidence.status == 'unavailable':
        return SPEAKER_RULES + '\nResolution unavailable; use supported existing labels with the no-guess rule.'
    lines = [SPEAKER_RULES, 'VOICE EVIDENCE (data)', 'status=' + evidence.status]
    for cluster in evidence.clusters:
        candidates = sorted(cluster.candidates, key=lambda candidate: -candidate.probability)
        entries = [
            {
                'name': candidate_name(candidate, people),
                'person_id': candidate.person_id,
                'probability': candidate.probability,
                'band': candidate.band,
                'source': candidate.source,
            }
            for candidate in candidates
        ]
        lines.append(
            json.dumps(
                {'voice': cluster.id, 'segments': cluster.segment_ids, 'candidates_best_first': entries},
                ensure_ascii=False,
            )
        )
    for pair in evidence.similarities:
        lines.append(json.dumps({'voices': [pair.a, pair.b], 'similarity': pair.similarity}))
    return '\n'.join(lines)
