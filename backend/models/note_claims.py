"""Pure validation of claim spans against the current note projection."""

from typing import Any


def current_note_claims(structured: Any) -> list[Any]:
    """Return claims still present in a Structured note or serialized projection.

    Preserve exact text and attribution; never mutate the note or read storage.
    Targets are JSON pointers to visible string fields, not claim metadata.
    """
    claims = structured.get('note_claims') if isinstance(structured, dict) else getattr(structured, 'note_claims', None)
    kept = []
    for claim in claims or []:
        target = claim.get('target') if isinstance(claim, dict) else getattr(claim, 'target', None)
        text = claim.get('text') if isinstance(claim, dict) else getattr(claim, 'text', None)
        if not isinstance(target, str) or not target.startswith('/') or not isinstance(text, str) or not text.strip():
            continue
        parts = target[1:].split('/')
        if parts[0] == 'note_claims':
            continue
        value = structured
        for part in parts:
            part = part.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not part.isascii() or not part.isdecimal() or (len(part) > 1 and part.startswith('0')):
                    value = None
                    break
                # Bound index parsing as well as indexing untrusted persisted targets.
                if len(part) > len(str(len(value))) or int(part) >= len(value):
                    value = None
                    break
                value = value[int(part)]
            elif isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None) if part in getattr(type(value), 'model_fields', {}) else None
        if isinstance(value, str) and text in value:
            kept.append(claim)
    return kept
