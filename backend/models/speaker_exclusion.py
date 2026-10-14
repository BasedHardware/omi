"""Pure manual-receipt exclusion walker shared by writers and the wire projection.

``utils.manual_speaker_assignments`` owns the receipt writes; the
``Conversation`` wire model projects the still-winning exclusions for clients
(``excluded_speakers``). Both must agree on exactly which voices a receipt
still excludes, so the walker lives here — pure stdlib, importable from the
model layer without dragging ``database``/``config`` into it.
"""

from typing import Mapping


def _receipt_section(receipt: object, key: str) -> Mapping:
    """A stored receipt is user data: a wrong-typed section must not crash the reader."""
    if not isinstance(receipt, Mapping):
        return {}
    section = receipt.get(key)
    return section if isinstance(section, Mapping) else {}


def receipt_rejected_speakers(receipt: Mapping) -> dict:
    """speaker_id -> its winning rejection decision, per the manual receipt.

    Speaker entries carry the speaker id in their key; selected-segment
    rejections carry the voice they were written against in ``speaker_id``.
    A rejection only stands while no newer explicit positive decision
    (an entry without ``rejection``) covers the same voice.
    """
    decisions: dict = {}
    for key, entry in _receipt_section(receipt, 'speakers').items():
        if not isinstance(entry, dict):
            continue
        try:
            speaker_id = int(key)
        except (TypeError, ValueError):
            continue
        decisions.setdefault(speaker_id, []).append(entry)
    for entry in _receipt_section(receipt, 'segments').values():
        if isinstance(entry, dict) and not entry.get('segment_only') and isinstance(entry.get('speaker_id'), int):
            decisions.setdefault(entry['speaker_id'], []).append(entry)
    rejected: dict = {}
    for speaker_id, entries in decisions.items():
        rejection = None
        positive = -1
        for entry in entries:
            generation = entry.get('generation', 0)
            if entry.get('rejection'):
                if rejection is None or generation >= rejection.get('generation', 0):
                    rejection = entry
            else:
                positive = max(positive, generation)
        if rejection is not None and positive <= rejection.get('generation', 0):
            rejected[speaker_id] = rejection
    return rejected


def receipt_excluded_speakers(receipt: object) -> list:
    """Sorted speaker ids whose whole-voice ``not_a_person`` still wins.

    Mirrors the ignored-marker rule: only a still-winning ``not_a_person``
    rejection excludes a voice — newer ``not_me``/``not_person`` decisions and
    every positive whole-voice decision (speaker entry or selected-segment
    bulk assign) supersede it, while ``segment_only`` (range) entries never
    unseat a whole-voice decision in either direction.
    """
    if not isinstance(receipt, Mapping):
        return []
    return sorted(
        speaker_id
        for speaker_id, decision in receipt_rejected_speakers(receipt).items()
        if (decision.get('rejection') or {}).get('kind') == 'not_a_person'
    )
