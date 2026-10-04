"""Invalidate provenance together with its edited prose or source evidence."""

import copy
from typing import Any, Sequence


def _value(value: Any, field: str, default=None):
    return value.get(field, default) if isinstance(value, dict) else getattr(value, field, default)


def invalidate_note_claims(structured: Any, targets: Sequence[str] = (), *, segment_id: str | None = None) -> bool:
    claims = _value(structured, 'note_claims')
    if claims is None:
        return False

    def affected(claim):
        target = _value(claim, 'target', '')
        if (
            not isinstance(target, str)
            or not target
            or any(root == '' or target == root or target.startswith(root + '/') for root in targets)
        ):
            return True
        return segment_id is not None and (
            f'speech:{segment_id}' in (_value(claim, 'evidence_ids') or [])
            or any(
                _value(source, 'source_kind') == 'speech' and _value(source, 'source_ref') == segment_id
                for source in (_value(claim, 'evidence_sources') or [])
            )
        )

    kept = [claim for claim in claims if not affected(claim)] if isinstance(claims, list) else []
    if kept == claims:
        return False
    if isinstance(structured, dict):
        structured['note_claims'] = kept
    else:
        structured.note_claims = kept
    return True


def claim_invalidation_patch(structured: Any, targets: Sequence[str] = (), *, segment_id: str | None = None) -> dict:
    copied = copy.deepcopy(structured)
    return (
        {'structured.note_claims': _value(copied, 'note_claims')}
        if invalidate_note_claims(copied, targets, segment_id=segment_id)
        else {}
    )


def apply_user_title(data: dict, title: str | None) -> None:
    if title is None:
        return
    structured = data.get('structured')
    if not isinstance(structured, dict):
        structured = {}
        data['structured'] = structured
    structured['title'] = title
    invalidate_note_claims(structured, ('/title',))


def prepare_generated_note(data: dict, existing: dict, delete_field: Any) -> None:
    title = existing.get('user_title')
    apply_user_title(data, title if isinstance(title, str) and title.strip() else None)
    structured, previous = data.get('structured'), existing.get('structured')
    # Firestore set(merge=True) recursively merges maps. A flag-off replacement
    # omits note_claims, so explicitly remove an older episode's annotations.
    if (
        isinstance(structured, dict)
        and 'note_claims' not in structured
        and isinstance(previous, dict)
        and 'note_claims' in previous
    ):
        structured['note_claims'] = delete_field


def summary_source_reference_invalidations(structured: Any, segment_id: str) -> dict:
    if not isinstance(structured, dict):
        return {}
    invalidations = claim_invalidation_patch(structured, segment_id=segment_id)
    for field in ('sections', 'action_items'):
        items = structured.get(field)
        if not isinstance(items, list):
            continue
        copied = copy.deepcopy(items)
        changed = False
        for item in copied:
            references = item.get('source_segment_ids') if isinstance(item, dict) else None
            if isinstance(references, (list, tuple, set)) and segment_id in references:
                item['source_segment_ids'] = []
                changed = True
        if changed:
            invalidations[f'structured.{field}'] = copied
    return invalidations
