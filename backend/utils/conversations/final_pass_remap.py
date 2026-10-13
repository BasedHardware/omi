"""Fail-closed record promotion preserving every user annotation."""

from copy import deepcopy

from utils.conversations.segment_remap import plan_segment_remap, remap_receipt, remap_translations, remap_source_ids
from utils.manual_speaker_assignments import apply_manual_assignments


def remap_final_record(old, new, receipt, structured, *, clock_offset):
    new = deepcopy(new)
    plan = plan_segment_remap(old, new, offset_seconds=clock_offset)
    if not plan.safe:
        raise ValueError('unsafe final record remap')
    remapped_receipt = remap_receipt(receipt, old, new, plan)
    translations = remap_translations(old, plan)
    by_id = {s['id']: s for s in new}
    edited = {}
    for source in old:
        # Legacy manually edited segments may predate a receipt. Preserve both
        # positive and negative owner edits, plus manually assigned people.
        if source.get('speaker_label_source') in {'manual', 'carried'} or (
            not source.get('speaker_match_source') and source.get('person_id')
        ):
            identity = (source.get('is_user', False), source.get('person_id'))
            for target in plan.ids[source['id']]:
                if target in edited and edited[target] != identity:
                    raise ValueError('conflicting edited identities')
                edited[target] = identity
                by_id[target].update(
                    is_user=identity[0],
                    person_id=identity[1],
                    speaker_label_source=source.get('speaker_label_source') or 'manual',
                    speaker_match_source=None,
                )
        for target in plan.ids[source['id']]:
            if target in translations:
                by_id[target]['translations'] = translations[target]
    new = apply_manual_assignments(new, remapped_receipt)

    def remap_refs(value):
        if isinstance(value, dict):
            return {
                k: remap_source_ids(v, plan) if k == 'source_segment_ids' else remap_refs(v) for k, v in value.items()
            }
        if isinstance(value, list):
            return [remap_refs(v) for v in value]
        return value

    # Align the new record to the persisted conversation clock.
    for segment in new:
        segment['start'] -= clock_offset
        segment['end'] -= clock_offset
        if segment['start'] < 0:
            raise ValueError('negative remapped clock')
    return {
        'transcript_segments': new,
        'manual_speaker_assignments': remapped_receipt,
        'structured': remap_refs(deepcopy(structured)),
    }
