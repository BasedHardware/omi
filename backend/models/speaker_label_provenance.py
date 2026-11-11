"""Single projection of where a segment's speaker identity came from."""

from typing import Literal, Mapping, Optional

Source = Literal['manual', 'auto', 'carried']
_PUBLIC_SOURCES = {'manual', 'auto', 'carried'}


def project_source(segment: Mapping, decision: Optional[Mapping] = None) -> Optional[Source]:
    """manual | auto | carried for a labeled segment, else None.

    A winning receipt decision outranks every stored field: its ``source``
    marks carried-over identities, everything else it wrote is manual.
    Without a receipt the persisted public value is honored, then the
    internal match evidence proves an automatic label. An identity with no
    provenance at all projects None rather than guessing.
    """
    if isinstance(decision, Mapping):
        if not (decision.get('person_id') or decision.get('is_user')):
            return None
        return 'carried' if decision.get('source') == 'carried' else 'manual'
    if not (segment.get('person_id') or segment.get('is_user')):
        return None
    stored = segment.get('speaker_label_source')
    if stored in _PUBLIC_SOURCES:
        return stored
    if segment.get('speaker_match_source'):
        return 'auto'
    return None
